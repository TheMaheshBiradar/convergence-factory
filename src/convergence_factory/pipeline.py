"""The single orchestrator — the six-stage Convergence Factory pipeline.

    1 INGEST      repos/inventory -> ProjectScans
    2 EXTRACT     module plugins + registered FACT probes -> facts in the store
    3 CAPABILITIES facts -> Capability[] (the analytical spine; no blob)
    4 FINDINGS     capabilities with >=2 members, scored + played, per dimension
    5 VIEWS        capability matrix (primary) + bipartite graph + REPORT probes
    6 REMEDIATE    (opt-in) ratchets + rewrite recipes from findings

`cli` and `pipelines/flow.py` should both call `run()` — one sequence, one place.
Run directly:  python -m convergence_factory.pipeline <repos_root> --out .factory
"""
from __future__ import annotations

import argparse
import os
import time
from typing import List, Tuple

from .core.capability import build_capabilities, summarize
from .core.interfaces import PipelineConfig
from .core.store import Store
from .exporters import matrix as matrix_view
from .exporters.graphify import export_capability_graph
from .probes.registry import FACT_PROBES, REPORT_PROBES, fact_probe, report_probe
from .runner import extract

# --- register the portfolio probes (central registration; probe modules untouched) ---

@fact_probe("api")
def _probe_api(store, ctx):
    from .probes.contracts import extract_api
    return {"endpoints": extract_api(store)}


@fact_probe("clones")
def _probe_clones(store, ctx):
    from .probes.clones.clone_probe import detect_clones
    return {"clones": len(detect_clones(store))}


@report_probe("bom")
def _probe_bom(store, ctx):
    from .probes.bom import run_bom
    b = run_bom(store, ctx["out"])
    return {"sboms": len(b["sbom_files"]), "shared_deps": len(b["shared_dependencies"])}


@report_probe("schema")
def _probe_schema(store, ctx):
    from .probes.schema import analyze_schema
    s = analyze_schema(store)
    return {"tables": len(s["tables"]), "fk_edges": len(s["fk_edges"]),
            "orphan_tables": len(s["orphan_tables"])}


@report_probe("tech")
def _probe_tech(store, ctx):
    import json
    from .core.tech import analyze_tech, summarize as tech_summary
    tech = analyze_tech(store)
    site = os.path.join(ctx["out"], "site")
    os.makedirs(site, exist_ok=True)
    with open(os.path.join(site, "tech.json"), "w", encoding="utf-8") as fh:
        json.dump(tech, fh, indent=2)
    return tech_summary(tech)


def _semantic_pairs(store, judge=None, embedder=None) -> List[Tuple[str, str, str]]:
    """Recall candidates, judge them, return confirmed pairs.

    `judge` / `embedder` are injected (Dependency Inversion): pass a RestJudge for
    real LLM confirmation, or leave None for the conservative heuristic default.
    """
    from .probes.semantic.probe import recall
    from .probes.semantic.judge import judge_candidates
    try:
        candidates = recall(store, embedder) if embedder is not None else recall(store)
    except TypeError:
        candidates = recall(store)
    judged = judge_candidates(store, candidates, judge=judge)
    return [(c["a"], c["b"], c.get("tier", "LOW"))
            for c in judged if c.get("confirmed")]


def run(config: PipelineConfig, judge=None, embedder=None, store_factory=None) -> dict:
    """Execute the six-stage pipeline against a typed config.

    store_factory / judge / embedder are injected dependencies (DIP); defaults
    give the standard SQLite store and the conservative heuristic judge.
    """
    # importing census pulls in the plugin packages, registering every probe
    from .ingestion import census as census_mod

    out = config.out
    os.makedirs(out, exist_ok=True)
    db_path = os.path.join(out, "factory.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    store = (store_factory or Store)(db_path)
    ctx = {"out": out}
    timings = {}

    def stage(name):
        def log(msg=""):
            print(f"[{name}] {msg}".rstrip())
        return log

    # 1 INGEST
    t = time.time()
    log = stage("ingest")
    if config.inventory:
        import json
        from .ingestion.connectors.gitlab import parse_inventory
        with open(config.inventory) as fh:
            scans = census_mod.scan_inventory(parse_inventory(json.load(fh)), config.root)
    else:
        scans = census_mod.scan(config.root)
    log(f"projects={len(scans)}")
    timings["ingest"] = time.time() - t

    # 2 EXTRACT (module plugins + FACT probes)
    t = time.time()
    log = stage("extract")
    totals = {"integration": 0, "deps": 0, "gaps": 0, "modules": 0}
    for s in scans:
        st = extract(store, s)
        for k in totals:
            totals[k] += st.get(k, 0)
    log(f"modules={totals['modules']} integration={totals['integration']} "
        f"deps={totals['deps']} gaps={totals['gaps']}")
    for name, fn in FACT_PROBES:
        res = fn(store, ctx)
        log(f"probe:{name} {res}")
    timings["extract"] = time.time() - t

    # 3 CAPABILITIES
    t = time.time()
    log = stage("capabilities")
    pairs = _semantic_pairs(store, judge=judge, embedder=embedder) if config.semantic else []
    caps = build_capabilities(store, semantic_pairs=pairs,
                              functional_max_size=config.functional_max_size)
    summ = summarize(caps)
    log(f"shared_capabilities={summ['total']} by_dimension={summ['by_dimension']} "
        f"semantic_confirmed={len(pairs)}")
    timings["capabilities"] = time.time() - t

    # 4 FINDINGS
    log = stage("findings")
    by_play = {}
    for c in caps:
        by_play[c.play] = by_play.get(c.play, 0) + 1
    top = caps[:10]
    log(f"by_play={by_play}")
    for c in top:
        log(f"  [{c.play:<11}] {c.dimension:<11} opp={c.opportunity:<5} "
            f"tier={c.tier:<4} {c.label[:48]} :: {len(c.module_ids)} modules")

    # 5 VIEWS
    t = time.time()
    log = stage("views")
    # convergence plan — the "unify into this" target, rendered into the view
    import json as _json
    from .core.convergence import build as build_convergence
    convergence = build_convergence(store, caps)
    m = matrix_view.render(caps, out, max_cols=config.matrix_max_cols,
                           convergence=convergence)
    gpath = os.path.join(out, "site", "capability-graph.json")
    export_capability_graph(caps, gpath)
    with open(os.path.join(out, "site", "convergence.json"), "w", encoding="utf-8") as fh:
        _json.dump(convergence, fh, indent=2)
    log(f"matrix={m['matrix_html']} graph={gpath} convergence={convergence['rollup']}")

    report_results = {}
    for name, fn in REPORT_PROBES:
        report_results[name] = fn(store, ctx)
        log(f"probe:{name} {report_results[name]}")
    timings["views"] = time.time() - t

    # 6 REMEDIATE (opt-in)
    if config.remediate:
        log = stage("remediate")
        clusters = [{"members": c.module_ids, "owners": c.owners, "play": c.play,
                     "label": c.label, "shared": [(c.dimension, c.id)],
                     "tier": c.tier, "opportunity": c.opportunity,
                     "coupling": c.coupling, "edges": []} for c in caps]
        from .remediation.ratchets.ratchet import generate_all_ratchets
        from .remediation.refactoring.rewrite import generate_all_rewrite_recipes
        r = generate_all_ratchets(clusters, os.path.join(out, "ratchets"))
        rec = generate_all_rewrite_recipes(clusters, os.path.join(out, "recipes"))
        log(f"ratchets={sum(len(v) for v in r.values())} recipes={len(rec)}")

    store.close()

    print("\n=== CONVERGENCE PLAN (unify into this) ===")
    for p in convergence["capability_plans"][:10]:
        frm = ", ".join(s.split(":")[0] for s in p["migrate_from"]) or "-"
        print(f"  [{p['play']:<11}] {p['dimension']:<10} {p['label'][:34]:<34} "
              f"-> canonical: {p['canonical'].split(':')[0]:<18} (migrate: {frm})")
    for tp in convergence["tech_plans"][:6]:
        print(f"  [STANDARDIZE] tech       {tp['category']:<34} -> standard: {tp['canonical']} "
              f"(migrate: {', '.join(tp['migrate_from_libs']) or '-'})")
    print(f"  rollup: {convergence['rollup']}")

    print("\n=== SUMMARY ===")
    print(f"projects={len(scans)} modules={totals['modules']} "
          f"capabilities={summ['total']} plays={by_play}")
    print("timings(s): " + " ".join(f"{k}={v:.2f}" for k, v in timings.items()))
    print(f"matrix : {m['matrix_html']}")
    return {"projects": len(scans), "modules": totals["modules"],
            "capabilities": summ["total"], "by_dimension": summ["by_dimension"],
            "by_play": by_play, "convergence": convergence["rollup"],
            "timings": timings, **m}


def main(argv=None):
    p = argparse.ArgumentParser(prog="convergence_factory.pipeline")
    p.add_argument("root", nargs="?", default=None, help="directory of repos")
    p.add_argument("--out", default=None)
    p.add_argument("--no-semantic", action="store_true")
    p.add_argument("--remediate", action="store_true")
    p.add_argument("--inventory", default=None)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = args.root or os.path.join(here, "fixtures", "repos")
    out = args.out or os.path.join(here, ".factory")
    cfg = PipelineConfig(root=root, out=out, semantic=not args.no_semantic,
                         remediate=args.remediate, inventory=args.inventory,
                         verbose=args.verbose)
    run(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
