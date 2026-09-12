"""Uniform probe registry.

Two kinds of cross-cutting probe, both self-registering so the orchestrator runs
them without knowing their names:

  * FACT probes   — run in EXTRACT, after per-module language plugins; they write
                    normalized facts to the store (e.g. api/contract, clones).
  * REPORT probes — run in VIEWS; they read the store and emit artifacts, without
                    mutating facts (e.g. BOM SBOMs, schema FK/orphan analysis).

Language plugins keep their own REGISTRY (probes/integration/base.py); this adds
the same "drop a file, no orchestrator edits" property to portfolio probes.
"""
from __future__ import annotations

from typing import Callable, List, Tuple

FACT_PROBES: List[Tuple[str, Callable]] = []
REPORT_PROBES: List[Tuple[str, Callable]] = []


def fact_probe(name: str):
    def deco(fn: Callable):
        FACT_PROBES.append((name, fn))
        return fn
    return deco


def report_probe(name: str):
    def deco(fn: Callable):
        REPORT_PROBES.append((name, fn))
        return fn
    return deco
