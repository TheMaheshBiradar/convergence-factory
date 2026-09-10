"""Convergence Factory Core Analytical Engine (Standard Library Only).

Contains:
- schema: Normalized schema contract (v0.1) and validation
- store: SQLite FactStore with SHA-256 caching
- resolver: Config and constant resolution
- graph: Derived similarity graph, clustering, and opportunity formula
"""
from __future__ import annotations

from . import errors, graph, resolver, schema, store
from .errors import ERROR_TRACKER, ErrorTracker, FrameworkError
from .graph import build, promote_candidates
from .resolver import (
    Resolution,
    ResolutionContext,
    load_properties,
    load_simple_yaml,
    resolve,
)
from .schema import (
    API_KINDS,
    DEP_SCOPES,
    DIRECTIONS,
    MODULE_KINDS,
    RESOURCE_TYPES,
    SCHEMA_VERSION,
    TIERS,
    ApiSurface,
    CapabilitySummary,
    ClonePair,
    Dependency,
    FactBundle,
    Gap,
    IntegrationFact,
    Module,
    ModuleMetric,
    Project,
    Provenance,
    SchemaError,
    to_dict,
    validate_api,
    validate_bundle,
    validate_dependency,
    validate_integration,
    validate_module,
)
from .store import Store

__all__ = [
    "SCHEMA_VERSION",
    "TIERS",
    "DIRECTIONS",
    "RESOURCE_TYPES",
    "MODULE_KINDS",
    "API_KINDS",
    "DEP_SCOPES",
    "ApiSurface",
    "CapabilitySummary",
    "ClonePair",
    "Dependency",
    "FactBundle",
    "Gap",
    "IntegrationFact",
    "Module",
    "ModuleMetric",
    "Project",
    "Provenance",
    "SchemaError",
    "to_dict",
    "validate_api",
    "validate_bundle",
    "validate_dependency",
    "validate_integration",
    "validate_module",
    "Store",
    "Resolution",
    "ResolutionContext",
    "resolve",
    "load_simple_yaml",
    "load_properties",
    "build",
    "promote_candidates",
    "schema",
    "store",
    "resolver",
    "graph",
    "errors",
    "ERROR_TRACKER",
    "ErrorTracker",
    "FrameworkError",
]
