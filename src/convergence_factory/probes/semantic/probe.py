"""M1.5 — the recall pipeline.

For each module: summarize -> embed the summary -> brute-force nearest neighbours
(fine at portfolio scale; swap in an ANN index for millions of vectors). Pairs
above a threshold are CANDIDATES only — tier MED/LOW, never promoted. An LLM/
human judge confirms them in Phase 1.5. This is the net for functional overlap
that shares no infrastructure and so is invisible to the integration probe.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import List

from convergence_factory.core.schema import CapabilitySummary
from convergence_factory.core.store import Store
from .embedder import Embedder, HashingEmbedder, cosine
from .summarizer import HeuristicSummarizer, Summarizer


def recall(store: Store, embedder: Embedder = None, summarizer: Summarizer = None,
           med_threshold: float = 0.75, low_threshold: float = 0.55) -> List[dict]:
    embedder = embedder or HashingEmbedder()
    summarizer = summarizer or HeuristicSummarizer()

    facts_by_mod = defaultdict(list)
    for f in store.integration_facts():
        facts_by_mod[f.module_id].append(f)
    deps_by_mod = defaultdict(list)
    for row in store.db.execute("SELECT module_id, purl FROM dependencies"):
        deps_by_mod[row["module_id"]].append(row["purl"].split("/")[-1])

    vectors = {}
    summaries = []
    for m in store.modules():
        text = summarizer.summarize(m.name, facts_by_mod.get(m.id, []),
                                    deps_by_mod.get(m.id, []))
        vectors[m.id] = embedder.embed(text)
        summaries.append(CapabilitySummary(
            module_id=m.id, summary=text, embedding_ref=f"vec:{m.id}", tier="MED"))
    store.add_summaries(summaries)

    candidates = []
    for a, b in combinations(sorted(vectors), 2):
        sim = cosine(vectors[a], vectors[b])
        if sim >= low_threshold:
            candidates.append({
                "a": a, "b": b, "similarity": round(sim, 3),
                "tier": "MED" if sim >= med_threshold else "LOW"})
    candidates.sort(key=lambda c: -c["similarity"])
    return candidates
