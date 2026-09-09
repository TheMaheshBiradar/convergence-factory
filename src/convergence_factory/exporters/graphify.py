"""Graphify & Cytoscape graph.json exporter for visual convergence inspection."""
from __future__ import annotations

import json
from typing import Any, Dict, List
from convergence_factory.core.store import Store


def build_graph_data(store: Store, clusters: List[dict]) -> Dict[str, Any]:
    """Extracts node-edge network data suitable for Cytoscape, Graphify, and D3."""
    nodes = {}
    edges_list = []
    for m in store.modules():
        nodes[m.id] = {"id": m.id, "label": m.name, "type": "module", "lang": m.lang}
    for f in store.integration_facts():
        res_key = f"{f.resource_type}:{f.resource_id}"
        if res_key not in nodes:
            nodes[res_key] = {"id": res_key, "label": f.resource_id, "type": "resource", "resource_type": f.resource_type}
        src = f.module_id if f.direction in ("PRODUCES", "WRITES") else res_key
        tgt = res_key if f.direction in ("PRODUCES", "WRITES") else f.module_id
        edges_list.append({"source": src, "target": tgt, "direction": f.direction, "tier": f.tier})

    return {"nodes": list(nodes.values()), "edges": edges_list, "clusters": clusters}


def export_graph_json(store: Store, clusters: List[dict], out_path: str) -> str:
    """Exports node-edge network data to a graph.json file."""
    data = build_graph_data(store, clusters)
    with open(out_path, "w", encoding="utf-8") as gfh:
        json.dump(data, gfh, indent=2)
    return out_path
