"""M0.3 — ingestion + census.

Production pulls the 200 repos via the existing repo-intelligence analyzer's
GitLab hook. For local runs (and the bundled fixtures) census scans a directory
whose immediate subdirectories are repos. For each it records a Project manifest
and picks the primary language plugin.
"""
from __future__ import annotations

import os
from typing import List

from .plugins.base import REGISTRY, read, walk_files
from .runner import ProjectScan
from .schema import Project

_SRC_EXTS = (".py", ".java", ".sql", ".ts", ".js", ".go", ".rb")


def _loc(repo_path: str) -> int:
    total = 0
    for path in walk_files(repo_path, _SRC_EXTS):
        total += read(path).count("\n") + 1
    return total


def _owner(repo_path: str) -> str:
    f = os.path.join(repo_path, "OWNER")
    return read(f).strip() if os.path.exists(f) else "unknown"


def scan_project(repo_path: str, project_id: Optional[str] = None, repo_url: str = "") -> Optional[ProjectScan]:
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
    project = Project(
        id=name, name=name, repo_url=repo_url or f"local:{name}", owner_team=_owner(repo_path),
        langs=langs, loc=_loc(repo_path), activity="unknown",
        deploy_target=det.get("build", ""))
    return ProjectScan(project=project, repo_path=repo_path, primary=primary)


def scan(root: str) -> List[ProjectScan]:
    scans: List[ProjectScan] = []
    for name in sorted(os.listdir(root)):
        repo_path = os.path.join(root, name)
        if not os.path.isdir(repo_path) or name.startswith("."):
            continue
        ps = scan_project(repo_path, project_id=name)
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

