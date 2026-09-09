"""Portfolio Ingestion, Census & Caching Layer.

Contains:
- census: Filesystem & inventory scanning
- caching: SHA-256 repo content hashing
- connectors: Remote portfolio sources (GitLab)
"""
from . import caching, census, connectors
from .caching import compute_repo_hash
from .census import scan, scan_inventory, scan_project

__all__ = [
    "census",
    "caching",
    "connectors",
    "scan",
    "scan_project",
    "scan_inventory",
    "compute_repo_hash",
]
