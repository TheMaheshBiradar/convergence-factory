"""M1.5 — capability summaries.

The production `RestSummarizer` asks a self-hosted LLM for a short, language-
neutral description of what a module does. `HeuristicSummarizer` derives one from
the module's already-extracted facts (topics, tables, calls, deps) — no model
required — which is enough to drive recall in a local run and doubles as a decent
fallback when the LLM is unavailable.
"""
from __future__ import annotations

from typing import List, Protocol

from convergence_factory.core.schema import IntegrationFact


class Summarizer(Protocol):
    def summarize(self, module_name: str, facts: List[IntegrationFact],
                  deps: List[str]) -> str: ...


class HeuristicSummarizer:
    def summarize(self, module_name, facts, deps):
        verbs = {"PRODUCES": "publishes", "CONSUMES": "consumes",
                 "READS": "reads", "WRITES": "writes", "CALLS": "calls"}
        parts = []
        for f in facts:
            noun = {"KAFKA_TOPIC": "event", "SQL_TABLE": "table",
                    "HTTP_ENDPOINT": "endpoint"}.get(f.resource_type, "resource")
            parts.append(f"{verbs.get(f.direction, f.direction.lower())} {noun} {f.resource_id}")
        summary = f"{module_name}: " + "; ".join(sorted(set(parts)))
        if deps:
            summary += " | uses " + ", ".join(sorted(set(deps))[:6])
        return summary


class RestSummarizer:
    def __init__(self, url: str = ""):
        self.url = url

    def summarize(self, module_name, facts, deps):  # pragma: no cover
        raise NotImplementedError(
            "RestSummarizer is a stub. Point it at your self-hosted LLM, or use "
            "HeuristicSummarizer for a local run.")
