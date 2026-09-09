"""M1.3 — lang-java.

Parses Java into a real AST with tree-sitter (in-process, no JVM) and walks
method invocations, annotations and field declarations to extract wiring:
Spring Kafka producers/listeners, JPA @Query & native SQL (handed to lang-sql),
RestTemplate calls. Topic values go through the shared resolver, so a literal
constant is HIGH and a @Value config placeholder resolved via application.yml is
MED — the same duplicate, honest about confidence.

Backends, in order of fidelity:
  1. tree-sitter AST      (used here — accurate, structural)
  2. regex fallback       (when tree_sitter_java is absent — degrades gracefully)
  3. JVM sidecar          (JavaParser/Spoon — the max-fidelity production option,
                           emits this same normalized JSON)
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from convergence_factory.core.resolver import (Resolution, ResolutionContext, load_properties,
                        load_simple_yaml, resolve)
from convergence_factory.core.schema import (Dependency, FactBundle, Gap, IntegrationFact, Module,
                      ModuleMetric, Provenance)
from .base import LanguagePlugin, read, register, walk_files
from .lang_sql import extract_sql_lineage

try:                                    # backend 1: real AST
    import tree_sitter_java as _tsj
    from tree_sitter import Language, Parser
    _PARSER = Parser(Language(_tsj.language()))
    _TS = True
except Exception:                       # pragma: no cover
    _TS = False

_HTTP_CALLS = {"getForObject", "postForObject", "getForEntity", "exchange"}
_DEP = re.compile(r'<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>', re.S)


# --- tree-sitter helpers ---------------------------------------------------

def _txt(n) -> str:
    return n.text.decode("utf8", "ignore")


def _strlit(n) -> str:
    t = _txt(n)
    return t[1:-1] if len(t) >= 2 and t[0] in "\"'" else t


def _descend(n):
    stack = [n]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(x.named_children)


def _string_literals(n):
    return [d for d in _descend(n) if d.type == "string_literal"]


def _first_arg(mi):
    args = mi.child_by_field_name("arguments")
    if args and args.named_child_count:
        return args.named_children[0]
    return None


def _prov(rel, node) -> Provenance:
    return Provenance(file=rel, line=node.start_point[0] + 1, snippet=_txt(node)[:80])


class JavaPlugin(LanguagePlugin):
    name = "lang-java"
    lang = "java"
    backend = "tree-sitter" if _TS else "regex"

    def detect(self, repo_path):
        files = walk_files(repo_path, (".java",))
        if not files:
            return None
        build = "maven" if os.path.exists(os.path.join(repo_path, "pom.xml")) else "gradle"
        return {"claims": ["java"], "build": build, "score": len(files)}

    def modules(self, repo_path, project_id):
        name = os.path.basename(repo_path.rstrip("/"))
        return [Module(id=f"{project_id}:java", project_id=project_id,
                       path=repo_path, name=name, kind="service",
                       lang="java", build_system=self.detect(repo_path)["build"])]

    def _config(self, repo_path) -> Dict[str, str]:
        cfg: Dict[str, str] = {}
        for path in walk_files(repo_path, (".yml", ".yaml")):
            cfg.update(load_simple_yaml(read(path)))
        for path in walk_files(repo_path, (".properties",)):
            cfg.update(load_properties(read(path)))
        return cfg

    def facts(self, module, repo_path):
        bundle = FactBundle(module=module, source_ref=repo_path)
        config = self._config(repo_path)
        for path in walk_files(repo_path, (".java",)):
            src = read(path)
            rel = os.path.relpath(path, repo_path)
            if _TS:
                self._facts_ast(src, rel, module.id, config, bundle)
            else:
                self._facts_regex(src, rel, module.id, config, bundle)
        bundle.dependencies.extend(self._deps(module.id, repo_path))
        bundle.metrics.append(ModuleMetric(
            module_id=module.id, name="coupling",
            value=self._coupling(repo_path)))
        return bundle

    # --- backend 1: tree-sitter AST ---------------------------------------

    def _facts_ast(self, src, rel, mid, config, bundle):
        root = _PARSER.parse(src.encode("utf8")).root_node
        ctx = ResolutionContext(config=config)
        consts, vfields = self._collect(root, ctx)
        for n in _descend(root):
            if n.type == "method_invocation":
                self._visit_call(n, mid, rel, consts, vfields, bundle)
            elif n.type in ("annotation", "marker_annotation"):
                self._visit_annotation(n, mid, rel, bundle)

    def _collect(self, root, ctx):
        """Pass 1: gather String constants (HIGH) and @Value fields (config->MED)."""
        consts: Dict[str, str] = {}
        vfields: Dict[str, tuple] = {}
        for n in _descend(root):
            if n.type != "field_declaration":
                continue
            tnode = n.child_by_field_name("type")
            is_string = tnode is not None and _txt(tnode) == "String"
            placeholder = None
            for ann in _descend(n):
                if ann.type in ("annotation", "marker_annotation"):
                    name = ann.child_by_field_name("name")
                    if name and _txt(name) == "Value":
                        lits = _string_literals(ann)
                        if lits:
                            placeholder = _strlit(lits[0])
            for d in n.named_children:
                if d.type != "variable_declarator":
                    continue
                nm = d.child_by_field_name("name")
                name = _txt(nm) if nm else None
                if not name:
                    continue
                if placeholder is not None:
                    res = resolve(placeholder, ctx)
                    vfields[name] = (res.value, res.tier, res.notes)
                else:
                    val = d.child_by_field_name("value")
                    if val is None:
                        lits = _string_literals(d)
                        val = lits[0] if lits else None
                    if is_string and val is not None and val.type == "string_literal":
                        consts[name] = _strlit(val)
        return consts, vfields

    def _visit_call(self, mi, mid, rel, consts, vfields, bundle):
        name = mi.child_by_field_name("name")
        nm = _txt(name) if name else ""
        if nm == "send":
            self._emit_topic(_first_arg(mi), "PRODUCES", mi, mid, rel, consts, vfields, bundle)
        elif nm in _HTTP_CALLS:
            arg = _first_arg(mi)
            if arg is not None and arg.type == "string_literal":
                bundle.integration.append(IntegrationFact(
                    module_id=mid, direction="CALLS", resource_type="HTTP_ENDPOINT",
                    resource_id=_strlit(arg), tier="HIGH", provenance=_prov(rel, mi)))
        elif nm == "createNativeQuery":
            arg = _first_arg(mi)
            if arg is not None and arg.type == "string_literal":
                self._emit_sql(_strlit(arg), mid, rel, mi, bundle)

    def _visit_annotation(self, ann, mid, rel, bundle):
        name = ann.child_by_field_name("name")
        nm = _txt(name) if name else ""
        if nm == "KafkaListener":
            pairs = [c for c in _descend(ann) if c.type == "element_value_pair"]
            targets = []
            if pairs:
                for pr in pairs:
                    key = pr.child_by_field_name("key")
                    if key and _txt(key) == "topics":
                        targets += [_strlit(l) for l in _string_literals(pr)]
            else:
                targets += [_strlit(l) for l in _string_literals(ann)]
            for topic in targets:
                bundle.integration.append(IntegrationFact(
                    module_id=mid, direction="CONSUMES", resource_type="KAFKA_TOPIC",
                    resource_id=topic, tier="HIGH", provenance=_prov(rel, ann)))
        elif nm == "Query":
            for lit in _string_literals(ann):
                self._emit_sql(_strlit(lit), mid, rel, ann, bundle)

    def _emit_topic(self, arg, direction, node, mid, rel, consts, vfields, bundle):
        if arg is None:
            return
        if arg.type == "string_literal":
            value, tier, notes = _strlit(arg), "HIGH", "literal at call site"
        else:
            ident = _txt(arg)
            if ident in consts:
                value, tier, notes = consts[ident], "HIGH", "local constant"
            elif ident in vfields:
                value, tier, notes = vfields[ident]
            else:
                bundle.gaps.append(Gap(module_id=mid, kind="KAFKA_TOPIC",
                                       expression=_txt(arg), provenance=_prov(rel, node)))
                return
        if value is None:
            bundle.gaps.append(Gap(module_id=mid, kind="KAFKA_TOPIC",
                                   expression=_txt(arg), provenance=_prov(rel, node)))
            return
        prov = _prov(rel, node)
        prov.resolver_notes = notes
        bundle.integration.append(IntegrationFact(
            module_id=mid, direction=direction, resource_type="KAFKA_TOPIC",
            resource_id=value, tier=tier, provenance=prov))

    def _emit_sql(self, sql, mid, rel, node, bundle):
        for direction, table in extract_sql_lineage(sql):
            bundle.integration.append(IntegrationFact(
                module_id=mid, direction=direction, resource_type="SQL_TABLE",
                resource_id=table, tier="HIGH", provenance=_prov(rel, node)))

    # --- backend 2: regex fallback (grammar absent) -----------------------

    _SEND = re.compile(r'\.send\(\s*([A-Za-z_][\w\.]*|"[^"]+")')
    _VALUE_FIELD = re.compile(r'@Value\(\s*"([^"]+)"\s*\)\s*(?:private|public|protected)?\s*(?:final\s+)?String\s+(\w+)')
    _CONST = re.compile(r'static\s+final\s+String\s+(\w+)\s*=\s*"([^"]+)"')
    _QUERY = re.compile(r'@Query\(\s*(?:value\s*=\s*)?"([^"]+)"', re.S)
    _NATIVE = re.compile(r'createNativeQuery\(\s*"([^"]+)"', re.S)
    _REST = re.compile(r'\.(?:getForObject|postForObject|getForEntity|exchange)\(\s*"([^"]+)"')

    def _facts_regex(self, src, rel, mid, config, bundle):
        ctx = ResolutionContext(config=config)
        for name, val in self._CONST.findall(src):
            ctx.constants[name] = val
        vfields = {}
        for placeholder, field in self._VALUE_FIELD.findall(src):
            res = resolve(placeholder, ctx)
            vfields[field] = (res.value, res.tier, res.notes)
        lines = src.splitlines()
        for m in self._SEND.finditer(src):
            ln = src.count("\n", 0, m.start()) + 1
            prov = Provenance(file=rel, line=ln,
                              snippet=lines[ln - 1].strip() if ln <= len(lines) else "")
            arg = m.group(1).strip()
            if arg.startswith('"'):
                res = Resolution(arg.strip('"'), "HIGH", "literal at call site")
            elif arg in ctx.constants:
                res = Resolution(ctx.constants[arg], "HIGH", "local constant")
            elif arg in vfields:
                res = Resolution(*vfields[arg])
            else:
                res = Resolution(None, "LOW", "unresolved")
            if res.resolved:
                prov.resolver_notes = res.notes
                bundle.integration.append(IntegrationFact(
                    module_id=mid, direction="PRODUCES", resource_type="KAFKA_TOPIC",
                    resource_id=res.value, tier=res.tier, provenance=prov))
            else:
                bundle.gaps.append(Gap(module_id=mid, kind="KAFKA_TOPIC",
                                       expression=arg, provenance=prov))
        for rx in (self._QUERY, self._NATIVE):
            for m in rx.finditer(src):
                for direction, table in extract_sql_lineage(m.group(1)):
                    bundle.integration.append(IntegrationFact(
                        module_id=mid, direction=direction, resource_type="SQL_TABLE",
                        resource_id=table, tier="HIGH",
                        provenance=Provenance(file=rel, snippet="(jpa/native query)")))
        for m in self._REST.finditer(src):
            bundle.integration.append(IntegrationFact(
                module_id=mid, direction="CALLS", resource_type="HTTP_ENDPOINT",
                resource_id=m.group(1), tier="HIGH",
                provenance=Provenance(file=rel, snippet="(resttemplate)")))

    def _deps(self, mid, repo_path) -> List[Dependency]:
        out = []
        pom = os.path.join(repo_path, "pom.xml")
        if os.path.exists(pom):
            for group, artifact in _DEP.findall(read(pom)):
                out.append(Dependency(module_id=mid,
                                      purl=f"pkg:maven/{group.strip()}/{artifact.strip()}",
                                      scope="runtime"))
        return out

    @staticmethod
    def _coupling(repo_path) -> float:
        """Internal-class/import dependency density in [0,1] for Java modules.
        Computes directed edge density among local Java classes/files.
        """
        files = walk_files(repo_path, (".java",))
        n = len(files)
        if n < 2:
            return 0.0

        file_types = {}  # file_path -> (pkg_name, set of type_names)
        pkg_re = re.compile(r"^\s*package\s+([\w\.]+)\s*;", re.M)
        type_re = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z0-9_]+)\b")
        import_re = re.compile(r"^\s*import\s+(?:static\s+)?([\w\.\*]+)\s*;", re.M)

        for p in files:
            src = read(p)
            pkg_m = pkg_re.search(src)
            pkg = pkg_m.group(1) if pkg_m else ""
            types = set(type_re.findall(src))
            if not types:
                base = os.path.splitext(os.path.basename(p))[0]
                types = {base}
            file_types[p] = (pkg, types)

        edges = set()
        for p in files:
            src = read(p)
            pkg, types = file_types[p]
            imports = import_re.findall(src)

            # check explicit imports
            for imp in imports:
                imp_clean = imp.strip()
                for target_p, (t_pkg, t_types) in file_types.items():
                    if target_p == p:
                        continue
                    for t in t_types:
                        fqcn = f"{t_pkg}.{t}" if t_pkg else t
                        if imp_clean == fqcn or (imp_clean.endswith(".*") and imp_clean[:-2] == t_pkg) or imp_clean == t:
                            edges.add((p, target_p))

            # check direct references within same package
            words = set(re.findall(r"\b[A-Za-z0-9_]+\b", src))
            for target_p, (t_pkg, t_types) in file_types.items():
                if target_p == p:
                    continue
                if t_pkg == pkg and pkg:
                    for t in t_types:
                        if t in words:
                            edges.add((p, target_p))

        return round(len(edges) / (n * (n - 1)), 3)



register(JavaPlugin())
