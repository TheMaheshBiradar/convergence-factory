"""CLI entry point. `python -m convergence_factory <command>`.

Commands:
  run     [root] [--out DIR]   full pipeline -> redundancy map (default: fixtures)
  census  [root]               list the project manifest only
  eval    [root] [--expected]  run the calibration eval
"""
from __future__ import annotations

import argparse
import json
import os
import time

from . import census as census_mod
from . import graph as graph_mod
from . import ratchet as ratchet_mod
from . import report as report_mod
from .clone_probe import detect_clones
from .connectors.gitlab import parse_inventory
from .eval import format_report
from .eval import run as eval_run
from .executors import rewrite as rewrite_mod
from .logger import setup_logger
from .runner import extract
from .semantic.judge import judge_candidates
from .semantic.probe import recall
from .store import Store

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
DEFAULT_REPOS = os.path.join(_REPO_ROOT, "fixtures", "repos")
DEFAULT_EXPECTED = os.path.join(_REPO_ROOT, "fixtures", "expected")
DEFAULT_OUT = os.path.join(_REPO_ROOT, ".factory")


def cmd_run(args):
    setup_logger(verbose=getattr(args, "verbose", False))
    if getattr(args, "all", False):
        args.judge = True
        args.ratchet = True
        args.rewrite = True

    root = args.root or DEFAULT_REPOS
    os.makedirs(args.out, exist_ok=True)

    db_path = os.path.join(args.out, "factory.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    store = Store(db_path)

    print(f"[census] scanning {root}")
    if getattr(args, "inventory", None):
        with open(args.inventory) as f:
            items = parse_inventory(json.load(f))
        scans = census_mod.scan_inventory(items, root)
    else:
        scans = census_mod.scan(root)
    for s in scans:
        print(f"  · {s.project.id:<16} langs={','.join(s.project.langs):<12} "
              f"owner={s.project.owner_team:<12} primary={s.primary.name}")

    print("[extract] running plugins")
    totals = {"integration": 0, "deps": 0, "gaps": 0, "skipped": 0, "modules": 0}
    t_start = time.time()
    for s in scans:
        t0 = time.time()
        st = extract(store, s, verbose=getattr(args, "verbose", False))
        elapsed = time.time() - t0
        mod_label = f"{st['modules']} module" if st['modules'] == 1 else f"{st['modules']} modules"
        print(f"  · [{s.project.id:<16}] assigned plugin: {s.primary.name:<11} "
              f"({mod_label:<9}) -> {elapsed:.2f}s [facts: {st['integration']:<2}, deps: {st['deps']:<2}]")
        for k in totals:
            totals[k] += st[k]
    total_elapsed = time.time() - t_start
    print(f"  total: modules={totals['modules']} integration={totals['integration']} "
          f"deps={totals['deps']} gaps={totals['gaps']} skipped={totals['skipped']} in {total_elapsed:.2f}s")

    print("[api] scanning API/contract surfaces (OpenAPI/proto/GraphQL)")
    from convergence_factory.probes.contracts import extract_api
    api_count = extract_api(store)
    print(f"  endpoints exposed={api_count}")

    print("[clones] detecting cross-module code clones")
    clones = detect_clones(store)
    print(f"  clones detected={len(clones)}")

    print("[graph] building similarity graph + clustering")
    g = graph_mod.build(store)
    print(f"  clusters={len(g['clusters'])} edges={len(g['edges'])}")

    print("[semantic] recall (candidates only)")
    candidates = recall(store)
    print(f"  candidate pairs={len(candidates)}")

    if getattr(args, "judge", False):
        use_llm = getattr(args, "llm", False) or bool(os.environ.get("CONVERGENCE_LLM_ENDPOINT"))
        if use_llm:
            from .semantic.judge import RestJudge
            judge_impl = RestJudge(
                endpoint=getattr(args, "llm_endpoint", None),
                model=getattr(args, "llm_model", None),
                api_key=getattr(args, "llm_api_key", None)
            )

            print(f"[judge] running pairwise semantic judge via LLM ({judge_impl.model} @ {judge_impl.endpoint})")
        else:
            judge_impl = None
            print("[judge] running pairwise semantic judge (heuristic engine)")
        candidates = judge_candidates(store, candidates, judge=judge_impl)
        confirmed = [c for c in candidates if c.get("confirmed")]
        print(f"  confirmed duplicate pairs={len(confirmed)} of {len(candidates)}")
        g = graph_mod.promote_candidates(g, candidates, store)
        print(f"  total clusters after promotion={len(g['clusters'])}")


    print("[report] rendering redundancy map")
    summary = report_mod.render(store, g, candidates, args.out)

    if getattr(args, "ratchet", False):
        print("[ratchet] generating one-way governance ratchets")
        out_ratchets = os.path.join(args.out, "ratchets")
        generated_ratchets = ratchet_mod.generate_all_ratchets(g["clusters"], out_ratchets)
        print(f"  ratchets generated: ArchUnit={len(generated_ratchets['archunit'])} "
              f"Import-Linter={len(generated_ratchets['import_linter'])} "
              f"dep-cruiser={len(generated_ratchets['dependency_cruiser'])}")

    if getattr(args, "rewrite", False):
        print("[rewrite] generating OpenRewrite refactoring recipes")
        out_recipes = os.path.join(args.out, "recipes")
        generated_recipes = rewrite_mod.generate_all_rewrite_recipes(g["clusters"], out_recipes)
        print(f"  recipes generated={len(generated_recipes)}")

    print("[bom] generating SBOMs + shared-dependency report")
    from convergence_factory.probes.bom import run_bom
    bom = run_bom(store, args.out)
    print(f"  sboms={len(bom['sbom_files'])} shared-across-teams={len(bom['shared_dependencies'])}")

    print("[schema] analyzing DB schema (FK graph + orphans)")
    from convergence_factory.probes.schema import analyze_schema
    sch = analyze_schema(store)
    print(f"  tables={len(sch['tables'])} fk_edges={len(sch['fk_edges'])} "
          f"orphan_tables={len(sch['orphan_tables'])}")

    store.close()

    print("\n=== REDUNDANCY MAP ===")
    for c in g["clusters"]:
        members = ", ".join(m.split(":")[0] for m in c["members"])
        coupling = "—" if c["coupling"] is None else c["coupling"]
        print(f"  [{c['play']:<11}] {c['label']:<34} tier={c['tier']:<4} "
              f"opp={c['opportunity']:<4} coupling={coupling!s:<5} :: {members}")
    print(f"\nresolution rate: {summary['resolution_rate']}%   "
          f"(gaps tracked: {summary['gaps']})")
    print(f"site: {summary['site']}")
    return 0


def cmd_census(args):
    setup_logger(verbose=getattr(args, "verbose", False))
    root = args.root or DEFAULT_REPOS
    root_abs = os.path.abspath(root)

    print(f"\n=== CONVERGENCE FACTORY · PROJECT CENSUS ===")
    print(f"Target Directory : {root_abs}")
    if getattr(args, "inventory", None):
        print(f"GitLab Inventory : {args.inventory}")
        with open(args.inventory) as f:
            items = parse_inventory(json.load(f))
        scans = census_mod.scan_inventory(items, root)
    else:
        scans = census_mod.scan(root)

    if not scans:
        print("\n  ⚠️  No projects detected under this path.")
        print("  Tips:")
        print("    1. Pass the absolute or relative path to your repositories folder:")
        print("       ./run.sh /path/to/your/projects --census")
        print("    2. Ensure the target subdirectories contain build manifests (pom.xml, package.json, requirements.txt, pyproject.toml)")
        print("       or source files (.java, .py, .js, .ts, .sql).")
        return 0

    print(f"\nDiscovered {len(scans)} project(s):\n")
    print(f"  {'PROJECT ID':<26} {'LANGUAGES':<14} {'LOC':<7} {'OWNER':<14} {'PRIMARY PLUGIN':<16} {'PATH'}")
    print(f"  {'-'*26} {'-'*14} {'-'*7} {'-'*14} {'-'*16} {'-'*30}")
    for s in scans:
        p = s.project
        rel = os.path.relpath(s.repo_path, root_abs)
        rel_disp = "." if rel == "." else rel
        langs_str = ",".join(p.langs)[:13]
        print(f"  {p.id:<26} {langs_str:<14} {p.loc:<7} {p.owner_team:<14} {s.primary.name:<16} {rel_disp}")

    print(f"\nTotal: {len(scans)} project(s) ready for convergence analysis.")
    print("To run convergence analysis on these projects:")
    print(f"  ./run.sh {root_abs} --all --serve\n")
    return 0


def cmd_eval(args):
    root = args.root or DEFAULT_REPOS
    results = eval_run(root, args.expected or DEFAULT_EXPECTED)
    print(format_report(results))
    worst = min((r["recall"] for r in results), default=1.0)
    print(f"\nlowest recall: {worst}")
    return 0


def cmd_ratchet(args):
    root = args.root or DEFAULT_REPOS
    os.makedirs(args.out, exist_ok=True)
    db_path = os.path.join(args.out, "factory.db")
    if not os.path.exists(db_path):
        store = Store(db_path)
        for s in census_mod.scan(root):
            extract(store, s)
    else:
        store = Store(db_path)

    g = graph_mod.build(store)
    store.close()

    out_ratchets = os.path.join(args.out, "ratchets")
    generated = ratchet_mod.generate_all_ratchets(g["clusters"], out_ratchets)
    print(f"[ratchet] Generated governance rules in {out_ratchets}")
    print(f"  · ArchUnit tests       : {len(generated['archunit'])}")
    print(f"  · Import-Linter configs: {len(generated['import_linter'])}")
    print(f"  · dep-cruiser rules    : {len(generated['dependency_cruiser'])}")
    return 0


def cmd_judge(args):
    root = args.root or DEFAULT_REPOS
    os.makedirs(args.out, exist_ok=True)
    db_path = os.path.join(args.out, "factory.db")
    store = Store(db_path)
    if not os.path.exists(db_path) or len(store.modules()) == 0:
        for s in census_mod.scan(root):
            extract(store, s)

    candidates = recall(store)
    use_llm = getattr(args, "llm", False) or bool(os.environ.get("CONVERGENCE_LLM_ENDPOINT"))
    if use_llm:
        from .semantic.judge import RestJudge
        judge_impl = RestJudge(
            endpoint=getattr(args, "llm_endpoint", None),
            model=getattr(args, "llm_model", None),
            api_key=getattr(args, "llm_api_key", None)
        )

        print(f"[judge] evaluating candidates via LLM ({judge_impl.model} @ {judge_impl.endpoint})")
    else:
        judge_impl = None
        print("[judge] evaluating candidates via heuristic engine")
    evaluated = judge_candidates(store, candidates, judge=judge_impl)
    store.close()


    print("\n=== SEMANTIC PAIRWISE JUDGE VERDICTS ===")
    for c in evaluated:
        status = "CONFIRMED" if c.get("confirmed") else "REFUTED"
        print(f"  [{status:<9}] {c['a']:<22} <-> {c['b']:<22} "
              f"conf={c.get('confidence', 0.0):<4} play={c.get('play', 'LEAVE'):<11}")
        print(f"               Reason: {c.get('reason', '')}")
    return 0


def cmd_rewrite(args):
    root = args.root or DEFAULT_REPOS
    os.makedirs(args.out, exist_ok=True)
    db_path = os.path.join(args.out, "factory.db")
    store = Store(db_path)
    if not os.path.exists(db_path) or len(store.modules()) == 0:
        for s in census_mod.scan(root):
            extract(store, s)

    g = graph_mod.build(store)
    store.close()

    out_recipes = os.path.join(args.out, "recipes")
    generated = rewrite_mod.generate_all_rewrite_recipes(g["clusters"], out_recipes)
    print(f"[rewrite] Generated OpenRewrite convergence recipes in {out_recipes}")
    for f in generated:
        print(f"  · {os.path.basename(f)}")
    return 0


def cmd_heal(args):
    root = args.root or DEFAULT_REPOS
    from .heal import run_self_healing
    print(f"[self-heal] running automated convergence healing on {root}")
    report = run_self_healing(root, cluster_id=args.cluster)
    print("\n=== SELF-HEALING EXECUTION REPORT ===")
    print(f"  Initial duplicate clusters : {report.initial_clusters}")
    print(f"  Remediated actions         : {len(report.actions)}")
    print(f"  Total opportunity recovered: {report.total_recovered}")
    for act in report.actions:
        print(f"  · [{act.play}] {act.target_resource} -> {act.canonical_resource}")
        print(f"      Modified files  : {len(act.files_modified)}")
        print(f"      Ratchets locked : {len(act.ratchets_installed)}")
    print(f"  Remaining clusters         : {report.remaining_clusters}")
    print(f"  All clusters healed        : {'YES' if report.all_healed else 'PARTIAL'}")
    return 0


def cmd_serve(args):
    import http.server
    import socketserver
    import webbrowser

    site_dir = os.path.join(args.out, "site")
    if not os.path.exists(site_dir):
        print(f"[serve] No report found in {site_dir}. Run `convergence-factory run` first.")
        return 1

    port = args.port

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=site_dir, **kw)

    try:
        with socketserver.TCPServer(("", port), Handler) as httpd:
            url = f"http://localhost:{port}"
            print(f"[serve] Serving Redundancy Map at {url} (Ctrl+C to stop)")
            if not getattr(args, "no_browser", False):
                webbrowser.open(url)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] Server stopped.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="convergence_factory")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="full pipeline -> redundancy map")
    r.add_argument("root", nargs="?", default=None)
    r.add_argument("--out", default=DEFAULT_OUT)
    r.add_argument("--all", action="store_true", help="run everything: pairwise judge, CI/CD ratchets, and rewrite recipes")
    r.add_argument("--judge", action="store_true", help="run pairwise judge to confirm and promote candidates")

    r.add_argument("--llm", action="store_true", help="use live LLM server for judge instead of heuristic engine")
    r.add_argument("--llm-endpoint", default=None, help="LLM REST endpoint (default: http://localhost:11434/api/generate or $CONVERGENCE_LLM_ENDPOINT)")
    r.add_argument("--llm-model", default=None, help="LLM model name (default: llama3 or $CONVERGENCE_LLM_MODEL)")
    r.add_argument("--llm-api-key", "--llm-key", dest="llm_api_key", default=None, help="LLM API key or auth token (or $CONVERGENCE_LLM_KEY / $OPENAI_API_KEY)")
    r.add_argument("--ratchet", action="store_true", help="generate one-way governance ratchets")
    r.add_argument("--rewrite", action="store_true", help="generate OpenRewrite refactoring recipes")
    r.add_argument("-v", "--verbose", action="store_true", help="enable verbose debug logging")
    r.add_argument("--inventory", default=None, help="path to GitLab inventory JSON")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("census", help="project manifest only")
    c.add_argument("root", nargs="?", default=None)
    c.add_argument("-v", "--verbose", action="store_true", help="enable verbose debug logging")
    c.add_argument("--inventory", default=None, help="path to GitLab inventory JSON")
    c.set_defaults(func=cmd_census)

    e = sub.add_parser("eval", help="calibration eval")
    e.add_argument("root", nargs="?", default=None)
    e.add_argument("--expected", default=None)
    e.set_defaults(func=cmd_eval)

    rt = sub.add_parser("ratchet", help="generate one-way governance ratchets from clusters")
    rt.add_argument("root", nargs="?", default=None)
    rt.add_argument("--out", default=DEFAULT_OUT)
    rt.set_defaults(func=cmd_ratchet)

    j = sub.add_parser("judge", help="evaluate semantic candidates via pairwise judge")
    j.add_argument("root", nargs="?", default=None)
    j.add_argument("--out", default=DEFAULT_OUT)
    j.add_argument("--llm", action="store_true", help="use live LLM server for judge")
    j.add_argument("--llm-endpoint", default=None, help="LLM REST endpoint (default: http://localhost:11434/api/generate or $CONVERGENCE_LLM_ENDPOINT)")
    j.add_argument("--llm-model", default=None, help="LLM model name (default: llama3 or $CONVERGENCE_LLM_MODEL)")
    j.add_argument("--llm-api-key", "--llm-key", dest="llm_api_key", default=None, help="LLM API key or auth token (or $CONVERGENCE_LLM_KEY / $OPENAI_API_KEY)")
    j.set_defaults(func=cmd_judge)



    rw = sub.add_parser("rewrite", help="generate OpenRewrite refactoring recipes from clusters")
    rw.add_argument("root", nargs="?", default=None)
    rw.add_argument("--out", default=DEFAULT_OUT)
    rw.set_defaults(func=cmd_rewrite)

    hl = sub.add_parser("heal", help="automatically refactor duplicate clusters and lock CI ratchets")
    hl.add_argument("root", nargs="?", default=None)
    hl.add_argument("--cluster", default=None, help="target specific cluster ID to heal")
    hl.set_defaults(func=cmd_heal)

    srv = sub.add_parser("serve", help="serve the interactive redundancy map in the browser")
    srv.add_argument("--out", default=DEFAULT_OUT)
    srv.add_argument("--port", type=int, default=8080, help="port to serve on (default: 8080)")
    srv.add_argument("--no-browser", action="store_true", help="do not auto-open the browser")
    srv.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    return args.func(args)

