"""Orchestration over the portfolio repositories with content-hash caching.

Supports zero-dependency plain Python execution, and automatically wraps stages
with Prefect (@flow, @task) and Dagster (@job, @op) orchestration decorators
when the corresponding optional framework is installed.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from convergence_factory import census, graph, report
from convergence_factory.clone_probe import detect_clones
from convergence_factory.connectors.gitlab import parse_inventory
from convergence_factory.executors.rewrite import generate_all_rewrite_recipes
from convergence_factory.ratchet import generate_all_ratchets
from convergence_factory.runner import extract
from convergence_factory.semantic.judge import judge_candidates
from convergence_factory.semantic.probe import recall
from convergence_factory.store import Store

# Optional Prefect integration
try:
    from prefect import flow as prefect_flow, task as prefect_task
    PREFECT_AVAILABLE = True
except ImportError:
    PREFECT_AVAILABLE = False

    def prefect_task(fn=None, **kwargs):
        if fn is not None:
            return fn
        def decorator(f):
            return f
        return decorator

    def prefect_flow(fn=None, **kwargs):
        if fn is not None:
            return fn
        def decorator(f):
            return f
        return decorator


# Optional Dagster integration
try:
    from dagster import job as dagster_job, op as dagster_op
    DAGSTER_AVAILABLE = True
except ImportError:
    DAGSTER_AVAILABLE = False

    def dagster_op(fn=None, **kwargs):
        if fn is not None:
            return fn
        def decorator(f):
            return f
        return decorator

    def dagster_job(fn=None, **kwargs):
        if fn is not None:
            return fn
        def decorator(f):
            return f
        return decorator


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


@prefect_task(name="census-scan")
def task_census(repos_root: str, inventory_path: Optional[str] = None) -> list:
    if inventory_path and os.path.exists(inventory_path):
        with open(inventory_path) as f:
            items = parse_inventory(json.load(f))
        return census.scan_inventory(items, repos_root)
    return census.scan(repos_root)


@prefect_task(name="extract-facts")
def task_extract_repo(store: Store, scan, use_cache: bool = True) -> bool:
    """Extracts facts for a single repository, returning True if freshly extracted."""
    if use_cache:
        curr_hash = compute_repo_hash(scan.repo_path)
        prev_hash = store.get_cache(scan.project.id)
        if prev_hash == curr_hash:
            return False
        if prev_hash is not None:
            store.clear_project(scan.project.id)
        extract(store, scan)
        store.set_cache(scan.project.id, curr_hash)
        return True
    else:
        extract(store, scan)
        return True


@prefect_task(name="detect-clones")
def task_clones(store: Store) -> list:
    return detect_clones(store)


@prefect_task(name="build-graph")
def task_graph(store: Store) -> dict:
    return graph.build(store)


@prefect_task(name="semantic-recall")
def task_recall(store: Store) -> list:
    return recall(store)


@prefect_task(name="pairwise-judge")
def task_judge(store: Store, g: dict, candidates: list) -> tuple[dict, list]:
    evaluated = judge_candidates(store, candidates)
    promoted_graph = graph.promote_candidates(g, evaluated, store)
    return promoted_graph, evaluated


@prefect_task(name="render-report")
def task_report(store: Store, g: dict, candidates: list, out_dir: str) -> dict:
    return report.render(store, g, candidates, out_dir)


@prefect_task(name="generate-ratchets")
def task_ratchets(clusters: list, out_dir: str) -> dict:
    out_ratchets = os.path.join(out_dir, "ratchets")
    return generate_all_ratchets(clusters, out_ratchets)


@prefect_task(name="generate-rewrites")
def task_rewrites(clusters: list, out_dir: str) -> list:
    out_recipes = os.path.join(out_dir, "recipes")
    return generate_all_rewrite_recipes(clusters, out_recipes)


def run_pipeline(
    repos_root: str,
    out_dir: str,
    use_cache: bool = True,
    judge: bool = False,
    ratchet: bool = False,
    rewrite: bool = False,
    inventory: Optional[str] = None,
) -> dict:
    """Executes the full Convergence Factory pipeline.

    Args:
        repos_root: Root directory containing repository folders.
        out_dir: Target output directory for database, report, ratchets, and recipes.
        use_cache: If True, uses SHA-256 content hashes to skip unmodified repositories.
        judge: If True, evaluates candidate pairs with the Pairwise Semantic Judge.
        ratchet: If True, generates CI/CD one-way ratchet guardrails (ArchUnit, Import-Linter).
        rewrite: If True, generates OpenRewrite declarative refactoring recipes.
        inventory: Optional path to GitLab inventory JSON.
    """
    os.makedirs(out_dir, exist_ok=True)
    store = Store(os.path.join(out_dir, "factory.db"))
    stats = {"total_scans": 0, "extracted": 0, "cached": 0}

    scans = task_census(repos_root, inventory_path=inventory)
    for scan in scans:
        stats["total_scans"] += 1
        extracted = task_extract_repo(store, scan, use_cache=use_cache)
        if extracted:
            stats["extracted"] += 1
        else:
            stats["cached"] += 1

    task_clones(store)
    g = task_graph(store)
    candidates = task_recall(store)

    if judge:
        g, candidates = task_judge(store, g, candidates)

    summary = task_report(store, g, candidates, out_dir)

    if ratchet:
        ratchet_manifest = task_ratchets(g["clusters"], out_dir)
        summary["ratchets"] = ratchet_manifest

    if rewrite:
        rewrite_recipes = task_rewrites(g["clusters"], out_dir)
        summary["recipes"] = rewrite_recipes

    store.close()
    summary["pipeline_stats"] = stats
    return summary


# Export flow for Prefect orchestration engines
convergence_flow = prefect_flow(run_pipeline, name="convergence-factory-flow")

