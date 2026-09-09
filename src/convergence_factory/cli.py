"""CLI entry point. `python -m convergence_factory <command>`.

Commands:
  run     [root] [--out DIR]   full pipeline -> redundancy map (default: fixtures)
  census  [root]               list the project manifest only
  eval    [root] [--expected]  run the calibration eval
"""
from __future__ import annotations

import argparse
import os

from . import census as census_mod
from . import graph as graph_mod
from . import ratchet as ratchet_mod
from . import report as report_mod
from .clone_probe import detect_clones
from .connectors.gitlab import parse_inventory
import json
from .eval import format_report
from .eval import run as eval_run
from .executors import rewrite as rewrite_mod
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
    for s in scans:
        st = extract(store, s)
        for k in totals:
            totals[k] += st[k]
    print(f"  modules={totals['modules']} integration={totals['integration']} "
          f"deps={totals['deps']} gaps={totals['gaps']} skipped={totals['skipped']}")

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
        print("[judge] running pairwise semantic judge")
        candidates = judge_candidates(store, candidates)
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
    root = args.root or DEFAULT_REPOS
    if getattr(args, "inventory", None):
        with open(args.inventory) as f:
            items = parse_inventory(json.load(f))
        scans = census_mod.scan_inventory(items, root)
    else:
        scans = census_mod.scan(root)
    for s in scans:
        p = s.project
        print(f"{p.id:<18} langs={','.join(p.langs):<14} loc={p.loc:<6} "
              f"owner={p.owner_team:<12} primary={s.primary.name}")
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
    evaluated = judge_candidates(store, candidates)
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="convergence_factory")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="full pipeline -> redundancy map")
    r.add_argument("root", nargs="?", default=None)
    r.add_argument("--out", default=DEFAULT_OUT)
    r.add_argument("--judge", action="store_true", help="run pairwise judge to confirm and promote candidates")
    r.add_argument("--ratchet", action="store_true", help="generate one-way governance ratchets")
    r.add_argument("--rewrite", action="store_true", help="generate OpenRewrite refactoring recipes")
    r.add_argument("--inventory", default=None, help="path to GitLab inventory JSON")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("census", help="project manifest only")
    c.add_argument("root", nargs="?", default=None)
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
    j.set_defaults(func=cmd_judge)

    rw = sub.add_parser("rewrite", help="generate OpenRewrite refactoring recipes from clusters")
    rw.add_argument("root", nargs="?", default=None)
    rw.add_argument("--out", default=DEFAULT_OUT)
    rw.set_defaults(func=cmd_rewrite)

    hl = sub.add_parser("heal", help="automatically refactor duplicate clusters and lock CI ratchets")
    hl.add_argument("root", nargs="?", default=None)
    hl.add_argument("--cluster", default=None, help="target specific cluster ID to heal")
    hl.set_defaults(func=cmd_heal)

    args = p.parse_args(argv)
    return args.func(args)

