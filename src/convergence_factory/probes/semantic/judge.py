"""Phase 1.5 — The Pairwise Judge.

Evaluates semantic candidate pairs surfaced by vector embeddings (recall)
and makes an explicit determination: CONFIRMED or REFUTED as duplicate
capabilities, stamping a confidence score, rationale, and convergence play.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import urllib.request
from typing import Dict, List, Optional


from convergence_factory.core.store import Store


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


class RestJudge(Judge):
    """Pairwise judge delegating to an LLM endpoint (Ollama, vLLM, OpenAI, Azure, Groq, LiteLLM)."""

    def __init__(self, endpoint: Optional[str] = None,
                 model: Optional[str] = None,
                 api_key: Optional[str] = None,
                 fallback: Optional[Judge] = None):
        self.endpoint = endpoint or os.environ.get("CONVERGENCE_LLM_ENDPOINT") or os.environ.get("LLM_ENDPOINT") or "http://localhost:11434/api/generate"
        self.model = model or os.environ.get("CONVERGENCE_LLM_MODEL") or os.environ.get("LLM_MODEL") or "llama3"
        self.api_key = api_key or os.environ.get("CONVERGENCE_LLM_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.fallback = fallback or HeuristicJudge()

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
                "response_format": {"type": "json_object"}
            }
        else:
            payload_dict = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if is_chat_api:
                    content = data["choices"][0]["message"]["content"]
                    body = json.loads(content)
                else:
                    body = json.loads(data.get("response", "{}"))
                return JudgeResult(
                    confirmed=bool(body.get("confirmed", False)),
                    confidence=float(body.get("confidence", 0.5)),
                    reason=str(body.get("reason", "LLM judged evaluation")),
                    play=str(body.get("play", "LEAVE"))
                )
        except Exception:
            # Fallback gracefully to HeuristicJudge if model server is unreachable
            return self.fallback.evaluate(candidate, summary_a, summary_b, owner_a, owner_b)



def judge_candidates(arg1, arg2, judge: Optional[Judge] = None) -> List[dict]:
    """Evaluates all recall candidate pairs and records judgments in the store."""
    if isinstance(arg1, Store):
        store, candidates = arg1, arg2
    else:
        candidates, store = arg1, arg2
    judge = judge or HeuristicJudge()
    summaries = {row["module_id"]: row["summary"] for row in store.db.execute("SELECT module_id, summary FROM capability_summaries")}
    owners = store.module_owner()

    results = []
    for cand in candidates:
        ma, mb = cand["a"], cand["b"]
        sa = summaries.get(ma, ma)
        sb = summaries.get(mb, mb)
        oa = owners.get(ma, "unknown")
        ob = owners.get(mb, "unknown")

        res = judge.evaluate(cand, sa, sb, oa, ob)
        results.append({
            "a": ma,
            "b": mb,
            "similarity": cand.get("similarity", 0.0),
            "tier": cand.get("tier", "MED"),
            "confirmed": res.confirmed,
            "confidence": res.confidence,
            "reason": res.reason,
            "play": res.play,
            "owners": sorted({oa, ob})
        })

    return results
