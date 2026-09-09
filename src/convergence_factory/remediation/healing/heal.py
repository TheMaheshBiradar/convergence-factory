"""Automated Self-Healing Engine.

Executes closed-loop convergence remediation:
1. Identifies convergence clusters (RETIRE / STANDARDIZE).
2. Applies automated source refactoring across member repository files.
3. Installs one-way CI guardrails (ArchUnit, Import-Linter, dependency-cruiser) into the repos.
4. Re-scans the estate and verifies that the duplication opportunity score is reduced to zero.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from convergence_factory import census, graph
from convergence_factory.remediation.ratchets.ratchet import (generate_archunit_rule, generate_dependency_cruiser_rule,
                      generate_import_linter_contract)
from convergence_factory.runner import extract
from convergence_factory.core.store import Store


@dataclass
class HealingAction:
    cluster_id: str
    play: str
    target_resource: str
    canonical_resource: str
    files_modified: List[str] = field(default_factory=list)
    ratchets_installed: List[str] = field(default_factory=list)
    recovered_opportunity: float = 0.0


@dataclass
class HealingReport:
    actions: List[HealingAction] = field(default_factory=list)
    total_recovered: float = 0.0
    initial_clusters: int = 0
    remaining_clusters: int = 0
    all_healed: bool = False


def _replace_in_file(filepath: str, old_str: str, new_str: str) -> bool:
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if old_str in content:
            new_content = content.replace(old_str, new_str)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True
    except Exception:
        pass
    return False


def heal_cluster(cluster: Dict[str, Any], store: Store, base_dir: str, canonical_prefix: str = "canonical.") -> HealingAction:
    cid = cluster.get("id", "cluster")
    play = cluster.get("play", "STANDARDIZE")
    opp = float(cluster.get("opportunity", 0.0))
    members = cluster.get("members", [])
    shared = cluster.get("shared", [])

    action = HealingAction(
        cluster_id=cid,
        play=play,
        target_resource="",
        canonical_resource="",
        recovered_opportunity=opp,
    )

    if not shared or not members:
        return action

    # Primary resource to heal
    res = shared[0]
    if isinstance(res, (tuple, list)):
        old_res_id = res[1] if len(res) > 1 else str(res[0])
    else:
        old_res_id = res.get("resource_id", "")
    new_res_id = f"{canonical_prefix}{old_res_id}" if not old_res_id.startswith(canonical_prefix) else old_res_id
    action.target_resource = old_res_id
    action.canonical_resource = new_res_id

    # Find file locations from facts store
    mod_ids = [m.split(":")[0] for m in members]
    primary_mod = mod_ids[0]
    secondary_mods = set(mod_ids[1:])
    facts = [f for f in store.integration_facts() if f.resource_id == old_res_id]

    import re
    for f in facts:
        # Resolve repo path
        mod_prefix = f.module_id.split(":")[0]
        repo_cand = os.path.join(base_dir, mod_prefix)
        file_path = os.path.join(repo_cand, f.provenance.file) if os.path.exists(os.path.join(repo_cand, f.provenance.file)) else f.provenance.file

        if os.path.exists(file_path):
            if mod_prefix == primary_mod:
                # Primary member standardizes to canonical resource ID
                if _replace_in_file(file_path, old_res_id, new_res_id):
                    action.files_modified.append(file_path)
            elif mod_prefix in secondary_mods:
                # Secondary member decommissions duplicate publisher and delegates to primary
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as rf:
                        content = rf.read()
                    # Decommission the produce/send call in secondary duplicate
                    decom_content = re.sub(
                        r'([ \t]*.*(?:\.produce|\.send)\s*\(.*?\).*)',
                        r'# [CONVERGED: retired duplicate publisher; delegated to ' + primary_mod + r']\n# \1',
                        content
                    )
                    if decom_content != content:
                        with open(file_path, "w", encoding="utf-8") as wf:
                            wf.write(decom_content)
                        action.files_modified.append(file_path)
                    elif _replace_in_file(file_path, old_res_id, f"decommissioned.{old_res_id}"):
                        action.files_modified.append(file_path)
                except Exception:
                    pass

    # Install Ratchets directly into affected repos
    for member in members:
        mod_name = member.split(":")[0]
        repo_dir = os.path.join(base_dir, mod_name)
        if not os.path.isdir(repo_dir):
            continue

        # Python repo -> install .importlinter contract
        if os.path.exists(os.path.join(repo_dir, "requirements.txt")) or any(f.endswith(".py") for f in os.listdir(repo_dir)):
            linter_path = os.path.join(repo_dir, ".importlinter")
            with open(linter_path, "w", encoding="utf-8") as lf:
                lf.write(generate_import_linter_contract(cluster))
            action.ratchets_installed.append(linter_path)

        # Java repo -> install ArchUnit test
        pom_path = os.path.join(repo_dir, "pom.xml")
        if os.path.exists(pom_path):
            test_dir = os.path.join(repo_dir, "src", "test", "java", "com", "acme", "ratchet")
            os.makedirs(test_dir, exist_ok=True)
            test_file = os.path.join(test_dir, "ConvergenceRatchetTest.java")
            with open(test_file, "w", encoding="utf-8") as jf:
                jf.write(generate_archunit_rule(cluster))
            action.ratchets_installed.append(test_file)

        # Node.js repo -> install dependency-cruiser rule
        pkg_path = os.path.join(repo_dir, "package.json")
        if os.path.exists(pkg_path):
            dc_path = os.path.join(repo_dir, ".dependency-cruiser.json")
            with open(dc_path, "w", encoding="utf-8") as dcf:
                dcf.write(json.dumps(generate_dependency_cruiser_rule(cluster), indent=2))
            action.ratchets_installed.append(dc_path)

    return action


def run_self_healing(estate_dir: str, cluster_id: Optional[str] = None) -> HealingReport:
    """Runs the self-healing cycle over an estate, refactoring duplicates and installing guardrails."""
    # 1. Initial scan & graph
    db_path = os.path.join(estate_dir, ".heal_tmp.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    store = Store(db_path)
    scans = census.scan(estate_dir)
    for s in scans:
        extract(store, s)
    g = graph.build(store)

    initial_clusters = g["clusters"]
    report = HealingReport(initial_clusters=len(initial_clusters))

    clusters_to_heal = [c for c in initial_clusters if not cluster_id or c.get("id") == cluster_id]

    for c in clusters_to_heal:
        act = heal_cluster(c, store, estate_dir)
        report.actions.append(act)
        report.total_recovered += act.recovered_opportunity

    store.close()
    if os.path.exists(db_path):
        os.remove(db_path)

    # 2. Verification re-scan
    verify_store = Store(":memory:")
    verify_scans = census.scan(estate_dir)
    for s in verify_scans:
        extract(verify_store, s)
    verify_g = graph.build(verify_store)
    report.remaining_clusters = len(verify_g["clusters"])
    report.all_healed = (report.remaining_clusters == 0)
    verify_store.close()

    return report
