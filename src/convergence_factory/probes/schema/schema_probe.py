"""DB-schema probe (SchemaCrawler-style, static).

Builds a table-level foreign-key graph from DDL and flags orphan tables — tables
defined but neither referenced by a foreign key nor shared across modules. FK
edges give blast radius; orphans hint at dead data. A live-DB SchemaCrawler run
is the production upgrade; this static pass needs only the .sql in the repos.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import List, Tuple

from convergence_factory.core.store import Store
from convergence_factory.probes.integration.base import read, walk_files

_CREATE_TABLE = re.compile(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`"\w\.]+)', re.I)
_REFERENCES = re.compile(r'REFERENCES\s+([`"\w\.]+)', re.I)


def _clean(name: str) -> str:
    return name.strip().strip('`"').lower().split("(")[0]


def analyze_schema(store: Store) -> dict:
    """Returns tables, FK edges (child -> parent), orphan tables, shared tables."""
    tables = set()
    fk_edges: List[Tuple[str, str]] = []
    referenced = set()

    for m in store.modules():
        for f in walk_files(m.path, (".sql",)):
            sql = read(f)
            for stmt in sql.split(";"):
                cm = _CREATE_TABLE.search(stmt)
                if not cm:
                    continue
                child = _clean(cm.group(1))
                tables.add(child)
                for ref in _REFERENCES.finditer(stmt):
                    parent = _clean(ref.group(1))
                    if parent and parent != child:
                        fk_edges.append((child, parent))
                        referenced.add(parent)
                        referenced.add(child)

    # tables touched by more than one module count as "shared" (not orphaned)
    table_mods = defaultdict(set)
    for r in store.db.execute(
            "SELECT module_id, resource_id FROM integration_facts "
            "WHERE resource_type = 'SQL_TABLE'"):
        table_mods[r["resource_id"]].add(r["module_id"])
    shared = {t for t, mods in table_mods.items() if len(mods) > 1}

    fk_edges = sorted(set(fk_edges))
    orphans = sorted(t for t in tables if t not in referenced and t not in shared)
    return {"tables": sorted(tables), "fk_edges": fk_edges,
            "orphan_tables": orphans, "shared_tables": sorted(shared)}
