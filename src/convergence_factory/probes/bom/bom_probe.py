"""BOM probe — the dependency / bill-of-materials layer.

Turns the dependency facts the language plugins already extracted into (a) a
CycloneDX SBOM per project and (b) a shared-dependency report: libraries/
frameworks used across modules owned by different teams — the signal for stack
standardization. Production would swap the manifest parsing for Syft and enrich
with license/CVE data; the normalized output is the same.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Dict, List

from convergence_factory.core.store import Store


def _dependencies(store: Store):
    return store.db.execute(
        "SELECT module_id, purl, scope, tier FROM dependencies").fetchall()


def _dep_name(purl: str) -> str:
    return purl.split("/")[-1].split("@")[0]


def build_sbom(store: Store, out_dir: str) -> List[str]:
    """Write one CycloneDX (1.5) SBOM per project. Returns the file paths."""
    os.makedirs(out_dir, exist_ok=True)
    mod_project = {m.id: m.project_id for m in store.modules()}
    by_project: Dict[str, list] = defaultdict(list)
    for r in _dependencies(store):
        by_project[mod_project.get(r["module_id"], r["module_id"])].append(r)

    files = []
    for pid, deps in sorted(by_project.items()):
        components = [{
            "type": "library",
            "name": _dep_name(d["purl"]),
            "purl": d["purl"],
            "scope": "required" if d["scope"] == "runtime" else "optional",
        } for d in deps]
        doc = {
            "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "metadata": {"component": {"type": "application", "name": pid}},
            "components": components,
        }
        path = os.path.join(out_dir, f"{pid}.cdx.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        files.append(path)
    return files


def shared_dependency_report(store: Store, min_owners: int = 2) -> List[dict]:
    """Dependencies used by >=2 modules across >=min_owners teams — the stack-
    standardization candidates."""
    mod_owner = store.module_owner()
    modules: Dict[str, set] = defaultdict(set)
    owners: Dict[str, set] = defaultdict(set)
    for r in _dependencies(store):
        name = _dep_name(r["purl"])
        modules[name].add(r["module_id"])
        owners[name].add(mod_owner.get(r["module_id"], "unknown"))

    out = []
    for name, mods in modules.items():
        if len(mods) >= 2 and len(owners[name]) >= min_owners:
            out.append({"dependency": name, "modules": sorted(mods),
                        "owners": sorted(owners[name]), "count": len(mods)})
    out.sort(key=lambda x: (-x["count"], x["dependency"]))
    return out


def run_bom(store: Store, out_dir: str) -> dict:
    sbom_files = build_sbom(store, os.path.join(out_dir, "sbom"))
    shared = shared_dependency_report(store)
    return {"sbom_files": sbom_files, "shared_dependencies": shared}
