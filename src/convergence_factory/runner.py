"""M0.2 (execution half) — the plugin runner.

For each project the census found, pick the primary plugin (highest detect
score), ask it for modules and facts, validate every fact against the schema,
and write the valid ones to the store. Invalid facts are skipped with a warning
so one bad plugin never kills the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import (validate_api, validate_dependency, validate_integration,
                     SchemaError)
from .store import Store


@dataclass
class ProjectScan:
    project: object      # schema.Project
    repo_path: str
    primary: object      # LanguagePlugin instance


def extract(store: Store, scan: ProjectScan, verbose: bool = False) -> dict:
    store.add_project(scan.project)
    stats = {"integration": 0, "deps": 0, "gaps": 0, "skipped": 0, "modules": 0}
    for module in scan.primary.modules(scan.repo_path, scan.project.id):
        store.add_module(module)
        stats["modules"] += 1
        bundle = scan.primary.facts(module, scan.repo_path)

        good_int = []
        for f in bundle.integration:
            try:
                validate_integration(f)
                good_int.append(f)
            except SchemaError as e:
                stats["skipped"] += 1
                if verbose:
                    print(f"  ! skipped integration fact in {module.id}: {e}")
        store.add_integration(good_int)
        stats["integration"] += len(good_int)

        good_deps = []
        for d in bundle.dependencies:
            try:
                validate_dependency(d)
                good_deps.append(d)
            except SchemaError:
                stats["skipped"] += 1
        store.add_dependencies(good_deps)
        stats["deps"] += len(good_deps)

        for a in bundle.api:
            try:
                validate_api(a)
            except SchemaError:
                bundle.api.remove(a)
        store.add_api(bundle.api)

        store.add_gaps(bundle.gaps)
        stats["gaps"] += len(bundle.gaps)
        if bundle.summaries:
            store.add_summaries(bundle.summaries)
    return stats
