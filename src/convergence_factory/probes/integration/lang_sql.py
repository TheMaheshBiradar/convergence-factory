"""M1.1 — lang-sql.

Two jobs:
  1. As a standalone plugin, analyze SQL-only repos (warehouses, dbt, migrations).
  2. As a SHARED SERVICE: `extract_sql_lineage()` is called by the Python and
     Java plugins to turn embedded SQL strings into READS/WRITES table facts.

Uses sqlglot when installed (accurate, multi-dialect); falls back to a regex
lineage extractor so the factory runs with zero third-party deps.
"""
from __future__ import annotations

import os
import re
from typing import List, Tuple

from convergence_factory.core.schema import FactBundle, IntegrationFact, Module, Provenance
from .base import LanguagePlugin, read, register, walk_files

# direction, table
Lineage = List[Tuple[str, str]]

_CREATE = re.compile(r'\bCREATE\s+(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([`"\w\.]+)', re.I)
_INSERT = re.compile(r'\bINSERT\s+INTO\s+([`"\w\.]+)', re.I)
_UPDATE = re.compile(r'\bUPDATE\s+([`"\w\.]+)', re.I)
_DELETE = re.compile(r'\bDELETE\s+FROM\s+([`"\w\.]+)', re.I)
_FROM = re.compile(r'\bFROM\s+([`"\w\.]+)', re.I)
_JOIN = re.compile(r'\bJOIN\s+([`"\w\.]+)', re.I)


def _clean(name: str) -> str:
    return name.strip().strip('`"').lower()


def _regex_lineage(sql: str) -> Lineage:
    out: Lineage = []
    for m in _CREATE.finditer(sql):
        out.append(("WRITES", _clean(m.group(1))))
    for m in _INSERT.finditer(sql):
        out.append(("WRITES", _clean(m.group(1))))
    for m in _UPDATE.finditer(sql):
        out.append(("WRITES", _clean(m.group(1))))
    for m in _DELETE.finditer(sql):
        out.append(("WRITES", _clean(m.group(1))))
    for m in _FROM.finditer(sql):
        out.append(("READS", _clean(m.group(1))))
    for m in _JOIN.finditer(sql):
        out.append(("READS", _clean(m.group(1))))
    return out


def extract_sql_lineage(sql: str) -> Lineage:
    """Shared entry point. Returns [(direction, table), ...], de-duplicated."""
    if not sql or not sql.strip():
        return []
    lineage: Lineage
    try:
        import sqlglot
        from sqlglot import exp
        lineage = []
        for stmt in sqlglot.parse(sql, error_level=None):
            if stmt is None:
                continue
            writes = isinstance(stmt, (exp.Insert, exp.Update, exp.Delete, exp.Create))
            for t in stmt.find_all(exp.Table):
                name = _clean(t.name if not t.db else f"{t.db}.{t.name}")
                # the target of a write statement is written; other tables are read
                is_target = writes and t is stmt.find(exp.Table)
                lineage.append(("WRITES" if is_target else "READS", name))
    except Exception:
        lineage = _regex_lineage(sql)
    # de-dup, prefer WRITES over READS for the same table
    best = {}
    for direction, table in lineage:
        if table and (table not in best or direction == "WRITES"):
            best[table] = direction
    return [(d, t) for t, d in best.items()]


@register
class SqlPlugin(LanguagePlugin):
    name = "lang-sql"
    lang = "sql"

    def detect(self, repo_path):
        files = walk_files(repo_path, (".sql",))
        if not files:
            return None
        return {"claims": ["sql"], "build": "sql", "score": len(files)}

    def modules(self, repo_path, project_id):
        name = os.path.basename(repo_path.rstrip("/"))
        return [Module(id=f"{project_id}:sql", project_id=project_id,
                       path=repo_path, name=name, kind="library",
                       lang="sql", build_system="sql")]

    def facts(self, module, repo_path):
        bundle = FactBundle(module=module, source_ref=repo_path)
        for path in walk_files(repo_path, (".sql",)):
            sql = read(path)
            rel = os.path.relpath(path, repo_path)
            for direction, table in extract_sql_lineage(sql):
                bundle.integration.append(IntegrationFact(
                    module_id=module.id, direction=direction,
                    resource_type="SQL_TABLE", resource_id=table, tier="HIGH",
                    provenance=Provenance(file=rel, snippet="(sql)")))
        return bundle
