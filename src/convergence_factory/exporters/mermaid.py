"""Mermaid.js wiring and resource topology diagram generator."""
from __future__ import annotations

from collections import defaultdict
import os
import re
from typing import List, Optional, Set, Tuple

from convergence_factory.core.store import Store


def _safe_id(val: str) -> str:
    """Converts an arbitrary string identifier to a valid Mermaid node identifier."""
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', val)
    return cleaned if cleaned else "node"


def _safe_label(val: str, max_len: int = 60) -> str:
    """Escapes quotes and truncates long labels for readable Mermaid rendering."""
    s = val.replace('"', "'").strip()
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s


def generate_mermaid_diagram(store: Store, clusters: List[dict], max_edges: int = 1000) -> str:
    """Generates a clean, deduplicated Mermaid.js flow diagram representing resource wiring.

    Automatically prioritizes shared resources (cross-module coupling) and detected
    convergence clusters. Defaults to 1,000 edges so multi-project estates display completely
    without truncation. Configurable via CONVERGENCE_MAX_MERMAID_EDGES env var or max_edges parameter.
    """
    env_limit = os.environ.get("CONVERGENCE_MAX_MERMAID_EDGES")
    if env_limit:
        try:
            max_edges = int(env_limit)
        except ValueError:
            pass

    facts = store.integration_facts()
    if not facts:
        return "graph LR\n  empty[\"No integration facts recorded in FactStore\"]"

    module_name = {m.id: m.name for m in store.modules()}
    cluster_members: Set[str] = set()
    for cl in (clusters or []):
        cluster_members.update(cl.get("members", []))

    # 1. Map resource usage to identify shared resources
    resource_users = defaultdict(set)
    for f in facts:
        resource_users[(f.resource_type, f.resource_id)].add(f.module_id)

    # 2. Collect unique edges with priority scores
    scored_edges = []
    seen_edges: Set[Tuple[str, str, str, str]] = set()

    for f in facts:
        res_key = (f.resource_type, f.resource_id)
        mod_id = f.module_id
        direction = f.direction

        edge_tuple = (mod_id, f.resource_type, f.resource_id, direction)
        if edge_tuple in seen_edges:
            continue
        seen_edges.add(edge_tuple)

        score = 0
        users_count = len(resource_users[res_key])
        if users_count >= 2:
            score += 100 * users_count
        if mod_id in cluster_members:
            score += 50
        if f.tier == "HIGH":
            score += 20
        elif f.tier == "MED":
            score += 10

        scored_edges.append((score, f))

    # Sort descending by priority score
    scored_edges.sort(key=lambda x: x[0], reverse=True)

    is_truncated = len(scored_edges) > max_edges
    selected = [item[1] for item in scored_edges[:max_edges]]

    lines = ["graph LR"]
    nodes_added = set()

    for f in selected:
        mod_safe = _safe_id(f.module_id)
        mod_label = _safe_label(module_name.get(f.module_id, f.module_id))
        if mod_safe not in nodes_added:
            lines.append(f'  {mod_safe}["{mod_label}"]')
            nodes_added.add(mod_safe)

        res_safe = _safe_id(f"{f.resource_type}_{f.resource_id}")
        res_label = _safe_label(f.resource_id)
        if res_safe not in nodes_added:
            if f.resource_type == "KAFKA_TOPIC":
                lines.append(f'  {res_safe}(("{res_label}"))')
            elif f.resource_type == "SQL_TABLE":
                lines.append(f'  {res_safe}[("{res_label}")]')
            else:
                lines.append(f'  {res_safe}["{res_label}"]')
            nodes_added.add(res_safe)

        dir_label = f.direction.lower()
        if f.direction in ("PRODUCES", "WRITES"):
            lines.append(f"  {mod_safe} -->|{dir_label}| {res_safe}")
        else:
            lines.append(f"  {res_safe} -->|{dir_label}| {mod_safe}")

    if is_truncated:
        summary_label = (
            f"Showing top {len(selected)} core shared resources & cluster links "
            f"(of {len(facts)} total integration facts across {len(module_name)} modules). "
            f"Full comprehensive topology is available in graph.json / Cytoscape."
        )
        lines.append('  subgraph Estate_Summary ["Estate Summary"]')
        lines.append(f'    summary_note["{summary_label}"]')
        lines.append('  end')
        lines.append('  classDef summaryStyle fill:#f0f4f8,stroke:#93a9b8,stroke-dasharray: 5 5,color:#5c6a78;')
        lines.append('  class summary_note summaryStyle;')

    return "\n".join(lines)
