"""Phase 1.5 — The Pairwise Judge.

Evaluates semantic candidate pairs surfaced by vector embeddings (recall)
and makes an explicit determination: CONFIRMED or REFUTED as duplicate
capabilities, stamping a confidence score, rationale, and convergence play.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional


from convergence_factory.core.errors import ERROR_TRACKER
from convergence_factory.core.store import Store
from convergence_factory.logger import LOGGER


@dataclass
class JudgeResult:
    confirmed: bool
    confidence: float
    reason: str
    play: str  # RETIRE, STANDARDIZE, or LEAVE


class Judge:
    def evaluate(self, candidate: dict, summary_a: str, summary_b: str,
                 owner_a: str, owner_b: str) -> JudgeResult:
        raise NotImplementedError


_STOP_WORDS = {
    "and", "for", "the", "with", "this", "that", "from", "uses", "into", "some",
    "plain", "more", "like", "also", "have", "been", "according", "various"
}

# Structural / infrastructure vocabulary that nearly EVERY module summary shares
# (verbs and platform nouns). Overlap on these says "both are Kafka services",
# not "both do the same thing" — so it must NOT drive a confirmation. This is the
# fix for the judge rubber-stamping unrelated services as duplicates.
_GENERIC = {
    "produce", "publish", "consume", "read", "write", "call", "serve", "expose",
    "event", "topic", "table", "column", "endpoint", "queue", "cache", "resource",
    "service", "module", "library", "job", "api", "rest", "grpc", "http", "sql",
    "kafka", "spring", "data", "jpa", "boot", "client", "server", "use", "using",
    "confluent", "psycopg", "sqlalchemy", "requests", "httpx", "axios", "npm",
}


def _stem(w: str) -> str:
    return re.sub(r'(?:ing|ers|er|ed|s)$', '', w)


def _domain_tokens(summary: str) -> set:
    """Meaningful (non-generic, non-stopword) stemmed tokens from a summary."""
    toks = re.findall(r'\b[a-z]{3,}\b', summary.lower())
    out = set()
    for w in toks:
        if w in _STOP_WORDS:
            continue
        s = _stem(w)
        if s in _GENERIC or w in _GENERIC:
            continue
        out.add(s)
    return out


def _parse_json_object(raw_text: str) -> dict:
    """Robustly extracts and parses a JSON object from raw LLM output, handling markdown blocks and preamble."""
    text = (raw_text or "").strip()
    if not text:
        return {}
    # 1. Direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # 2. Markdown fenced code block: ```json ... ```
    m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text, re.I)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # 3. First balanced/outer curly braces
    m = re.search(r'(\{[\s\S]*\})', text)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


class HeuristicJudge(Judge):
    """Deterministic, dependency-free judge for local testing and CI.

    Conservative by design: a stand-in judge must not launder low-confidence
    recall into "confirmed". Confirmation requires overlap on real DOMAIN terms
    (e.g. `order`, `customer`), never on shared structural vocabulary.
    """

    def __init__(self, confidence_threshold: float = 0.82):
        self.threshold = confidence_threshold

    def evaluate(self, candidate: dict, summary_a: str, summary_b: str,
                 owner_a: str, owner_b: str) -> JudgeResult:
        sim = candidate.get("similarity", 0.0)
        dom_a = _domain_tokens(summary_a)
        dom_b = _domain_tokens(summary_b)
        overlap = dom_a & dom_b

        # Confirm only on real shared domain terms: two of them, or one plus a
        # very high embedding similarity. Generic vocabulary never counts.
        is_confirmed = len(overlap) >= 2 or (len(overlap) >= 1 and sim >= self.threshold)
        denom = max(len(dom_a | dom_b), 1)
        confidence = round(min(sim, 0.5 + len(overlap) / denom) if is_confirmed
                           else min(sim, 0.4), 2)

        if is_confirmed:
            play = "RETIRE" if owner_a == owner_b else "STANDARDIZE"
            shared_terms = ", ".join(sorted(overlap)[:3]) if overlap else "semantic intent"
            reason = f"Shares functional domain ({shared_terms}) with similarity {sim:.2f}"
        else:
            play = "LEAVE"
            reason = f"Insufficient capability overlap (sim={sim:.2f}, shared keywords={len(overlap)})"

        return JudgeResult(confirmed=is_confirmed, confidence=confidence,
                           reason=reason, play=play)


def _build_auth_headers(api_key: Optional[str]) -> Dict[str, str]:
    """Normalizes API key/token into HTTP headers.

    Accepts raw tokens ('abc123xyz') or pre-formatted bearer strings ('Bearer abc123xyz').
    Emits Authorization: Bearer <token> (preventing 'Bearer Bearer' duplicate prefixing)
    as well as api-key and x-api-key headers for enterprise internal gateways (Azure, Kong, Envoy).
    """
    if not api_key:
        return {}
    token = api_key.strip()
    if not token:
        return {}

    if token.lower().startswith("bearer "):
        raw_token = token[7:].strip()
        auth_header = token
    else:
        raw_token = token
        auth_header = f"Bearer {token}"

    headers = {"Authorization": auth_header}
    if raw_token:
        headers["api-key"] = raw_token
        headers["x-api-key"] = raw_token
    return headers


def _extract_retry_after(headers, default_sleep: float) -> float:
    """Extracts wait duration in seconds from Retry-After or rate-limit reset headers."""
    if not headers:
        return default_sleep

    # 1. retry-after-ms (Azure OpenAI, LiteLLM, enterprise gateways)
    ms_val = headers.get("retry-after-ms")
    if ms_val:
        try:
            return max(0.1, float(ms_val) / 1000.0)
        except (ValueError, TypeError):
            pass

    # 2. Retry-After (seconds, e.g. '5' or '5.0')
    retry_val = headers.get("Retry-After")
    if retry_val:
        try:
            return max(0.1, float(retry_val))
        except (ValueError, TypeError):
            pass

    # 3. x-ratelimit-reset-requests or x-ratelimit-reset-tokens or x-ratelimit-reset
    for reset_header in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens", "x-ratelimit-reset"):
        reset_val = headers.get(reset_header)
        if reset_val:
            try:
                sec = float(reset_val)
                if sec > 0:
                    return min(sec, 60.0)
            except (ValueError, TypeError):
                pass

    return default_sleep


class RestJudge(Judge):
    """Pairwise judge delegating to an LLM endpoint (Ollama, vLLM, OpenAI, Azure, Groq, LiteLLM)."""

    def __init__(self, endpoint: Optional[str] = None,
                 model: Optional[str] = None,
                 api_key: Optional[str] = None,
                 fallback: Optional[Judge] = None,
                 timeout: Optional[float] = None,
                 max_retries: Optional[int] = None,
                 delay: Optional[float] = None):
        self.endpoint = endpoint or os.environ.get("CONVERGENCE_LLM_ENDPOINT") or os.environ.get("LLM_ENDPOINT") or "http://localhost:11434/api/generate"
        self.model = model or os.environ.get("CONVERGENCE_LLM_MODEL") or os.environ.get("LLM_MODEL") or "llama3.1:latest"
        self.api_key = api_key or os.environ.get("CONVERGENCE_LLM_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.fallback = fallback or HeuristicJudge()
        env_timeout = os.environ.get("CONVERGENCE_LLM_TIMEOUT")
        self.timeout = timeout if timeout is not None else (float(env_timeout) if env_timeout else 60.0)
        env_retries = os.environ.get("CONVERGENCE_LLM_MAX_RETRIES")
        self.max_retries = max_retries if max_retries is not None else (int(env_retries) if env_retries else 3)
        env_delay = os.environ.get("CONVERGENCE_LLM_DELAY")
        self.delay = delay if delay is not None else (float(env_delay) if env_delay else 0.0)
        self.last_error: Optional[str] = None

    def evaluate(self, candidate: dict, summary_a: str, summary_b: str,
                 owner_a: str, owner_b: str) -> JudgeResult:
        prompt = f"""You are an enterprise software architect evaluating two code modules for capability duplication.
Module A: {candidate['a']}
Summary A: {summary_a}

Module B: {candidate['b']}
Summary B: {summary_b}

Do these two modules implement the same core business capability or duplicate each other?
Respond strictly in JSON format with keys:
- "confirmed": boolean
- "confidence": float between 0.0 and 1.0
- "reason": short one-sentence explanation
- "play": "RETIRE" if same owner, "STANDARDIZE" if cross-owner duplicate, or "LEAVE" if distinct.
"""
        is_chat_api = "/chat/completions" in self.endpoint or "openai" in self.endpoint or "groq" in self.endpoint

        if is_chat_api:
            payload_dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are an enterprise software architect evaluating duplicate capabilities. Respond strictly in JSON."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 120,
            }
        else:
            payload_dict = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "num_predict": 120,
                    "temperature": 0.0
                }
            }

        headers = {"Content-Type": "application/json"}
        headers.update(_build_auth_headers(self.api_key))

        payload = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=payload, headers=headers)

        attempt = 0
        last_err = None
        while True:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if not is_chat_api and "error" in data:
                        raise RuntimeError(f"Ollama error: {data['error']}")
                    if is_chat_api:
                        content = data["choices"][0]["message"]["content"]
                    else:
                        content = data.get("response", "{}")
                    body = _parse_json_object(content)
                    self.last_error = None
                    return JudgeResult(
                        confirmed=bool(body.get("confirmed", False)),
                        confidence=float(body.get("confidence", 0.5)),
                        reason=str(body.get("reason", "LLM judged evaluation")),
                        play=str(body.get("play", "LEAVE"))
                    )
            except urllib.error.HTTPError as err:
                if err.code == 429 and attempt < self.max_retries:
                    attempt += 1
                    base_sleep = (2.0 ** attempt) + random.uniform(0.1, 0.6)
                    sleep_sec = _extract_retry_after(err.headers, base_sleep)
                    sleep_sec = min(sleep_sec, 60.0)
                    msg = f"\n    ⏳ [429 Rate Limit] Enterprise gateway throttled. Awaiting {sleep_sec:.1f}s (retry {attempt}/{self.max_retries})... "
                    print(msg, end="", flush=True)
                    LOGGER.warning("HTTP 429 Rate Limit from %s. Sleeping %.2fs (attempt %d/%d)",
                                   self.endpoint, sleep_sec, attempt, self.max_retries)
                    time.sleep(sleep_sec)
                    continue
                last_err = err
                break
            except Exception as err:
                last_err = err
                break

        self.last_error = str(last_err)
        is_429 = isinstance(last_err, urllib.error.HTTPError) and last_err.code == 429
        warning_type = "RateLimitExhausted" if is_429 else "LLMCallFailure"
        remedy = (
            f"Gateway rate limit reached after {self.max_retries} retries. Use --llm-delay (current: {self.delay}s) or increase --llm-max-retries."
            if is_429
            else "Ensure model server is running, model name matches, or increase timeout with --llm-timeout."
        )
        ERROR_TRACKER.record_warning(
            phase="probe:semantic:judge",
            source=f"{self.endpoint} (model: {self.model})",
            warning_type=warning_type,
            message=f"LLM call failed for '{candidate.get('a')}' <-> '{candidate.get('b')}': {last_err}",
            details=str(last_err),
            remediation=remedy
        )
        LOGGER.warning(
            "RestJudge LLM call failed for '%s' <-> '%s': %s (falling back to heuristic judge)",
            candidate.get("a"), candidate.get("b"), last_err
        )
        fallback_res = self.fallback.evaluate(candidate, summary_a, summary_b, owner_a, owner_b)
        fallback_res.reason = f"[Fallback: {last_err}] {fallback_res.reason}"
        return fallback_res


def test_llm_connection(
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 25.0
) -> dict:
    """Diagnostic tool to verify LLM endpoint reachability, model availability, and JSON generation latency.

    Returns a dict with:
      - ok (bool): True if model responded with valid JSON within timeout
      - endpoint (str): Effective endpoint URL
      - model (str): Target model name
      - latency_s (float): End-to-end response time in seconds
      - response (dict): Parsed JSON verdict
      - available_models (list): If Ollama, list of locally installed models
      - error (str, optional): Failure reason if not ok
      - suggestion (str, optional): Actionable remediation guidance
    """
    ep = endpoint or os.environ.get("CONVERGENCE_LLM_ENDPOINT") or os.environ.get("LLM_ENDPOINT") or "http://localhost:11434/api/generate"
    mdl = model or os.environ.get("CONVERGENCE_LLM_MODEL") or os.environ.get("LLM_MODEL") or "llama3.1:latest"
    key = api_key or os.environ.get("CONVERGENCE_LLM_KEY") or os.environ.get("OPENAI_API_KEY") or ""

    is_chat = "/chat/completions" in ep or "openai" in ep or "groq" in ep
    available_models = []

    # 1. If Ollama, probe /api/tags first for installed models
    if "11434" in ep or "/api/generate" in ep:
        try:
            base = ep.split("/api/")[0] if "/api/" in ep else "http://localhost:11434"
            tags_url = f"{base}/api/tags"
            req_tags = urllib.request.Request(tags_url, headers=_build_auth_headers(key))
            with urllib.request.urlopen(req_tags, timeout=3.0) as resp:
                tags_data = json.loads(resp.read().decode("utf-8"))
                for m in tags_data.get("models", []):
                    if isinstance(m, dict) and "name" in m:
                        available_models.append(m["name"])
        except Exception:
            pass

        if available_models:
            exact_or_latest = mdl if ":" in mdl else f"{mdl}:latest"
            if mdl in available_models:
                pass
            elif exact_or_latest in available_models:
                mdl = exact_or_latest
            else:
                return {
                    "ok": False,
                    "endpoint": ep,
                    "model": mdl,
                    "available_models": available_models,
                    "error": f"Model '{mdl}' is not installed in local Ollama.",
                    "suggestion": f"Available models: {', '.join(available_models)}. Update --llm-model or run `ollama pull {mdl}`."
                }

    # 2. Test actual generation prompt
    test_prompt = (
        'Evaluate if ModuleA and ModuleB duplicate each other.\n'
        'Respond strictly in JSON format with keys: "confirmed" (boolean), "confidence" (float), "reason" (string), "play" ("STANDARDIZE" or "LEAVE").'
    )

    if is_chat:
        payload_dict = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": "You are an enterprise architect. Respond strictly in JSON format."},
                {"role": "user", "content": test_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 100,
        }
    else:
        payload_dict = {
            "model": mdl,
            "prompt": test_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_predict": 100,
                "temperature": 0.0
            }
        }

    headers = {"Content-Type": "application/json"}
    headers.update(_build_auth_headers(key))

    payload = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(ep, data=payload, headers=headers)

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
            latency = round(time.time() - t0, 2)
            data = json.loads(raw_body)

            if not is_chat and "error" in data:
                return {
                    "ok": False,
                    "endpoint": ep,
                    "model": mdl,
                    "available_models": available_models,
                    "error": f"Ollama error: {data['error']}",
                    "suggestion": f"Check installed models with `ollama list` or pull model with `ollama pull {mdl}`."
                }

            if is_chat:
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                content = data.get("response", "")

            parsed = _parse_json_object(content)
            if not parsed:
                return {
                    "ok": False,
                    "endpoint": ep,
                    "model": mdl,
                    "latency_s": latency,
                    "error": f"LLM returned non-JSON or unparseable output: {content[:150]}",
                    "suggestion": "Ensure the model supports JSON mode or instruction following."
                }

            return {
                "ok": True,
                "endpoint": ep,
                "model": mdl,
                "latency_s": latency,
                "available_models": available_models,
                "response": parsed
            }

    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry_sec = _extract_retry_after(e.headers, 2.0)
            return {
                "ok": False,
                "endpoint": ep,
                "model": mdl,
                "available_models": available_models,
                "error": f"HTTP 429 Too Many Requests: Gateway rate limit exceeded (Retry-After: {retry_sec:.1f}s)",
                "suggestion": f"Enterprise gateway is throttling requests. Use --llm-delay (e.g. --llm-delay {max(0.5, retry_sec):.1f}) or wait {retry_sec:.1f}s before retrying."
            }
        err_msg = f"HTTP {e.code}: {e.reason}"
        try:
            body = e.read().decode("utf-8")
            err_msg += f" - {body[:150]}"
        except Exception:
            pass
        return {
            "ok": False,
            "endpoint": ep,
            "model": mdl,
            "available_models": available_models,
            "error": err_msg,
            "suggestion": "Check endpoint URL, deployment name, or authentication API key."
        }
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "endpoint": ep,
            "model": mdl,
            "available_models": available_models,
            "error": f"Connection failed: {e.reason}",
            "suggestion": f"Ensure LLM server is running at {ep} and accessible from this machine."
        }
    except TimeoutError:
        return {
            "ok": False,
            "endpoint": ep,
            "model": mdl,
            "available_models": available_models,
            "error": f"Connection timed out after {timeout}s",
            "suggestion": f"Model is taking too long to compute on CPU. Consider a smaller model (e.g. llama3.2:3b), GPU acceleration, or increasing timeout."
        }
    except Exception as e:
        return {
            "ok": False,
            "endpoint": ep,
            "model": mdl,
            "available_models": available_models,
            "error": str(e),
            "suggestion": "Check connection parameters and server logs."
        }


def judge_candidates(arg1, arg2, judge: Optional[Judge] = None, interactive: bool = True, delay: Optional[float] = None) -> List[dict]:
    """Evaluates all recall candidate pairs and records judgments in the store.

    When interactive=True (default), prints live progress per candidate pair so the CLI user is never left without feedback.
    Supports proactive throttle pacing between candidate pairs via delay (or judge.delay).
    """
    if isinstance(arg1, Store):
        store, candidates = arg1, arg2
    else:
        candidates, store = arg1, arg2
    judge = judge or HeuristicJudge()
    summaries = {row["module_id"]: row["summary"] for row in store.db.execute("SELECT module_id, summary FROM capability_summaries")}
    owners = store.module_owner()

    effective_delay = delay if delay is not None else getattr(judge, "delay", 0.0)
    total = len(candidates)
    results = []
    for idx, cand in enumerate(candidates, start=1):
        ma, mb = cand["a"], cand["b"]
        sa = summaries.get(ma, ma)
        sb = summaries.get(mb, mb)
        oa = owners.get(ma, "unknown")
        ob = owners.get(mb, "unknown")
        sim = cand.get("similarity", 0.0)

        if interactive:
            print(f"  [judge] [{idx}/{total}] Calling judge for '{ma}' <-> '{mb}' (similarity={sim:.2f}) ... ", end="", flush=True)

        t_start = time.time()
        res = judge.evaluate(cand, sa, sb, oa, ob)
        elapsed = time.time() - t_start

        if interactive:
            verdict = "CONFIRMED" if res.confirmed else "REFUTED"
            print(f"-> [{verdict}] in {elapsed:.2f}s (conf={res.confidence:.2f}, play={res.play})", flush=True)
            if res.reason:
                print(f"            Reason: {res.reason}", flush=True)

        results.append({
            "a": ma,
            "b": mb,
            "similarity": sim,
            "tier": cand.get("tier", "MED"),
            "confirmed": res.confirmed,
            "confidence": res.confidence,
            "reason": res.reason,
            "play": res.play,
            "owners": sorted({oa, ob})
        })

        if effective_delay > 0 and idx < total:
            time.sleep(effective_delay)

    return results

