"""API & Contract Surfaces Probe (Probe 3).

Surfaces REST endpoints, gRPC services, GraphQL schemas, and OpenAPI contracts.
"""
from __future__ import annotations

from typing import List
from convergence_factory.core.schema import ApiSurface, Module

def extract_contracts(module: Module, repo_path: str) -> List[ApiSurface]:
    """Base extractor for contract surfaces."""
    return []

__all__ = ["extract_contracts"]
