"""M1.3 — lang-node (JavaScript / TypeScript).

Parses JS/TS into a real AST with tree-sitter and walks call expressions to
extract wiring: kafkajs producers/consumers (the cross-language signal that lets
a Node service join a Java/Python Kafka cluster), outbound HTTP calls, npm
dependencies, and an internal-import coupling graph. Falls back to regex when the
grammar is unavailable, so the factory still runs.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Set, Tuple

from convergence_factory.core.schema import (Dependency, FactBundle, Gap, IntegrationFact,
                      Module, ModuleMetric, Provenance)
from .base import LanguagePlugin, read, register, walk_files

_NODE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_HTTP_CALL_RE = re.compile(
    r'''(?:fetch|axios\.(?:get|post|put|delete|patch)|http\.(?:get|request))\s*\(\s*['"]([^'"]+)['"]''')
_KAFKA_TOPIC_RE = re.compile(r'''\btopics?\s*:\s*(\[[^\]]*\]|['"][^'"]+['"]|[A-Za-z_$][\w$]*)''')
_SEND_RE = re.compile(r'\.(?:send|produce)\s*\(')

try:                                    # real AST backend
    import tree_sitter_javascript as _tsj
    from tree_sitter import Language, Parser
    _JS = Parser(Language(_tsj.language()))
    _TS_JS = True
except Exception:                       # pragma: no cover
    _TS_JS = False


def _excluded(path: str) -> bool:
    return "/node_modules/" in path or "/dist/" in path or "/.git/" in path


def _strlit(node) -> Optional[str]:
    if node is None or node.type != "string":
        return None
    t = node.text.decode("utf8", "ignore")
    return t[1:-1] if len(t) >= 2 and t[0] in "\"'`" else t


_IMPORT_RE = re.compile(r'''(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))''')


def _coupling(repo_path: str) -> float:
    """Internal import graph density across local JS/TS modules."""
    files = [f for f in walk_files(repo_path, _NODE_EXTS) if not _excluded(f)]
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



def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(n.named_children)


class NodePlugin(LanguagePlugin):
    name = "lang-node"
    lang = "javascript"
    backend = "tree-sitter" if _TS_JS else "regex"

    def detect(self, repo_path: str) -> Optional[dict]:
        has_pkg = os.path.exists(os.path.join(repo_path, "package.json"))
        node_files = [f for f in walk_files(repo_path, _NODE_EXTS) if not _excluded(f)]
        if not has_pkg and not node_files:
            return None
        claims = ["javascript", "typescript"] if any(
            f.endswith((".ts", ".tsx")) for f in node_files) else ["javascript"]
        return {"claims": claims, "build": "npm" if has_pkg else "none",
                "score": len(node_files) + (20 if has_pkg else 0)}

    def modules(self, repo_path: str, project_id: str) -> List[Module]:
        name = project_id
        pkg = os.path.join(repo_path, "package.json")
        if os.path.exists(pkg):
            try:
                name = json.loads(read(pkg)).get("name", project_id)
            except Exception:
                pass
        return [Module(id=f"{project_id}:node", project_id=project_id, path=repo_path,
                       name=name, kind="service", lang="javascript",
                       build_system="npm" if os.path.exists(pkg) else "")]

    def facts(self, module: Module, repo_path: str) -> FactBundle:
        bundle = FactBundle(module=module, source_ref=repo_path)
        pkg = os.path.join(repo_path, "package.json")
        pkg_deps: Set[str] = set()
        if os.path.exists(pkg):
            try:
                data = json.loads(read(pkg))
                for scope, tier_scope in (("dependencies", "runtime"), ("devDependencies", "test")):
                    for name, ver in data.get(scope, {}).items():
                        pkg_deps.add(name)
                        bundle.dependencies.append(Dependency(
                            module_id=module.id, purl=f"pkg:npm/{name}@{str(ver).lstrip('^~>=')}",
                            scope=tier_scope, tier="HIGH"))
            except Exception:
                pass

        files = [f for f in walk_files(repo_path, _NODE_EXTS) if not _excluded(f)]
        has_kafka_pkg = "kafkajs" in pkg_deps
        import_edges: Set[Tuple[str, str]] = set()
        file_stems = {os.path.splitext(os.path.relpath(f, repo_path))[0].replace("\\", "/"): f
                      for f in files}

        for f in files:
            rel = os.path.relpath(f, repo_path)
            src = read(f)
            has_kafka = has_kafka_pkg or ("kafkajs" in src)
            if _TS_JS:
                self._facts_ast(src, rel, module.id, has_kafka, bundle,
                                src_stem=os.path.splitext(rel)[0].replace("\\", "/"),
                                file_stems=file_stems, import_edges=import_edges, repo_path=repo_path)
            else:
                self._facts_regex(src, rel, module.id, has_kafka, bundle)

        n = len(files)
        coupling = round(len(import_edges) / (n * (n - 1)), 3) if n > 1 else 0.0
        bundle.metrics.append(ModuleMetric(module_id=module.id, name="coupling", value=coupling))
        return bundle

    # --- AST backend ---
    def _facts_ast(self, src, rel, mid, has_kafka, bundle, src_stem, file_stems,
                   import_edges, repo_path):
        root = _JS.parse(src.encode("utf8")).root_node
        consts: Dict[str, str] = {}
        for n in _walk(root):
            if n.type == "variable_declarator":
                name = n.child_by_field_name("name")
                val = n.child_by_field_name("value")
                if name and val is not None and val.type == "string":
                    consts[name.text.decode()] = _strlit(val)
            elif n.type in ("import_statement",):
                srcnode = n.child_by_field_name("source")
                self._maybe_import_edge(_strlit(srcnode), rel, src_stem, file_stems,
                                        import_edges, repo_path)

        for n in _walk(root):
            if n.type != "call_expression":
                continue
            fn = n.child_by_field_name("function")
            args = n.child_by_field_name("arguments")
            if fn is None or args is None:
                continue
            callee = fn.text.decode("utf8", "ignore")
            first = args.named_children[0] if args.named_children else None
            line = n.start_point[0] + 1
            prov = Provenance(file=rel, line=line, snippet=src.splitlines()[line - 1].strip()
                              if line <= len(src.splitlines()) else "")
            # require("./x") coupling
            if callee == "require" and first is not None:
                self._maybe_import_edge(_strlit(first), rel, src_stem, file_stems,
                                        import_edges, repo_path)
            # kafkajs producer/consumer
            elif has_kafka and (callee.endswith(".send") or callee.endswith(".produce")):
                for topic, tier in self._topics(first, consts):
                    self._emit_topic(bundle, mid, "PRODUCES", topic, tier, prov)
            elif has_kafka and callee.endswith(".subscribe"):
                for topic, tier in self._topics(first, consts):
                    self._emit_topic(bundle, mid, "CONSUMES", topic, tier, prov)
            # HTTP calls
            elif callee == "fetch" or re.search(r'(?:axios|http|client|api)\.(?:get|post|put|delete|patch|request)$', callee):
                url = _strlit(first)
                if url:
                    bundle.integration.append(IntegrationFact(
                        module_id=mid, direction="CALLS", resource_type="HTTP_ENDPOINT",
                        resource_id=url, tier="HIGH", provenance=prov))

    def _topics(self, arg_obj, consts) -> List[Tuple[str, str]]:
        """Pull topic/topics values out of a kafkajs call's first-arg object."""
        out: List[Tuple[str, str]] = []
        if arg_obj is None or arg_obj.type != "object":
            return out
        for pair in arg_obj.named_children:
            if pair.type != "pair":
                continue
            key = pair.child_by_field_name("key")
            val = pair.child_by_field_name("value")
            if key is None or val is None or key.text.decode() not in ("topic", "topics"):
                continue
            for node in ([val] if val.type != "array" else val.named_children):
                lit = _strlit(node)
                if lit is not None:
                    out.append((lit, "HIGH"))
                elif node.type == "identifier":
                    name = node.text.decode()
                    if name in consts:
                        out.append((consts[name], "HIGH"))
        return out

    def _emit_topic(self, bundle, mid, direction, topic, tier, prov):
        bundle.integration.append(IntegrationFact(
            module_id=mid, direction=direction, resource_type="KAFKA_TOPIC",
            resource_id=topic, tier=tier, provenance=prov))

    @staticmethod
    def _maybe_import_edge(spec, rel, src_stem, file_stems, import_edges, repo_path):
        if not spec or not spec.startswith("."):
            return
        target = os.path.normpath(os.path.join(os.path.dirname(rel), spec)).replace("\\", "/")
        if target in file_stems:
            import_edges.add((src_stem, target))

    # --- regex fallback ---
    def _facts_regex(self, src, rel, mid, has_kafka, bundle):
        lines = src.splitlines()
        for i, line in enumerate(lines, 1):
            prov = Provenance(file=rel, line=i, snippet=line.strip())
            for m in _HTTP_CALL_RE.finditer(line):
                bundle.integration.append(IntegrationFact(
                    module_id=mid, direction="CALLS", resource_type="HTTP_ENDPOINT",
                    resource_id=m.group(1), tier="HIGH", provenance=prov))
            if has_kafka:
                direction = "CONSUMES" if ".subscribe" in line else (
                    "PRODUCES" if _SEND_RE.search(line) else None)
                if direction:
                    for tm in _KAFKA_TOPIC_RE.finditer(line):
                        for topic in re.findall(r'''['"]([^'"]+)['"]''', tm.group(1)):
                            bundle.integration.append(IntegrationFact(
                                module_id=mid, direction=direction, resource_type="KAFKA_TOPIC",
                                resource_id=topic, tier="HIGH", provenance=prov))


register(NodePlugin())
