"""M0.5 — the calibration eval.

Runs each plugin against a repo whose integration facts have been hand-labelled
(fixtures/expected/*.json) and reports precision / recall plus the resolution
rate. This is what lets you trust — or distrust — any number Phase 1 produces,
and it is where you set the per-plugin "done when" bar.

Expected file shape:
    {"repo": "py-orders",
     "integration": [["PRODUCES","KAFKA_TOPIC","order.created"], ...]}
"""
from __future__ import annotations

import json
import os
from typing import List

from .census import scan


def _extract_set(scans, repo_name):
    for s in scans:
        if s.project.id == repo_name:
            facts, gaps = set(), 0
            for m in s.primary.modules(s.repo_path, s.project.id):
                b = s.primary.facts(m, s.repo_path)
                for f in b.integration:
                    facts.add((f.direction, f.resource_type, f.resource_id))
                gaps += len(b.gaps)
            return facts, gaps
    return set(), 0


def run(repos_root: str, expected_dir: str) -> List[dict]:
    scans = scan(repos_root)
    results = []
    for name in sorted(os.listdir(expected_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(expected_dir, name)) as fh:
            spec = json.load(fh)
        expected = {tuple(x) for x in spec["integration"]}
        got, gaps = _extract_set(scans, spec["repo"])
        tp = len(expected & got)
        precision = tp / len(got) if got else 0.0
        recall = tp / len(expected) if expected else 1.0
        resolved = len(got)
        res_rate = resolved / (resolved + gaps) if (resolved + gaps) else 1.0
        results.append({
            "repo": spec["repo"], "precision": round(precision, 2),
            "recall": round(recall, 2), "resolution": round(res_rate, 2),
            "expected": len(expected), "got": len(got),
            "missed": sorted(expected - got), "extra": sorted(got - expected)})
    return results


def format_report(results: List[dict]) -> str:
    lines = [f"{'repo':<16}{'prec':>6}{'recall':>8}{'resol':>7}  {'exp/got':>8}"]
    lines.append("-" * 52)
    for r in results:
        lines.append(f"{r['repo']:<16}{r['precision']:>6}{r['recall']:>8}"
                     f"{r['resolution']:>7}  {r['expected']}/{r['got']:>3}")
        for m in r["missed"]:
            lines.append(f"    MISSED  {m}")
        for e in r["extra"]:
            lines.append(f"    EXTRA   {e}")
    return "\n".join(lines)
