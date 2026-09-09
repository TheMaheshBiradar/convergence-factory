"""BOM / dependency probe."""
import os
import re
from typing import List
from convergence_factory.core.schema import Dependency
from . import bom_probe  # noqa: F401
from .bom_probe import build_sbom, run_bom, shared_dependency_report  # noqa: F401


def parse_requirements_txt(path: str, module_id: str = "") -> List[Dependency]:
    """Extracts Python dependencies from requirements.txt."""
    if not os.path.exists(path):
        return []
    deps = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = re.split(r"[=><~]", line)[0].strip()
            if name:
                deps.append(Dependency(
                    module_id=module_id,
                    purl=f"pkg:pypi/{name}",
                    scope="runtime",
                    tier="HIGH"
                ))
    return deps


__all__ = ["bom_probe", "build_sbom", "run_bom", "shared_dependency_report", "parse_requirements_txt"]

