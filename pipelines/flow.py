"""Orchestration over the 200 repos.

This is the plain-Python shape of the pipeline; in production wrap each step as a
Prefect/Dagster task for retries, caching (key on repo content hash), and
parallel fan-out across the portfolio. The logic is identical to `cli.cmd_run`.
"""
from __future__ import annotations

from convergence_factory import census, graph, report
from convergence_factory.runner import extract
from convergence_factory.semantic.probe import recall
from convergence_factory.store import Store


def run_pipeline(repos_root: str, out_dir: str) -> dict:
    store = Store(f"{out_dir}/factory.db")
    for scan in census.scan(repos_root):          # M0.3 ingest + census
        extract(store, scan)                      # M0.2 run plugins -> facts
    g = graph.build(store)                         # M0.4 + M1.6 graph + cluster
    candidates = recall(store)                     # M1.5 semantic recall
    summary = report.render(store, g, candidates, out_dir)  # M1.6 publish
    store.close()
    return summary
