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

from ..resolver import ResolutionContext, resolve
from ..schema import (Dependency, FactBundle, Gap, IntegrationFact, Module,
                      Provenance)
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
        return bundle

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
        req = os.path.join(repo_path, "requirements.txt")
        out = []
        if os.path.exists(req):
            for line in read(req).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg = re.split(r"[=<>!~ ]", line, 1)[0]
                    out.append(Dependency(module_id=module_id,
                                          purl=f"pkg:pypi/{pkg}", scope="runtime"))
        return out
