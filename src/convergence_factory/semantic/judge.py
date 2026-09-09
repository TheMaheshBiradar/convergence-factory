"""Phase 1.5 — The Pairwise Judge.

Evaluates semantic candidate pairs surfaced by vector embeddings (recall)
and makes an explicit determination: CONFIRMED or REFUTED as duplicate
capabilities, stamping a confidence score, rationale, and convergence play.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Dict, List, Optional
import urllib.request

from ..store import Store


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


class HeuristicJudge(Judge):
    """Deterministic, dependency-free judge for local testing and CI."""

    def __init__(self, confidence_threshold: float = 0.70):
        self.threshold = confidence_threshold

    def evaluate(self, candidate: dict, summary_a: str, summary_b: str,
                 owner_a: str, owner_b: str) -> JudgeResult:
        sim = candidate.get("similarity", 0.0)

        # Tokenize meaningful words (>3 chars)
        words_a = set(re.findall(r'\b[a-z]{4,}\b', summary_a.lower()))
        words_b = set(re.findall(r'\b[a-z]{4,}\b', summary_b.lower()))
        overlap = words_a & words_b

        # High similarity (>0.75) or significant keyword overlap confirms duplication
        is_confirmed = sim >= self.threshold or len(overlap) >= 2
        confidence = round(max(sim, len(overlap) / max(len(words_a | words_b), 1)), 2)

        if is_confirmed:
            play = "RETIRE" if owner_a == owner_b else "STANDARDIZE"
            shared_terms = ", ".join(sorted(overlap)[:3]) if overlap else "semantic intent"
            reason = f"Shares functional domain ({shared_terms}) with similarity {sim:.2f}"
        else:
            play = "LEAVE"
            reason = f"Insufficient capability overlap (sim={sim:.2f}, shared keywords={len(overlap)})"

        return JudgeResult(
            confirmed=is_confirmed,
            confidence=confidence,
            reason=reason,
            play=play
        )


class RestJudge(Judge):
    """Pairwise judge delegating to a self-hosted LLM endpoint (vLLM, Ollama, etc.)."""

    def __init__(self, endpoint: str = "http://localhost:11434/api/generate",
                 model: str = "llama3", fallback: Optional[Judge] = None):
        self.endpoint = endpoint
        self.model = model
        self.fallback = fallback or HeuristicJudge()

    def evaluate(self, candidate: dict, summary_a: str, summary_b: str,
                 owner_a: str, owner_b: str) -> JudgeResult:
        prompt = f"""Compare the following two software module capability summaries:
Module A (Owner: {owner_a}):
{summary_a}

Module B (Owner: {owner_b}):
{summary_b}

Do these two modules perform substantially the same business capability?
Respond in strictly valid JSON format with keys:
"confirmed": true/false,
"confidence": 0.0-1.0,
"reason": "short explanation",
"play": "RETIRE" (if same owner) or "STANDARDIZE" (if different owners) or "LEAVE"
"""
        req_data = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False
        }).encode("utf8")

        try:
            req = urllib.request.Request(
                self.endpoint,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf8"))
                body = json.loads(data.get("response", "{}"))
                return JudgeResult(
                    confirmed=bool(body.get("confirmed", False)),
                    confidence=float(body.get("confidence", 0.5)),
                    reason=str(body.get("reason", "LLM pairwise comparison")),
                    play=str(body.get("play", "STANDARDIZE"))
                )
        except Exception:
            # Fall back gracefully to heuristic judge when endpoint is offline
            return self.fallback.evaluate(candidate, summary_a, summary_b, owner_a, owner_b)


def judge_candidates(store: Store, candidates: List[dict],
                     judge: Optional[Judge] = None) -> List[dict]:
    """Evaluates all candidate pairs through the judge."""
    judge = judge or HeuristicJudge()
    owner_map = store.module_owner()

    # Load summaries from store
    summaries: Dict[str, str] = {}
    for row in store.db.execute("SELECT module_id, summary FROM capability_summaries"):
        summaries[row["module_id"]] = row["summary"]

    evaluated = []
    for cand in candidates:
        mod_a = cand["a"]
        mod_b = cand["b"]
        sum_a = summaries.get(mod_a, "")
        sum_b = summaries.get(mod_b, "")
        own_a = owner_map.get(mod_a, "unknown")
        own_b = owner_map.get(mod_b, "unknown")

        res = judge.evaluate(cand, sum_a, sum_b, own_a, own_b)
        evaluated.append({
            **cand,
            "confirmed": res.confirmed,
            "confidence": res.confidence,
            "reason": res.reason,
            "play": res.play,
            "owners": sorted(list(set([own_a, own_b])))
        })

    return evaluated
