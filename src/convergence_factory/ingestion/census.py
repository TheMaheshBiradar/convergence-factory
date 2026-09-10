"""M0.3 — ingestion + census.

Production pulls the 200 repos via the existing repo-intelligence analyzer's
GitLab hook. For local runs (and the bundled fixtures) census scans a directory
whose immediate subdirectories are repos. For each it records a Project manifest
and picks the primary language plugin.
"""
from __future__ import annotations

import os
from typing import List, Optional

from convergence_factory.logger import LOGGER
from convergence_factory.probes.integration.base import REGISTRY, is_ignored_dir, read, walk_files
from convergence_factory.runner import ProjectScan
from convergence_factory.core.schema import Project

_SRC_EXTS = (".py", ".java", ".sql", ".ts", ".js", ".go", ".rb")


_MANIFEST_FILES = {
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "package.json",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile",
    "go.mod", "Cargo.toml", "Gemfile",
    "OWNER", "catalog-info.yaml",
}

_INTERNAL_DIR_NAMES = {
    "src", "main", "test", "tests", "resources", "lib", "app",
    "controllers", "services", "models", "routes", "views", "components",
    "config", "utils", "internal", "pkg", "cmd",
}


def _loc(repo_path: str) -> int:
    total = 0
    for path in walk_files(repo_path, _SRC_EXTS):
        try:
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    total += chunk.count(b"\n")
            total += 1
        except OSError:
            pass
    return total


def _owner(repo_path: str, root_dir: str = "") -> str:
    """Checks for an OWNER file in repo_path, or walks up to root_dir to inherit group ownership."""
    cur = os.path.abspath(repo_path)
    root_abs = os.path.abspath(root_dir) if root_dir else ""
    while True:
        f = os.path.join(cur, "OWNER")
        if os.path.exists(f):
            content = read(f).strip()
            if content:
                return content
        if not root_abs or cur == root_abs or os.path.dirname(cur) == cur:
            break
        cur = os.path.dirname(cur)
    return "unknown"


def scan_project(repo_path: str, project_id: Optional[str] = None, repo_url: str = "", root_dir: str = "") -> Optional[ProjectScan]:
    name = project_id or os.path.basename(repo_path.rstrip("/"))
    detections = []
    for plugin in REGISTRY:
        det = plugin.detect(repo_path)
        if det:
            detections.append((plugin, det))
    if not detections:
        return None
    langs = sorted({c for _p, d in detections for c in d["claims"]})
    primary, det = max(detections, key=lambda pd: pd[1].get("score", 0))
    loc = _loc(repo_path)
    owner = _owner(repo_path, root_dir=root_dir)
    LOGGER.info(
        "Census '%s': assigned primary plugin '%s' (claims: %s, candidates: [%s], loc: %d, owner: %s)",
        name, primary.name, langs,
        ", ".join(f"{p.name}:{d.get('score', 0)}" for p, d in detections),
        loc, owner
    )
    project = Project(
        id=name, name=os.path.basename(repo_path.rstrip("/")), repo_url=repo_url or f"local:{name}",
        owner_team=owner, langs=langs, loc=loc, activity="unknown",
        deploy_target=det.get("build", ""))
    return ProjectScan(project=project, repo_path=repo_path, primary=primary)


def find_project_dirs(root: str, max_depth: int = 5) -> List[str]:
    """Recursively discovers project directories within flat or nested group/subgroup hierarchies.

    Detects leaf projects containing manifests or source files without descending into
    internal source/resource directories (src, test, etc.).
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []

    project_paths: List[str] = []

    def _has_manifest_or_code(path: str) -> bool:
        try:
            entries = os.listdir(path)
        except OSError:
            return False
        files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
        if bool(set(files) & _MANIFEST_FILES) or os.path.exists(os.path.join(path, ".git")):
            return True
        return any(f.endswith(_SRC_EXTS) for f in files)

    def _has_child_projects(path: str, cur_depth: int) -> bool:
        if cur_depth >= max_depth:
            return False
        try:
            entries = os.listdir(path)
        except OSError:
            return False
        for e in entries:
            if is_ignored_dir(e) or e in _INTERNAL_DIR_NAMES:
                continue
            child_path = os.path.join(path, e)
            if os.path.isdir(child_path):
                if _has_manifest_or_code(child_path):
                    return True
                if _has_child_projects(child_path, cur_depth + 1):
                    return True
        return False

    def _search(current_path: str, cur_depth: int):
        if cur_depth > max_depth or is_ignored_dir(os.path.basename(current_path)):
            return

        # If current_path has child projects in subdirectories, we search the children
        if _has_child_projects(current_path, cur_depth):
            try:
                for entry in sorted(os.listdir(current_path)):
                    if is_ignored_dir(entry) or entry in _INTERNAL_DIR_NAMES:
                        continue
                    child_path = os.path.join(current_path, entry)
                    if os.path.isdir(child_path):
                        _search(child_path, cur_depth + 1)
            except OSError:
                pass
        else:
            # Current path has NO child projects. Does it have manifest or code itself?
            if _has_manifest_or_code(current_path):
                project_paths.append(current_path)

    _search(root, cur_depth=0)
    return sorted(project_paths)


def scan(root: str) -> List[ProjectScan]:
    """Scans root for projects across flat or multi-level nested group/subgroup directory structures."""
    root_abs = os.path.abspath(root)
    proj_dirs = find_project_dirs(root_abs)
    if not proj_dirs:
        return []

    # Detect if any basenames collide across different subgroups
    basenames = [os.path.basename(p.rstrip("/")) for p in proj_dirs]
    counts = {}
    for b in basenames:
        counts[b] = counts.get(b, 0) + 1

    scans: List[ProjectScan] = []
    for repo_path in proj_dirs:
        bname = os.path.basename(repo_path.rstrip("/"))
        if counts.get(bname, 0) > 1:
            # Collision: use relative path slug as unique ID (e.g. subgroup_a-order-service)
            rel = os.path.relpath(repo_path, root_abs).replace("\\", "/")
            project_id = rel.replace("/", "-")
        else:
            project_id = bname

        ps = scan_project(repo_path, project_id=project_id, root_dir=root_abs)
        if ps:
            scans.append(ps)
    return scans


def scan_inventory(inventory_items: List[dict], base_dir: str) -> List[ProjectScan]:
    """Scans local directories that correspond to items in a GitLab inventory."""
    scans: List[ProjectScan] = []
    for item in inventory_items:
        name = item.get("name") or item.get("path_with_namespace", "").split("/")[-1] or str(item.get("id"))
        cand_path = os.path.join(base_dir, name)
        if os.path.isdir(cand_path):
            ps = scan_project(cand_path, project_id=name, repo_url=item.get("http_url_to_repo", f"gitlab:{name}"))
            if ps:
                scans.append(ps)
    return scans

