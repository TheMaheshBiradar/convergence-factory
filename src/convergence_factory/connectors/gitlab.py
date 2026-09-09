"""GitLab Portfolio Connector.

Bridges GitLab inventories and APIs into the Convergence Factory census.
Reads inventory JSON files (from gitlab-repo-intelligence or GitLab exports)
or queries the GitLab REST API directly to feed ProjectScan objects.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional
import urllib.request


def parse_inventory(data: Any) -> List[Dict[str, Any]]:
    """Walks nested group/subgroup/project structures or flat lists to extract all projects."""
    projects: List[Dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if "projects" in node and isinstance(node["projects"], list):
                for p in node["projects"]:
                    if isinstance(p, dict) and "id" in p:
                        projects.append(p)
            elif "id" in node and "groups" not in node and "subgroups" not in node:
                projects.append(node)

            if "groups" in node and isinstance(node["groups"], list):
                for g in node["groups"]:
                    _walk(g)
            if "subgroups" in node and isinstance(node["subgroups"], list):
                for sg in node["subgroups"]:
                    _walk(sg)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    # Deduplicate and merge attributes
    deduped: Dict[Any, Dict[str, Any]] = {}
    for p in projects:
        pid = p.get("id")
        if pid not in deduped:
            deduped[pid] = dict(p)
        else:
            for k, v in p.items():
                if v and not deduped[pid].get(k):
                    deduped[pid][k] = v
    return list(deduped.values())


class GitLabConnector:
    """Connector to pull repository trees or clone repos from GitLab."""

    def __init__(self, token: Optional[str] = None, base_url: str = "https://gitlab.com"):
        self.token = token or os.environ.get("GITLAB_TOKEN", "")
        self.base_url = base_url.rstrip("/")

    def fetch_project(self, project_id: int | str) -> Dict[str, Any]:
        """Fetches project metadata from the GitLab REST API."""
        url = f"{self.base_url}/api/v4/projects/{project_id}"
        req = urllib.request.Request(url)
        if self.token:
            req.add_header("PRIVATE-TOKEN", self.token)

        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf8"))

    def sync_repo(self, repo_url: str, target_dir: str, default_branch: str = "main") -> str:
        """Clones or pulls a repository into target_dir."""
        os.makedirs(os.path.dirname(os.path.abspath(target_dir)), exist_ok=True)
        auth_url = repo_url
        if self.token and "gitlab.com" in repo_url and not repo_url.startswith("git@"):
            # Inject token into HTTPS URL safely for git CLI
            auth_url = repo_url.replace("https://", f"https://oauth2:{self.token}@")

        if os.path.exists(os.path.join(target_dir, ".git")):
            # Update existing
            subprocess.run(["git", "-C", target_dir, "pull", "--ff-only"],
                           capture_output=True, check=False)
        else:
            # Clone new shallow copy
            subprocess.run(["git", "clone", "--depth", "1", "-b", default_branch, auth_url, target_dir],
                           capture_output=True, check=False)
        return target_dir
