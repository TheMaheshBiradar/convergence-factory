"""API / contract probe."""
from typing import List
from convergence_factory.core.schema import ApiSurface, Module
from . import api_probe  # noqa: F401
from .api_probe import extract_api  # noqa: F401


def extract_contracts(module: Module = None, repo_path: str = "") -> List[ApiSurface]:
    """Base extractor for contract surfaces."""
    return []


__all__ = ["api_probe", "extract_api", "extract_contracts"]

