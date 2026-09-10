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

import traceback

from .core.errors import ERROR_TRACKER
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
        try:
            modules = plugin.modules(scan.repo_path, scan.project.id)
        except Exception as e:
            ERROR_TRACKER.record(
                phase=f"probe:integration:{plugin.name}",
                source=scan.repo_path,
                error_type=type(e).__name__,
                message=f"Plugin '{plugin.name}' failed to discover modules: {e}",
                details=traceback.format_exc(),
                remediation="Check project build files and language configuration."
            )
            modules = []

        LOGGER.debug("  Project '%s' [%s] discovered %d module(s)", scan.project.id, plugin.name, len(modules))
        for module in modules:
            store.add_module(module)
            stats["modules"] += 1
            t_mod = time.time()
            try:
                bundle = plugin.facts(module, scan.repo_path)
            except Exception as e:
                ERROR_TRACKER.record(
                    phase=f"probe:integration:{plugin.name}",
                    source=f"{module.id} ({scan.repo_path})",
                    error_type=type(e).__name__,
                    message=f"Plugin '{plugin.name}' failed to extract facts: {e}",
                    details=traceback.format_exc(),
                    remediation="Check file encodings, AST syntax, or parser compatibility."
                )
                continue

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
                    ERROR_TRACKER.record_warning(
                        phase="schema:validation",
                        source=f"{module.id} ({f.resource_type}:{f.resource_id})",
                        warning_type="InvalidIntegrationFact",
                        message=str(e),
                        remediation="Verify resource URI format and valid direction values."
                    )
                    if verbose:
                        print(f"  ! skipped integration fact in {module.id}: {e}")
            store.add_integration(good_int)
            stats["integration"] += len(good_int)

            good_deps = []
            for d in bundle.dependencies:
                try:
                    validate_dependency(d)
                    good_deps.append(d)
                except SchemaError as e:
                    stats["skipped"] += 1
                    ERROR_TRACKER.record_warning(
                        phase="schema:validation",
                        source=f"{module.id} ({d.purl})",
                        warning_type="InvalidDependency",
                        message=str(e)
                    )
            store.add_dependencies(good_deps)
            stats["deps"] += len(good_deps)

            for a in bundle.api:
                try:
                    validate_api(a)
                except SchemaError as e:
                    bundle.api.remove(a)
                    ERROR_TRACKER.record_warning(
                        phase="schema:validation",
                        source=f"{module.id} ({a.path})",
                        warning_type="InvalidApiSurface",
                        message=str(e)
                    )
            store.add_api(bundle.api)

            store.add_gaps(bundle.gaps)
            stats["gaps"] += len(bundle.gaps)
            for g in bundle.gaps:
                g_file = g.provenance.file if getattr(g, "provenance", None) else getattr(g, "file", "unknown")
                g_expr = getattr(g, "expression", "") or getattr(g, "target_expr", "")
                g_kind = getattr(g, "kind", "resource")
                g_reason = g.provenance.resolver_notes if getattr(g, "provenance", None) else getattr(g, "reason", "")
                msg = f"Unresolved {g_kind} expression '{g_expr}'"
                if g_reason:
                    msg += f": {g_reason}"
                ERROR_TRACKER.record_warning(
                    phase="probe:gaps",
                    source=f"{module.id} ({g_file})",
                    warning_type="UnresolvedDynamicReference",
                    message=msg,
                    remediation="Define explicit property or environment constant in application configs."
                )

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
