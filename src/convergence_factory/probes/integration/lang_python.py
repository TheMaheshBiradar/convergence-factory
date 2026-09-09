"""M1.2 — lang-python.

Uses the stdlib `ast` (no third-party parser needed) to extract a module's
wiring: Kafka producers/consumers, embedded SQL (handed to lang-sql), and
outbound HTTP calls, plus dependencies. Topic/URL expressions go through the
shared resolver, so a literal is HIGH and a config/env-sourced value is MED.
"""
from __future__ import annotations

import ast
import os
import re
from typing import List

from convergence_factory.core.resolver import ResolutionContext, resolve
from convergence_factory.core.schema import (Dependency, FactBundle, Gap, IntegrationFact, Module,
                      ModuleMetric, Provenance)
from .base import LanguagePlugin, read, register, walk_files
from .lang_sql import extract_sql_lineage

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "request"}
_KAFKA_HINTS = ("kafka", "confluent_kafka", "aiokafka")


def _looks_like_sql(s: str) -> bool:
    head = s.lstrip()[:12].upper()
    return head.startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "WITH "))


class _Visitor(ast.NodeVisitor):
    def __init__(self, ctx, rel, src_lines):
        self.ctx = ctx
        self.rel = rel
        self.lines = src_lines
        self.integration: List[IntegrationFact] = []
        self.gaps: List[Gap] = []
        self.has_kafka = False

    def _prov(self, node):
        ln = getattr(node, "lineno", 0)
        snippet = self.lines[ln - 1].strip() if 0 < ln <= len(self.lines) else ""
        return Provenance(file=self.rel, line=ln, snippet=snippet)

    def _emit(self, node, direction, rtype, expr, kind):
        res = resolve(expr, self.ctx)
        prov = self._prov(node)
        if res.resolved:
            prov.resolver_notes = res.notes
            self.integration.append(IntegrationFact(
                module_id="", direction=direction, resource_type=rtype,
                resource_id=res.value, tier=res.tier, provenance=prov))
        else:
            self.gaps.append(Gap(module_id="", kind=rtype, expression=expr,
                                 provenance=prov))

    def visit_Call(self, node):
        func = node.func
        # attribute call: obj.method(...)
        if isinstance(func, ast.Attribute):
            attr = func.attr
            arg0 = node.args[0] if node.args else None
            # Kafka produce
            if attr in ("send", "produce") and self.has_kafka and arg0 is not None:
                self._emit(node, "PRODUCES", "KAFKA_TOPIC", ast.unparse(arg0), "kafka")
            # DB execute with embedded SQL
            elif attr in ("execute", "executemany") and arg0 is not None:
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str) \
                        and _looks_like_sql(arg0.value):
                    for direction, table in extract_sql_lineage(arg0.value):
                        self.integration.append(IntegrationFact(
                            module_id="", direction=direction,
                            resource_type="SQL_TABLE", resource_id=table,
                            tier="HIGH", provenance=self._prov(node)))
            # HTTP call
            elif attr in _HTTP_METHODS and arg0 is not None and self._http_obj(func.value):
                self._emit(node, "CALLS", "HTTP_ENDPOINT", ast.unparse(arg0), "http")
        # bare call: KafkaConsumer("topic", ...) / subscribe([...])
        elif isinstance(func, ast.Name) and func.id == "KafkaConsumer":
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    self._emit(node, "CONSUMES", "KAFKA_TOPIC", ast.unparse(a), "kafka")
        self.generic_visit(node)

    @staticmethod
    def _http_obj(value) -> bool:
        try:
            return any(h in ast.unparse(value) for h in ("requests", "httpx", "session", "client"))
        except Exception:
            return False


def _build_context(tree: ast.AST) -> ResolutionContext:
    ctx = ResolutionContext()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            val = node.value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                ctx.constants[name] = val.value                     # literal -> HIGH
            elif isinstance(val, ast.Call):                          # os.getenv("K","def")
                try:
                    src = ast.unparse(val.func)
                except Exception:
                    src = ""
                if src in ("os.getenv", "os.environ.get") and val.args:
                    default = val.args[1].value if len(val.args) > 1 \
                        and isinstance(val.args[1], ast.Constant) else None
                    if default is not None:
                        ctx.config[name] = default                   # config default -> MED
    return ctx


@register
class PythonPlugin(LanguagePlugin):
    name = "lang-python"
    lang = "python"

    def detect(self, repo_path):
        files = walk_files(repo_path, (".py",))
        if not files:
            return None
        build = "unknown"
        if os.path.exists(os.path.join(repo_path, "pyproject.toml")):
            build = "pyproject"
        elif os.path.exists(os.path.join(repo_path, "requirements.txt")):
            build = "pip"
        return {"claims": ["python"], "build": build, "score": len(files)}

    def modules(self, repo_path, project_id):
        name = os.path.basename(repo_path.rstrip("/"))
        return [Module(id=f"{project_id}:py", project_id=project_id,
                       path=repo_path, name=name, kind="service",
                       lang="python", build_system=self.detect(repo_path)["build"])]

    def facts(self, module, repo_path):
        bundle = FactBundle(module=module, source_ref=repo_path)
        for path in walk_files(repo_path, (".py",)):
            src = read(path)
            rel = os.path.relpath(path, repo_path)
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            imports = self._imports(tree)
            ctx = _build_context(tree)
            v = _Visitor(ctx, rel, src.splitlines())
            v.has_kafka = any(any(h in i for h in _KAFKA_HINTS) for i in imports)
            v.visit(tree)
            for f in v.integration:
                f.module_id = module.id
            for g in v.gaps:
                g.module_id = module.id
            bundle.integration.extend(v.integration)
            bundle.gaps.extend(v.gaps)
        bundle.dependencies.extend(self._deps(module.id, repo_path))
        bundle.metrics.append(ModuleMetric(
            module_id=module.id, name="coupling",
            value=self._coupling(repo_path)))
        return bundle

    @staticmethod
    def _coupling(repo_path) -> float:
        """Internal-import-graph density in [0,1]: how much the repo's own
        modules depend on each other. A proxy for how entangled a capability is
        with its host — the convergence score's `coupling` factor.

        Dependency-free (stdlib ast). Grimp / Import-Linter are the production
        upgrade (cycle detection, layered contracts, the one-way ratchet).
        """
        files = walk_files(repo_path, (".py",))
        names = {}
        for p in files:
            rel = os.path.relpath(p, repo_path)
            name = rel[:-3].replace(os.sep, ".")
            names[p] = name[:-9] if name.endswith(".__init__") else name
        local = set(names.values())
        n = len(local)
        if n < 2:
            return 0.0

        def resolve_local(cand):
            if cand in local:
                return cand
            cur = cand
            while "." in cur:
                cur, _ = cur.rsplit(".", 1)
                if cur in local:
                    return cur
            return None

        edges = set()  # distinct (importer, target) pairs
        for p in files:
            src = names[p]
            try:
                tree = ast.parse(read(p))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                cands = []
                if isinstance(node, ast.Import):
                    cands = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    # `from pkg import b` -> try both pkg and pkg.b
                    cands = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                for cand in cands:
                    tgt = resolve_local(cand)
                    if tgt and tgt != src:
                        edges.add((src, tgt))
        # density over all possible directed edges between modules
        return round(len(edges) / (n * (n - 1)), 3)

    @staticmethod
    def _imports(tree) -> List[str]:
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
        return names

    @staticmethod
    def _deps(module_id, repo_path) -> List[Dependency]:
        pkgs = set()
        # 1. requirements*.txt
        try:
            for f in os.listdir(repo_path):
                if f.startswith("requirements") and f.endswith(".txt"):
                    for line in read(os.path.join(repo_path, f)).splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            pkg = re.split(r"[=<>!~ ]", line, 1)[0].strip()
                            if pkg:
                                pkgs.add(pkg.lower().replace("-", "_"))
        except OSError:
            pass

        # 2. pyproject.toml
        pyproj = os.path.join(repo_path, "pyproject.toml")
        if os.path.exists(pyproj):
            content = read(pyproj)
            in_deps = False
            for line in content.splitlines():
                if "dependencies" in line and "=" in line and "[" in line:
                    in_deps = True
                if in_deps:
                    for m in re.finditer(r'["\']([a-zA-Z0-9_\-\.]+)', line):
                        val = m.group(1)
                        if val not in ("dependencies", "project"):
                            pkgs.add(val.lower().replace("-", "_"))
                    if "]" in line:
                        in_deps = False

        # 3. setup.py
        setup_file = os.path.join(repo_path, "setup.py")
        if os.path.exists(setup_file):
            content = read(setup_file)
            for m in re.finditer(r'deps\[["\']([a-zA-Z0-9_\-\.]+)["\']\]', content):
                pkgs.add(m.group(1).lower().replace("-", "_"))
            for m in re.finditer(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL):
                for p in re.finditer(r'["\']([a-zA-Z0-9_\-\.]+)', m.group(1)):
                    pkgs.add(p.group(1).lower().replace("-", "_"))

        return [Dependency(module_id=module_id, purl=f"pkg:pypi/{pkg}", scope="runtime")
                for pkg in sorted(pkgs)]
