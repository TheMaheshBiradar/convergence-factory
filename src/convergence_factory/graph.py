"""M0.4 (graph build) + M1.6 (clustering & scoring).

The graph is DERIVED from integration facts, not authored: modules that touch the
same (resource_type, resource_id) are linked. Two producers of the same Kafka
topic, or two writers of the same table, get a stronger edge. Connected
components become capability clusters, each scored for convergence opportunity
and tagged with a play.

Only the signals we can actually compute today drive the score (overlap,
ownership fragmentation). Drift and coupling are Phase-2 signals and are reported
as such rather than faked.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Dict, List

from .store import Store

_TIER_RANK = {"HIGH": 3, "MED": 2, "LOW": 1}


class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(b)] = self.find(a)


def _edge_type(dir_a: str, dir_b: str, rtype: str) -> str:
    if rtype == "KAFKA_TOPIC" and dir_a == "PRODUCES" and dir_b == "PRODUCES":
        return "DUP_PRODUCER"
    if rtype == "SQL_TABLE" and dir_a == "WRITES" and dir_b == "WRITES":
        return "DUP_WRITER"
    return "SHARES_RESOURCE"


def build(store: Store) -> dict:
    facts = store.integration_facts()
    owner = store.module_owner()

    # group module touches by resource
    resources: Dict[tuple, list] = defaultdict(list)
    for f in facts:
        resources[(f.resource_type, f.resource_id)].append(
            (f.module_id, f.direction, f.tier))

    edges: List[dict] = []
    uf = _UnionFind()
    for (rtype, rid), touches in resources.items():
        modules = {m for m, _d, _t in touches}
        if len(modules) < 2:
            continue
        by_mod = {}
        for m, d, t in touches:
            # keep the strongest-tier touch per module for this resource
            if m not in by_mod or _TIER_RANK[t] > _TIER_RANK[by_mod[m][1]]:
                by_mod[m] = (d, t)
        for a, b in combinations(sorted(by_mod), 2):
            dir_a, tier_a = by_mod[a]
            dir_b, tier_b = by_mod[b]
            # a link is only as strong as its weaker end
            link_tier = "HIGH" if _TIER_RANK[tier_a] == _TIER_RANK[tier_b] == 3 \
                else min((tier_a, tier_b), key=lambda t: _TIER_RANK[t])
            edges.append({
                "a": a, "b": b, "type": _edge_type(dir_a, dir_b, rtype),
                "resource_type": rtype, "resource_id": rid, "tier": link_tier})
            uf.union(a, b)

    # connected components -> clusters
    comps: Dict[str, list] = defaultdict(list)
    nodes = {n for e in edges for n in (e["a"], e["b"])}
    for n in nodes:
        comps[uf.find(n)].append(n)

    clusters = []
    for root, members in comps.items():
        cl_edges = [e for e in edges if e["a"] in members and e["b"] in members]
        shared = sorted({(e["resource_type"], e["resource_id"]) for e in cl_edges})
        owners = sorted({owner.get(m, "unknown") for m in members})
        best_tier = max((e["tier"] for e in cl_edges), key=lambda t: _TIER_RANK[t])
        tier_mix = sorted({e["tier"] for e in cl_edges}, key=lambda t: -_TIER_RANK[t])
        has_dup = any(e["type"] in ("DUP_PRODUCER", "DUP_WRITER") for e in cl_edges)
        score = len(shared) * len(members) + (2 if has_dup else 0)
        clusters.append({
            "members": sorted(members), "owners": owners, "shared": shared,
            "edges": cl_edges, "tier": best_tier, "tier_mix": tier_mix,
            "score": score, "play": _play(has_dup, owners, cl_edges),
            "label": _label(cl_edges),
        })
    clusters.sort(key=lambda c: (-c["score"], -_TIER_RANK[c["tier"]]))
    return {"clusters": clusters, "edges": edges, "resource_count": len(resources)}


def _play(has_dup: bool, owners: List[str], edges: List[dict]) -> str:
    single_owner = len(owners) == 1
    if has_dup and single_owner:
        return "RETIRE"          # true duplicate, one team can consolidate
    if has_dup and not single_owner:
        return "STANDARDIZE"     # same function across teams -> pick a canonical
    if any(e["type"] == "SHARES_RESOURCE" for e in edges):
        return "EXTRACT"         # shared data/utility -> shared library/service
    return "LEAVE"


def _label(edges: List[dict]) -> str:
    dup_prod = [e for e in edges if e["type"] == "DUP_PRODUCER"]
    dup_write = [e for e in edges if e["type"] == "DUP_WRITER"]
    if dup_prod:
        return f"Publishes event · {dup_prod[0]['resource_id']}"
    if dup_write:
        return f"Writes table · {dup_write[0]['resource_id']}"
    e = edges[0]
    kind = "topic" if e["resource_type"] == "KAFKA_TOPIC" else \
        "table" if e["resource_type"] == "SQL_TABLE" else "endpoint"
    return f"Shares {kind} · {e['resource_id']}"
