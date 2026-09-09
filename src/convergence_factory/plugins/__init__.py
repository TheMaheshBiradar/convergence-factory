"""Backward-compatible facade for convergence_factory.probes.integration."""
from ..probes.integration import *  # noqa: F401, F403
from ..probes.integration.base import REGISTRY  # noqa: F401
from . import base, lang_java, lang_node, lang_python, lang_sql  # noqa: F401

__all__ = ["REGISTRY"]
