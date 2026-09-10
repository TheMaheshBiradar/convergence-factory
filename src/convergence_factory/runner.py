"""M0.2 (execution half) — the plugin runner.

For each project the census found, pick the primary plugin (highest detect
score), ask it for modules and facts, validate every fact against the schema,
and write the valid ones to the store. Invalid facts are skipped with a warning
so one bad plugin never kills the pipeline.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

from .logger import LOGGER
from .schema import (validate_api, validate_dependency, validate_integration,
                     SchemaError)
from .store import Store


@dataclass
class ProjectScan:
    project: object      # schema.Project
    repo_path: str
    primary: object      # LanguagePlugin instance
    plugins: List[object] = field(default_factory=list)


def extract(store: Store, scan: ProjectScan, verbose: bool = False) -> dict:
    t0 = time.time()
    active_plugins = scan.plugins if getattr(scan, "plugins", None) else [scan.primary]
    plugin_names = ", ".join(p.name for p in active_plugins)
    plugin_label = f"plugin '{plugin_names}'" if len(active_plugins) == 1 else f"plugin(s) '{plugin_names}'"
    LOGGER.info(
        "Extracting project '%s' -> assigned %s (path: %s)",
        scan.project.id, plugin_label, scan.repo_path
    )
    store.add_project(scan.project)
    stats = {"integration": 0, "deps": 0, "gaps": 0, "skipped": 0, "modules": 0}
    for plugin in active_plugins:
        modules = plugin.modules(scan.repo_path, scan.project.id)
        LOGGER.debug("  Project '%s' [%s] discovered %d module(s)", scan.project.id, plugin.name, len(modules))
        for module in modules:
            store.add_module(module)
            stats["modules"] += 1
            t_mod = time.time()
            bundle = plugin.facts(module, scan.repo_path)
            LOGGER.debug(
                "  Module '%s' processed by '%s' in %.3fs (raw facts: %d)",
                module.id, plugin.name, time.time() - t_mod, len(bundle.integration)
            )

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
        if bundle.metrics:
            store.add_metrics(bundle.metrics)
    elapsed = time.time() - t0
    finish_label = f"plugin '{plugin_names}'" if len(active_plugins) == 1 else f"plugin(s) '{plugin_names}'"
    LOGGER.info(
        "Finished extraction: project '%s' -> %s in %.3fs (modules=%d, facts=%d, deps=%d, gaps=%d)",
        scan.project.id, finish_label, elapsed, stats["modules"], stats["integration"], stats["deps"], stats["gaps"]
    )
    return stats
