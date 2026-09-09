"""Convergence Factory — a layered evidence pipeline that turns a portfolio of
heterogeneous repositories into a ranked map of duplicate functionality.

Importing the package registers the bundled language plugins.
"""
from . import plugins  # noqa: F401  (import side-effect: registers plugins)
from .schema import SCHEMA_VERSION

__version__ = "0.1.0"
__all__ = ["SCHEMA_VERSION", "__version__"]
