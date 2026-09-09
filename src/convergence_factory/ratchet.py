"""One-Way Ratchet Generator.

Generates CI/CD governance rules (ArchUnit, Import-Linter, dependency-cruiser)
from convergence clusters to freeze architectural debt and block new
references to duplicate or retired modules.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List


def generate_archunit_rule(cluster: dict) -> str:
    """Generates an ArchUnit Java test snippet preventing dependencies on retired members."""
    shared_desc = ", ".join(f"{rtype}: {rid}" for rtype, rid in cluster.get("shared", []))
    members = [m.split(":")[0] for m in cluster.get("members", [])]
    rule_name = f"no_calls_to_{members[0].replace('-', '_')}"
    pkg_pattern = f"..{members[0].replace('-', '.')}.."

    return f"""package com.acme.governance;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

/**
 * Convergence Ratchet: Play {cluster.get('play')}
 * Capability: {cluster.get('label')} ({shared_desc})
 * Target Members: {', '.join(members)}
 */
@AnalyzeClasses(packages = "com.acme")
public class ConvergenceRatchetTest {{

    @ArchTest
    public static final ArchRule {rule_name} =
        noClasses().should().dependOnClassesThat()
            .resideInAPackage("{pkg_pattern}")
            .because("Module is marked for {cluster.get('play')} in the Convergence Redundancy Map");
}}
"""


def generate_import_linter_contract(cluster: dict) -> str:
    """Generates an Import-Linter contract to forbid imports of deprecated modules."""
    members = [m.split(":")[0] for m in cluster.get("members", [])]
    target_mod = members[0].replace("-", "_")
    return f"""[importlinter]
root_package = my_app

[importlinter:contract:convergence-{target_mod}]
name = Convergence Ratchet: Block {cluster.get('play')} ({target_mod})
type = forbidden
source_modules =
    my_app
forbidden_modules =
    {target_mod}
"""


def generate_dependency_cruiser_rule(cluster: dict) -> dict:
    """Generates a dependency-cruiser rule forbidding imports from the retired module."""
    members = [m.split(":")[0] for m in cluster.get("members", [])]
    target = members[0]
    return {
        "name": f"convergence-no-{target}",
        "severity": "error",
        "comment": f"Convergence Ratchet: {cluster.get('play')} on capability {cluster.get('label')}",
        "from": {},
        "to": {
            "path": f".*{target}.*"
        }
    }


def generate_all_ratchets(clusters: List[dict], out_dir: str) -> Dict[str, List[str]]:
    """Generates governance rule files for all actionable convergence clusters."""
    os.makedirs(out_dir, exist_ok=True)
    archunit_dir = os.path.join(out_dir, "archunit")
    linter_dir = os.path.join(out_dir, "import_linter")
    dep_dir = os.path.join(out_dir, "dependency_cruiser")

    for d in [archunit_dir, linter_dir, dep_dir]:
        os.makedirs(d, exist_ok=True)

    generated: Dict[str, List[str]] = {"archunit": [], "import_linter": [], "dependency_cruiser": []}
    dep_rules = []

    for i, c in enumerate(clusters):
        play = c.get("play", "")
        if play not in ("RETIRE", "STANDARDIZE"):
            continue

        members = [m.split(":")[0] for m in c.get("members", [])]
        name = members[0]

        # 1. ArchUnit
        java_code = generate_archunit_rule(c)
        java_path = os.path.join(archunit_dir, f"ConvergenceRatchet_{name.replace('-', '_')}_Test.java")
        with open(java_path, "w") as f:
            f.write(java_code)
        generated["archunit"].append(java_path)

        # 2. Import-Linter
        linter_cfg = generate_import_linter_contract(c)
        linter_path = os.path.join(linter_dir, f".importlinter_{name}")
        with open(linter_path, "w") as f:
            f.write(linter_cfg)
        generated["import_linter"].append(linter_path)

        # 3. dependency-cruiser
        dep_rules.append(generate_dependency_cruiser_rule(c))

    if dep_rules:
        dep_path = os.path.join(dep_dir, "dependency-cruiser-ratchet.json")
        with open(dep_path, "w") as f:
            json.dump({"forbidden": dep_rules}, f, indent=2)
        generated["dependency_cruiser"].append(dep_path)

    return generated
