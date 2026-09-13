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

_SRC_EXTS = (".py", ".java", ".sql", ".ts", ".js", ".go", ".rb", ".jsp", ".jspf", ".tag", ".tld", ".jsx", ".tsx")


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

# A directory owning one of these is a *project root*: we stop descending, because
# its examples/, docs/, src/ belong to it. OWNER / catalog-info are ownership
# markers, NOT code manifests, so they never by themselves make a dir a project.
_CODE_MANIFESTS = {
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "Pipfile", "go.mod", "Cargo.toml", "Gemfile",
}

# Monorepo containers: their manifested children are the real projects.
_MONOREPO_CONTAINERS = {"packages", "apps", "libs", "modules"}

# Never a project, never descended into as a project container.
_NON_PROJECT_DIRS = _INTERNAL_DIR_NAMES | {
    "examples", "example", "docs", "doc", "samples", "sample", "demo", "demos",
    "benchmarks", "benchmark", "fixtures", "e2e", "node_modules", "dist",
    "build", "vendor", "__tests__", "site-packages",
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
    plugins = [p for p, _d in detections]
    loc = _loc(repo_path)
    owner = _owner(repo_path, root_dir=root_dir)
    LOGGER.info(
        "Census '%s': assigned primary plugin '%s' (active plugins: [%s], claims: %s, loc: %d, owner: %s)",
        name, primary.name,
        ", ".join(f"{p.name}:{d.get('score', 0)}" for p, d in detections),
        langs, loc, owner
    )
    project = Project(
        id=name, name=os.path.basename(repo_path.rstrip("/")), repo_url=repo_url or f"local:{name}",
        owner_team=owner, langs=langs, loc=loc, activity="unknown",
        deploy_target=det.get("build", ""))
    return ProjectScan(project=project, repo_path=repo_path, primary=primary, plugins=plugins)


def find_project_dirs(root: str, max_depth: int = 6) -> List[str]:
    """Discover project directories across flat, nested-group, and monorepo layouts.

    A directory with its own *code* manifest is a project and we do NOT descend
    into it — its examples/, docs/, src/ are part of that project, not separate
    projects. The exception is a monorepo: a packages/ (or apps/, libs/, modules/)
    container of manifested children means those children are the projects.
    Manifest-less directories are treated as group/subgroup containers and searched
    recursively. This ensures every real repo yields at least one project (root as
    fallback) and stops the census from turning a repo's examples into projects.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []

    project_paths: List[str] = []

    def _entries(path: str) -> List[str]:
        try:
            return os.listdir(path)
        except OSError:
            return []

    def _has_code_manifest(path: str) -> bool:
        return bool(set(_entries(path)) & _CODE_MANIFESTS)

    def _has_code(path: str) -> bool:
        """A repo root signal: a code manifest, source files, or a .git dir. OWNER
        alone does not count (it is an ownership marker on a group container)."""
        if os.path.exists(os.path.join(path, ".git")):
            return True
        files = [e for e in _entries(path) if os.path.isfile(os.path.join(path, e))]
        if set(files) & _CODE_MANIFESTS:
            return True
        return any(f.endswith(_SRC_EXTS) for f in files)

    def _monorepo_subprojects(path: str) -> List[str]:
        subs: List[str] = []
        for cont in _MONOREPO_CONTAINERS:
            cpath = os.path.join(path, cont)
            if os.path.isdir(cpath):
                for e in sorted(_entries(cpath)):
                    ep = os.path.join(cpath, e)
                    if os.path.isdir(ep) and not is_ignored_dir(e) and _has_code_manifest(ep):
                        subs.append(ep)
        return subs

    def _has_child_projects(path: str, cur_depth: int) -> bool:
        if cur_depth >= max_depth:
            return False
        for e in _entries(path):
            if is_ignored_dir(e) or e in _NON_PROJECT_DIRS:
                continue
            cp = os.path.join(path, e)
            if os.path.isdir(cp) and (_has_code(cp) or _has_child_projects(cp, cur_depth + 1)):
                return True
        return False

    def _search(current_path: str, cur_depth: int):
        base = os.path.basename(current_path.rstrip("/"))
        if cur_depth > max_depth or is_ignored_dir(base) or base in _NON_PROJECT_DIRS:
            return

        if _has_code_manifest(current_path):
            # A real repo root. Split a monorepo into its packages; otherwise this
            # directory is one project and we do NOT descend into examples/src/etc.
            subs = _monorepo_subprojects(current_path)
            if subs:
                for sp in subs:
                    _search(sp, cur_depth + 1)
            else:
                project_paths.append(current_path)
            return

        # No code manifest here -> group/subgroup container: search deeper.
        if _has_child_projects(current_path, cur_depth):
            for entry in sorted(_entries(current_path)):
                if is_ignored_dir(entry) or entry in _NON_PROJECT_DIRS:
                    continue
                cp = os.path.join(current_path, entry)
                if os.path.isdir(cp):
                    _search(cp, cur_depth + 1)
        elif _has_code(current_path):
            # Code-only leaf (e.g. a SQL/migrations repo with no manifest).
            project_paths.append(current_path)

    _search(root, cur_depth=0)
    return sorted(set(project_paths))


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

