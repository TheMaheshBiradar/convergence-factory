"""Mermaid.js wiring and resource topology diagram generator."""
from __future__ import annotations

from typing import List
from convergence_factory.core.store import Store


def generate_mermaid_diagram(store: Store, clusters: List[dict]) -> str:
    """Generates Mermaid.js flow diagram representing resource wiring and modules."""
    lines = ["graph LR"]
    module_name = {m.id: m.name for m in store.modules()}
    facts = store.integration_facts()
    nodes_added = set()

    for f in facts:
        mod_safe = f.module_id.replace(":", "_").replace("-", "_").replace(".", "_")
        mod_label = module_name.get(f.module_id, f.module_id)
        if mod_safe not in nodes_added:
            lines.append(f'  {mod_safe}["{mod_label}"]')
            nodes_added.add(mod_safe)

        res_safe = f"{f.resource_type}_{f.resource_id}".replace(".", "_").replace("-", "_").replace("/", "_")
        if res_safe not in nodes_added:
            if f.resource_type == "KAFKA_TOPIC":
                lines.append(f'  {res_safe}(("{f.resource_id}"))')
            elif f.resource_type == "SQL_TABLE":
                lines.append(f'  {res_safe}[("{f.resource_id}")]')
            else:
                lines.append(f'  {res_safe}["{f.resource_id}"]')
            nodes_added.add(res_safe)

        if f.direction in ("PRODUCES", "WRITES"):
            lines.append(f"  {mod_safe} -->|{f.direction.lower()}| {res_safe}")
        else:
            lines.append(f"  {res_safe} -->|{f.direction.lower()}| {mod_safe}")

    return "\n".join(lines)
