"""Backward-compatible facade for convergence_factory.ingestion.connectors."""
from . import gitlab  # noqa: F401
from ..ingestion.connectors import *  # noqa: F401, F403
