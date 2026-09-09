"""Repository content-hash caching utilities for incremental execution."""
from __future__ import annotations

import hashlib
import os


def compute_repo_hash(repo_path: str) -> str:
    """Computes a sha256 content hash of non-hidden repository files."""
    hasher = hashlib.sha256()
    for root, _, files in os.walk(repo_path):
        for f in sorted(files):
            if f.startswith("."):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "rb") as fh:
                    hasher.update(fh.read())
            except (OSError, IOError):
                pass
    return hasher.hexdigest()
