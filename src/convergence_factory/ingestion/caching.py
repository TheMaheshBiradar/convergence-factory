"""Repository content-hash caching utilities for incremental execution."""
from __future__ import annotations

import hashlib
import os

from convergence_factory.probes.integration.base import is_ignored_dir


def compute_repo_hash(repo_path: str) -> str:
    """Computes a sha256 content hash of non-hidden, non-ignored repository files."""
    hasher = hashlib.sha256()
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not is_ignored_dir(d)]
        for f in sorted(files):
            if f.startswith(".") or f.endswith((".pyc", ".class", ".o", ".so", ".dylib")):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        hasher.update(chunk)
            except (OSError, IOError):
                pass
    return hasher.hexdigest()
