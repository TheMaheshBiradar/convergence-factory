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

from convergence_factory.core.schema import FactBundle, Module

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

_IGNORED_DIRS = {
    # Version control & OS
    ".git", ".svn", ".hg", ".DS_Store",

    # Node.js / Web
    "node_modules", ".next", ".nuxt", ".output", ".turbo", ".yarn", ".npm",
    "coverage", ".nyc_output", "storybook-static", "bower_components", "jspm_packages",

    # Python
    ".venv", "venv", "env", ".env", "__pycache__", ".pytest_cache", ".tox",
    ".nox", ".mypy_cache", ".ruff_cache", ".coverage", "htmlcov", ".hypothesis",
    ".eggs",

    # Java / JVM
    "target", "build", ".gradle", ".m2", "out", "bin", ".settings", ".metadata",

    # General / IDE / Build / Infra
    ".idea", ".vscode", "vendor", "dist", "tmp", "temp", ".terraform",
}


def is_ignored_dir(name: str) -> bool:
    """Returns True if the directory should be pruned during traversal."""
    if not name or name == ".":
        return False
    if name in _IGNORED_DIRS:
        return True
    if name.startswith(".") and name != ".":
        return True
    if name.endswith((".egg-info", ".dist-info")):
        return True
    return False


def walk_files(repo_path: str, exts: tuple) -> List[str]:
    out = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not is_ignored_dir(d)]
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
