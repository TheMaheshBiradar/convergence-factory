"""SOLID seams for the pipeline.

The high-level orchestrator depends on these abstractions, not on concrete
classes (Dependency Inversion). Interfaces are kept small and role-specific
(Interface Segregation): a stage asks only for what it uses.

Layering rule: `core` never imports from `probes`/`exporters`/`remediation`, so
the embedding/judge/summarizer Protocols live with their implementations under
`probes.semantic`; this module holds only the abstractions the *core* pipeline
needs (the store it reads, the portfolio probes it runs, and its config).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class FactStore(Protocol):
    """The persistence abstraction the pipeline and capability stage read.

    Any object satisfying this can back the pipeline (SQLite today, DuckDB or a
    graph DB tomorrow) — the stages never name a concrete store.
    """
    def add_project(self, project: Any) -> None: ...
    def add_module(self, module: Any) -> None: ...
    def modules(self) -> List[Any]: ...
    def integration_facts(self) -> List[Any]: ...
    def module_owner(self) -> Dict[str, str]: ...
    def metrics_by_name(self, name: str) -> Dict[str, float]: ...
    def clone_pairs(self) -> List[Any]: ...
    def close(self) -> None: ...


@runtime_checkable
class PortfolioProbe(Protocol):
    """A cross-cutting probe run over the whole store (clones, api, bom, schema).

    Registered via probes.registry; the EXTRACT/VIEWS stages iterate the registry
    and never hard-code probe names (Open/Closed).
    """
    def __call__(self, store: FactStore, ctx: Dict[str, Any]) -> Dict[str, Any]: ...


@dataclass
class PipelineConfig:
    """Single typed configuration object for a pipeline run.

    Replaces scattered positional args / env lookups so a run is reproducible and
    a stage's inputs are explicit and testable.
    """
    root: str
    out: str
    semantic: bool = True
    remediate: bool = False
    inventory: Optional[str] = None
    functional_max_size: int = 6      # blob guard on the fuzzy dimension
    matrix_max_cols: int = 40         # columns shown per dimension in the matrix
    verbose: bool = False
