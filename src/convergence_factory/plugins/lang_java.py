"""Backward-compatible facade for convergence_factory.probes.integration.lang_java."""
from ..probes.integration.lang_java import *  # noqa: F401, F403
try:
    from ..probes.integration.lang_java import _coupling  # noqa: F401
except ImportError:
    pass
