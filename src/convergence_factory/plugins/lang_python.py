"""Backward-compatible facade for convergence_factory.probes.integration.lang_python."""
from ..probes.integration.lang_python import *  # noqa: F401, F403
try:
    from ..probes.integration.lang_python import _coupling  # noqa: F401
except ImportError:
    pass
