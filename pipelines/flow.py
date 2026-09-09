"""Orchestration over the 200 repos with content-hash caching.

This is the plain-Python shape of the pipeline; in production wrap each step as a
Prefect/Dagster task for retries, caching (key on repo content hash), and
parallel fan-out across the portfolio.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

from convergence_factory import census, graph, report
from convergence_factory.runner import extract
from convergence_factory.semantic.probe import recall
from convergence_factory.store import Store


def compute_repo_hash(repo_path: str) -> str:
    """Computes a sha256 content hash of non-hidden repository files."""
    hasher = hashlib.sha256()
    for root, _, files in os.walk(repo_path):
        for f in sorted(files):
            if f.startswith("."):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "rb") as fh:
                    hasher.update(fh.read())
            except (OSError, IOError):
                pass
    return hasher.hexdigest()


def run_pipeline(repos_root: str, out_dir: str, use_cache: bool = True) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    store = Store(os.path.join(out_dir, "factory.db"))
    stats = {"total_scans": 0, "extracted": 0, "cached": 0}

    for scan in census.scan(repos_root):          # M0.3 ingest + census
        stats["total_scans"] += 1
        if use_cache:
            curr_hash = compute_repo_hash(scan.repo_path)
            prev_hash = store.get_cache(scan.project.id)
            if prev_hash == curr_hash:
                stats["cached"] += 1
                continue
            if prev_hash is not None:
                store.clear_project(scan.project.id)
            extract(store, scan)                  # M0.2 run plugins -> facts
            store.set_cache(scan.project.id, curr_hash)
            stats["extracted"] += 1
        else:
            extract(store, scan)
            stats["extracted"] += 1

    g = graph.build(store)                         # M0.4 + M1.6 graph + cluster
    candidates = recall(store)                     # M1.5 semantic recall
    summary = report.render(store, g, candidates, out_dir)  # M1.6 publish
    store.close()
    summary["pipeline_stats"] = stats
    return summary
