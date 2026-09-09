"""M0.1 — The normalized fact model.

This module IS the contract between plugins and the core. Every plugin emits
these objects and nothing else; the core consumes only these and never learns a
language. Provenance and a confidence tier are mandatory on every extracted fact.

The schema is versioned: a plugin declares the version it targets, and the core
refuses facts from an incompatible major version.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List

SCHEMA_VERSION = "0.1"

# --- controlled vocabularies (the enums the core validates against) ---
TIERS = {"HIGH", "MED", "LOW"}
DIRECTIONS = {"PRODUCES", "CONSUMES", "READS", "WRITES", "CALLS"}
RESOURCE_TYPES = {"KAFKA_TOPIC", "SQL_TABLE", "HTTP_ENDPOINT", "JMS_QUEUE", "CACHE_KEY"}
MODULE_KINDS = {"service", "library", "job", "batch"}
API_KINDS = {"REST", "GRPC", "GRAPHQL"}
DEP_SCOPES = {"runtime", "test", "build"}


class SchemaError(ValueError):
    """Raised when a plugin emits a fact that violates the contract."""


@dataclass
class Provenance:
    file: str
    line: int = 0
    snippet: str = ""
    resolver_notes: str = ""


@dataclass
class Project:
    id: str
    repo_url: str = ""
    name: str = ""
    owner_team: str = ""
    langs: List[str] = field(default_factory=list)
    loc: int = 0
    activity: str = ""
    deploy_target: str = ""


@dataclass
class Module:
    id: str
    project_id: str
    path: str
    name: str
    kind: str = "service"
    lang: str = ""
    build_system: str = ""


@dataclass
class IntegrationFact:
    """The 'Kafka producer' signal: a module's wiring to shared infrastructure."""
    module_id: str
    direction: str
    resource_type: str
    resource_id: str
    tier: str
    provenance: Provenance
    schema_ref: str = ""


@dataclass
class Dependency:
    module_id: str
    purl: str
    scope: str = "runtime"
    tier: str = "HIGH"


@dataclass
class ApiSurface:
    module_id: str
    kind: str
    signature: str
    role: str = "server"
    tier: str = "HIGH"


@dataclass
class ClonePair:
    module_a: str
    module_b: str
    clone_type: int
    similarity: float
    tier: str = "HIGH"


@dataclass
class CapabilitySummary:
    module_id: str
    summary: str
    domain: str = ""
    operations: List[str] = field(default_factory=list)
    embedding_ref: str = ""
    tier: str = "MED"


@dataclass
class Gap:
    """A resource reference the resolver could not resolve — tracked, never dropped."""
    module_id: str
    kind: str          # what we were resolving, e.g. "KAFKA_TOPIC"
    expression: str    # the unresolved expression, verbatim
    provenance: Provenance


@dataclass
class FactBundle:
    """What a plugin returns for one module."""
    module: Module
    integration: List[IntegrationFact] = field(default_factory=list)
    dependencies: List[Dependency] = field(default_factory=list)
    api: List[ApiSurface] = field(default_factory=list)
    summaries: List[CapabilitySummary] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)
    source_ref: str = ""   # path to source text for the semantic probe


# --- validation: the core's gate on everything a plugin emits ---

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SchemaError(msg)


def validate_integration(f: IntegrationFact) -> None:
    _require(bool(f.module_id), "integration.module_id is required")
    _require(f.direction in DIRECTIONS, f"bad direction {f.direction!r}")
    _require(f.resource_type in RESOURCE_TYPES, f"bad resource_type {f.resource_type!r}")
    _require(bool(f.resource_id), "integration.resource_id is required")
    _require(f.tier in TIERS, f"bad tier {f.tier!r}")
    _require(isinstance(f.provenance, Provenance), "integration.provenance missing")


def validate_dependency(d: Dependency) -> None:
    _require(bool(d.module_id) and bool(d.purl), "dependency needs module_id and purl")
    _require(d.scope in DEP_SCOPES, f"bad dep scope {d.scope!r}")
    _require(d.tier in TIERS, f"bad tier {d.tier!r}")


def validate_api(a: ApiSurface) -> None:
    _require(a.kind in API_KINDS, f"bad api kind {a.kind!r}")
    _require(a.role in {"server", "client"}, f"bad api role {a.role!r}")


def validate_module(m: Module) -> None:
    _require(bool(m.id) and bool(m.project_id), "module needs id and project_id")
    _require(m.kind in MODULE_KINDS, f"bad module kind {m.kind!r}")


def validate_bundle(b: FactBundle) -> List[str]:
    """Validate a whole bundle. Returns a list of error strings (empty == clean).

    The runner uses this to skip invalid facts without killing the pipeline.
    """
    errors: List[str] = []
    try:
        validate_module(b.module)
    except SchemaError as e:
        errors.append(f"module: {e}")
    for f in b.integration:
        try:
            validate_integration(f)
        except SchemaError as e:
            errors.append(f"integration: {e}")
    for d in b.dependencies:
        try:
            validate_dependency(d)
        except SchemaError as e:
            errors.append(f"dependency: {e}")
    for a in b.api:
        try:
            validate_api(a)
        except SchemaError as e:
            errors.append(f"api: {e}")
    return errors


def to_dict(obj) -> dict:
    return asdict(obj)
