"""M0.4 — Fact store.

Facts land in SQLite (stdlib, zero infra) so they are queryable and durable; the
graph builder (graph.py) derives the similarity graph from these rows. In
production this is the place you would swap in DuckDB/Parquet for scale — the
interface below is all the rest of the system depends on.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Iterable, List

from .schema import (
    ApiSurface, CapabilitySummary, Dependency, Gap, IntegrationFact, Module,
    ModuleMetric, Project, Provenance,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, repo_url TEXT, name TEXT, owner_team TEXT,
  langs TEXT, loc INTEGER, activity TEXT, deploy_target TEXT);
CREATE TABLE IF NOT EXISTS modules (
  id TEXT PRIMARY KEY, project_id TEXT, path TEXT, name TEXT,
  kind TEXT, lang TEXT, build_system TEXT);
CREATE TABLE IF NOT EXISTS integration_facts (
  module_id TEXT, direction TEXT, resource_type TEXT, resource_id TEXT,
  tier TEXT, schema_ref TEXT, provenance TEXT);
CREATE TABLE IF NOT EXISTS dependencies (
  module_id TEXT, purl TEXT, scope TEXT, tier TEXT);
CREATE TABLE IF NOT EXISTS api_surfaces (
  module_id TEXT, kind TEXT, signature TEXT, role TEXT, tier TEXT);
CREATE TABLE IF NOT EXISTS capability_summaries (
  module_id TEXT, summary TEXT, domain TEXT, operations TEXT,
  embedding_ref TEXT, tier TEXT);
CREATE TABLE IF NOT EXISTS gaps (
  module_id TEXT, kind TEXT, expression TEXT, provenance TEXT);
CREATE TABLE IF NOT EXISTS module_metrics (
  module_id TEXT, name TEXT, value REAL);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    # --- writers ---
    def add_project(self, p: Project) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?,?,?,?)",
            (p.id, p.repo_url, p.name, p.owner_team, json.dumps(p.langs),
             p.loc, p.activity, p.deploy_target))
        self.db.commit()

    def add_module(self, m: Module) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO modules VALUES (?,?,?,?,?,?,?)",
            (m.id, m.project_id, m.path, m.name, m.kind, m.lang, m.build_system))
        self.db.commit()

    def add_integration(self, facts: Iterable[IntegrationFact]) -> None:
        self.db.executemany(
            "INSERT INTO integration_facts VALUES (?,?,?,?,?,?,?)",
            [(f.module_id, f.direction, f.resource_type, f.resource_id, f.tier,
              f.schema_ref, json.dumps(asdict(f.provenance))) for f in facts])
        self.db.commit()

    def add_dependencies(self, deps: Iterable[Dependency]) -> None:
        self.db.executemany(
            "INSERT INTO dependencies VALUES (?,?,?,?)",
            [(d.module_id, d.purl, d.scope, d.tier) for d in deps])
        self.db.commit()

    def add_api(self, apis: Iterable[ApiSurface]) -> None:
        self.db.executemany(
            "INSERT INTO api_surfaces VALUES (?,?,?,?,?)",
            [(a.module_id, a.kind, a.signature, a.role, a.tier) for a in apis])
        self.db.commit()

    def add_summaries(self, sums: Iterable[CapabilitySummary]) -> None:
        self.db.executemany(
            "INSERT INTO capability_summaries VALUES (?,?,?,?,?,?)",
            [(s.module_id, s.summary, s.domain, json.dumps(s.operations),
              s.embedding_ref, s.tier) for s in sums])
        self.db.commit()

    def add_gaps(self, gaps: Iterable[Gap]) -> None:
        self.db.executemany(
            "INSERT INTO gaps VALUES (?,?,?,?)",
            [(g.module_id, g.kind, g.expression, json.dumps(asdict(g.provenance)))
             for g in gaps])
        self.db.commit()

    def add_metrics(self, metrics: Iterable[ModuleMetric]) -> None:
        self.db.executemany(
            "INSERT INTO module_metrics VALUES (?,?,?)",
            [(m.module_id, m.name, m.value) for m in metrics])
        self.db.commit()

    def metrics_by_name(self, name: str) -> dict:
        rows = self.db.execute(
            "SELECT module_id, value FROM module_metrics WHERE name = ?", (name,)).fetchall()
        return {r["module_id"]: r["value"] for r in rows}

    # --- readers ---
    def projects(self) -> List[Project]:
        rows = self.db.execute("SELECT * FROM projects").fetchall()
        return [Project(r["id"], r["repo_url"], r["name"], r["owner_team"],
                        json.loads(r["langs"]), r["loc"], r["activity"],
                        r["deploy_target"]) for r in rows]

    def modules(self) -> List[Module]:
        rows = self.db.execute("SELECT * FROM modules").fetchall()
        return [Module(r["id"], r["project_id"], r["path"], r["name"],
                       r["kind"], r["lang"], r["build_system"]) for r in rows]

    def module_owner(self) -> dict:
        """module_id -> owner_team, via the module's project."""
        rows = self.db.execute(
            "SELECT m.id AS mid, p.owner_team AS owner FROM modules m "
            "JOIN projects p ON p.id = m.project_id").fetchall()
        return {r["mid"]: r["owner"] for r in rows}

    def integration_facts(self) -> List[IntegrationFact]:
        rows = self.db.execute("SELECT * FROM integration_facts").fetchall()
        out = []
        for r in rows:
            prov = json.loads(r["provenance"])
            out.append(IntegrationFact(
                r["module_id"], r["direction"], r["resource_type"],
                r["resource_id"], r["tier"], Provenance(**prov), r["schema_ref"]))
        return out

    def counts(self) -> dict:
        c = self.db.execute
        return {
            "projects": c("SELECT COUNT(*) FROM projects").fetchone()[0],
            "modules": c("SELECT COUNT(*) FROM modules").fetchone()[0],
            "integration_facts": c("SELECT COUNT(*) FROM integration_facts").fetchone()[0],
            "dependencies": c("SELECT COUNT(*) FROM dependencies").fetchone()[0],
            "gaps": c("SELECT COUNT(*) FROM gaps").fetchone()[0],
        }
