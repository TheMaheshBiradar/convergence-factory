"""M1.3 — lang-node (JavaScript / TypeScript).

Extracts npm/yarn dependencies from package.json, analyzes internal JS/TS
relative import coupling, and identifies HTTP endpoint/client wiring.
Zero third-party dependencies — parses package.json and uses regex AST scans.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Set

from ..schema import (Dependency, FactBundle, Gap, IntegrationFact, Module,
                      ModuleMetric, Provenance)
from .base import LanguagePlugin, read, register, walk_files

_NODE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_IMPORT_RE = re.compile(r'''(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))''')
_HTTP_CALL_RE = re.compile(r'''(?:fetch|axios\.(?:get|post|put|delete)|http\.(?:get|request))\s*\(\s*['"]([^'"]+)['"]''')


def _coupling(repo_path: str) -> float:
    """Internal import graph density across local JS/TS modules."""
    files = [f for f in walk_files(repo_path, _NODE_EXTS)
             if "/node_modules/" not in f and "/dist/" not in f and "/.git/" not in f]
    n = len(files)
    if n <= 1:
        return 0.0

    file_stems = {}
    for f in files:
        rel = os.path.relpath(f, repo_path).replace("\\", "/")
        stem = os.path.splitext(rel)[0]
        file_stems[stem] = rel

    edges: Set[tuple[str, str]] = set()
    for f in files:
        src_rel = os.path.relpath(f, repo_path).replace("\\", "/")
        src_dir = os.path.dirname(src_rel)
        text = read(f)
        for m in _IMPORT_RE.finditer(text):
            target = m.group(1) or m.group(2)
            if not target.startswith("."):
                continue
            norm_target = os.path.normpath(os.path.join(src_dir, target)).replace("\\", "/")
            if norm_target in file_stems:
                edges.add((src_rel, file_stems[norm_target]))

    max_edges = n * (n - 1)
    return round(len(edges) / max_edges, 3) if max_edges > 0 else 0.0


@register
class NodePlugin(LanguagePlugin):
    name = "lang-node"
    lang = "javascript"

    def detect(self, repo_path: str) -> dict | None:
        has_pkg = os.path.exists(os.path.join(repo_path, "package.json"))
        node_files = [f for f in walk_files(repo_path, _NODE_EXTS) if "/node_modules/" not in f]
        count = len(node_files)
        if not has_pkg and count == 0:
            return None
        return {
            "claims": ["javascript", "typescript"] if any(f.endswith((".ts", ".tsx")) for f in node_files) else ["javascript"],
            "build": "npm" if has_pkg else "none",
            "score": count + (20 if has_pkg else 0),
        }

    def modules(self, repo_path: str, project_id: str) -> List[Module]:
        mod_name = project_id
        pkg_json = os.path.join(repo_path, "package.json")
        if os.path.exists(pkg_json):
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    mod_name = data.get("name", project_id)
            except Exception:
                pass
        return [Module(
            id=f"{project_id}:node",
            project_id=project_id,
            path=repo_path,
            name=mod_name,
            kind="service",
            lang="javascript",
            build_system="npm" if os.path.exists(pkg_json) else "",
        )]

    def facts(self, module: Module, repo_path: str) -> FactBundle:
        deps: List[Dependency] = []
        integration: List[IntegrationFact] = []
        gaps: List[Gap] = []

        pkg_json = os.path.join(repo_path, "package.json")
        if os.path.exists(pkg_json):
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for pkg, ver in data.get("dependencies", {}).items():
                        ver_clean = str(ver).lstrip("^~>=")
                        deps.append(Dependency(module_id=module.id, purl=f"pkg:npm/{pkg}@{ver_clean}", scope="runtime", tier="HIGH"))
                    for pkg, ver in data.get("devDependencies", {}).items():
                        ver_clean = str(ver).lstrip("^~>=")
                        deps.append(Dependency(module_id=module.id, purl=f"pkg:npm/{pkg}@{ver_clean}", scope="test", tier="HIGH"))
            except Exception:
                pass

        files = [f for f in walk_files(repo_path, _NODE_EXTS)
                 if "/node_modules/" not in f and "/dist/" not in f]
        for f in files:
            rel = os.path.relpath(f, repo_path)
            text = read(f)
            lines = text.splitlines()
            for line_idx, line in enumerate(lines, 1):
                for m in _HTTP_CALL_RE.finditer(line):
                    url = m.group(1)
                    integration.append(IntegrationFact(
                        module_id=module.id,
                        direction="CALLS",
                        resource_type="HTTP_ENDPOINT",
                        resource_id=url,
                        tier="HIGH",
                        provenance=Provenance(file=rel, line=line_idx, snippet=line.strip()),
                    ))

        coupling_val = _coupling(repo_path)
        metrics = [ModuleMetric(module_id=module.id, name="coupling", value=coupling_val)]

        return FactBundle(
            module=module,
            integration=integration,
            dependencies=deps,
            metrics=metrics,
            gaps=gaps,
            source_ref=repo_path,
        )
