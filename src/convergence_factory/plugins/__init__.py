"""Plugin discovery. Importing this package registers each language plugin.

In production, replace these explicit imports with entry-point discovery so a new
plugin package (e.g. lang-go) is found without editing the core.
"""
from . import lang_sql, lang_python, lang_java  # noqa: F401
from .base import REGISTRY

__all__ = ["REGISTRY"]
