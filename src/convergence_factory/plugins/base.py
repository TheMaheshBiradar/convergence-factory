"""M0.2 (contract half) — the plugin SPI.

A language plugin reads a repo in its language and emits normalized facts. It
implements only what it can: a partial plugin (say, modules + integration facts
but no clone detection) still contributes. The core consumes the FactBundle and
never learns the language.

Plugins register by discovery (import side-effect here; entry-points in prod).
"""
from __future__ import annotations

import os
from typing import List, Optional

from ..schema import FactBundle, Module

REGISTRY: List["LanguagePlugin"] = []


def register(plugin):
    """Register a plugin. Accepts a class (as a decorator) or an instance;
    either way the REGISTRY holds an instance. Returns the argument unchanged."""
    REGISTRY.append(plugin() if isinstance(plugin, type) else plugin)
    return plugin


class LanguagePlugin:
    name = "base"
    lang = ""

    def detect(self, repo_path: str) -> Optional[dict]:
        """Return {'claims': [...], 'build': str, 'score': int} or None.

        `score` (usually a source-file count) lets the runner pick the primary
        plugin when several claim a repo.
        """
        raise NotImplementedError

    def modules(self, repo_path: str, project_id: str) -> List[Module]:
        raise NotImplementedError

    def facts(self, module: Module, repo_path: str) -> FactBundle:
        raise NotImplementedError


# --- small shared filesystem helpers ---

def walk_files(repo_path: str, exts: tuple) -> List[str]:
    out = []
    for root, _dirs, files in os.walk(repo_path):
        if "/.git" in root:
            continue
        for f in files:
            if f.endswith(exts):
                out.append(os.path.join(root, f))
    return out


def read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""
