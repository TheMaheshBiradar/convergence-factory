"""Stage 3 + 4 — the Capability model and findings. The analytical spine.

A *capability* is one thing that >=2 modules share, in ONE dimension. This
REPLACES the old "union every shared resource into giant connected components"
step: instead of merging a topic edge + a table edge + a clone edge into one
blob, each shared resource (or each semantic / clone cluster) is its own
capability with its own members and its own dimension. Reading a capability's
members is a duplication finding, scoped and rankable.

`build_capabilities(store, semantic_pairs=...)` returns the capability set; the
modules x capabilities matrix and the bipartite graph are just two renderings of
it (see exporters/matrix.py and exporters/graphify.py).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .store import Store

_TIER_RANK = {"HIGH": 3, "MED": 2, "LOW": 1}

# resource_type -> dimension
_DIM = {
    "KAFKA_TOPIC": "messaging", "JMS_QUEUE": "messaging",
    "SQL_TABLE": "data", "SQL_COLUMN": "column",
    "HTTP_ENDPOINT": "api", "CACHE_KEY": "cache",
}


@dataclass
class Capability:
    id: str                       # e.g. "messaging:order.created"
    dimension: str                # messaging|data|column|api|code|functional|dependency|cache
    label: str
    members: List[dict] = field(default_factory=list)   # {module, direction, tier}
    tier: str = "LOW"
    play: str = "LEAVE"
    opportunity: float = 0.0
    owners: List[str] = field(default_factory=list)
    coupling: Optional[float] = None

    @property
    def module_ids(self) -> List[str]:
        return sorted({m["module"] for m in self.members})

    def as_dict(self) -> dict:
        return {"id": self.id, "dimension": self.dimension, "label": self.label,
                "members": self.members, "tier": self.tier, "play": self.play,
                "opportunity": self.opportunity, "owners": self.owners,
                "coupling": self.coupling, "member_count": len(self.module_ids)}


class _UnionFind:
    def __init__(self):
        self.p: Dict[str, str] = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(b)] = self.find(a)


def _best_tier(members: List[dict]) -> str:
    return max((m["tier"] for m in members), key=lambda t: _TIER_RANK.get(t, 0), default="LOW")


def _label(dim: str, rid: str, members: List[dict]) -> str:
    dirs = {m["direction"] for m in members}
    if dim == "messaging":
        return f"Publishes {rid}" if dirs == {"PRODUCES"} else f"Topic {rid}"
    if dim == "data":
        return f"Writes {rid}" if dirs == {"WRITES"} else f"Table {rid}"
    if dim == "column":
        return f"Column {rid}"
    if dim == "api":
        return f"Serves {rid}" if dirs == {"SERVES"} else f"Endpoint {rid}"
    return f"{dim}:{rid}"


def _finalize(cap: Capability, owner: Dict[str, str],
              coupling_map: Dict[str, float]) -> Capability:
    mods = cap.module_ids
    cap.owners = sorted({owner.get(m, "unknown") for m in mods})
    cm = [coupling_map[m] for m in mods if m in coupling_map]
    cap.coupling = round(sum(cm) / len(cm), 3) if cm else None

    dirs = [m["direction"] for m in cap.members]
    n_write = sum(1 for d in dirs if d == "WRITES")
    n_serve = sum(1 for d in dirs if d == "SERVES")
    is_dup = (
        cap.dimension in ("code", "functional")
        or (cap.dimension == "messaging" and set(dirs) == {"PRODUCES"})
        or (cap.dimension in ("data", "column") and n_write >= 2)
        or (cap.dimension == "api" and n_serve >= 2)
    )
    single_owner = len(cap.owners) == 1
    if is_dup and single_owner:
        cap.play = "RETIRE"
    elif is_dup:
        cap.play = "STANDARDIZE"
    elif cap.dimension == "dependency":
        cap.play = "STANDARDIZE"
    else:
        cap.play = "EXTRACT"

    base = len(mods) + (2 if is_dup else 0)
    cross_team = 1.5 if len(cap.owners) > 1 else 1.0
    tier_w = _TIER_RANK.get(cap.tier, 1) / 3
    cap.opportunity = round(base * (1 - (cap.coupling or 0.0)) * cross_team * tier_w, 2)
    return cap


def _cluster_pairs(pairs: List[Tuple[str, str, str]], dimension: str,
                   label_prefix: str, owner, coupling_map,
                   max_size: Optional[int] = None) -> List[Capability]:
    """Union pairs into components WITHIN a single dimension (never across).

    `max_size` guards against blob formation: a component larger than this is
    almost certainly a lexical-overlap artifact (the heuristic judge confirming
    on shared vocabulary), not a real capability cluster, so it is dropped rather
    than presented as one giant duplicate. Deterministic dimensions pass None.
    """
    if not pairs:
        return []
    uf = _UnionFind()
    tier_of: Dict[Tuple[str, str], str] = {}
    for a, b, t in pairs:
        uf.union(a, b)
        tier_of[tuple(sorted((a, b)))] = t
    comps: Dict[str, set] = defaultdict(set)
    for a, b, _t in pairs:
        comps[uf.find(a)].add(a)
        comps[uf.find(a)].add(b)
    caps = []
    for i, (root, mods) in enumerate(sorted(comps.items())):
        if len(mods) < 2 or (max_size is not None and len(mods) > max_size):
            continue
        # weakest tier across the component's edges = the component's confidence
        etiers = [t for (a, b), t in tier_of.items() if a in mods or b in mods]
        tier = min(etiers, key=lambda t: _TIER_RANK.get(t, 0)) if etiers else "LOW"
        members = [{"module": m, "direction": "SHARES", "tier": tier} for m in sorted(mods)]
        label = f"{label_prefix} · " + ", ".join(m.split(":")[0] for m in sorted(mods)[:3])
        caps.append(_finalize(Capability(
            id=f"{dimension}:{root}#{i}", dimension=dimension, label=label,
            members=members, tier=tier), owner, coupling_map))
    return caps


def build_capabilities(store: Store,
                       semantic_pairs: Optional[List[Tuple[str, str, str]]] = None,
                       functional_max_size: int = 6
                       ) -> List[Capability]:
    """Build every capability >=2 modules share, keyed by dimension.

    semantic_pairs: confirmed (module_a, module_b, tier) tuples from the judge.
    functional_max_size: drop semantic components larger than this (blob guard).
    """
    owner = store.module_owner()
    coupling_map = store.metrics_by_name("coupling")
    caps: List[Capability] = []

    # --- deterministic resource capabilities (messaging/data/column/api/...) ---
    groups: Dict[tuple, list] = defaultdict(list)
    for f in store.integration_facts():
        groups[(f.resource_type, f.resource_id)].append((f.module_id, f.direction, f.tier))
    for (rtype, rid), touches in groups.items():
        by: Dict[str, tuple] = {}
        for m, d, t in touches:
            if m not in by or _TIER_RANK[t] > _TIER_RANK[by[m][1]]:
                by[m] = (d, t)
        if len(by) < 2:
            continue
        members = [{"module": m, "direction": by[m][0], "tier": by[m][1]} for m in sorted(by)]
        dim = _DIM.get(rtype, "other")
        caps.append(_finalize(Capability(
            id=f"{dim}:{rid}", dimension=dim, label=_label(dim, rid, members),
            members=members, tier=_best_tier(members)), owner, coupling_map))

    # --- code clone capabilities ---
    clone_pairs = [(c.module_a, c.module_b, c.tier) for c in store.clone_pairs()]
    caps += _cluster_pairs(clone_pairs, "code", "Code clone", owner, coupling_map)

    # --- functional (semantic, confirmed by the judge) capabilities ---
    # functional (semantic) components are capped: an oversized one means the
    # judge over-confirmed on vocabulary — drop it, don't present a blob.
    caps += _cluster_pairs(semantic_pairs or [], "functional", "Semantic duplicate",
                           owner, coupling_map, max_size=functional_max_size)

    # --- dependency (shared library across >=2 teams) capabilities ---
    dep_mods: Dict[str, set] = defaultdict(set)
    dep_owner: Dict[str, set] = defaultdict(set)
    for r in store.db.execute("SELECT module_id, purl FROM dependencies"):
        name = r["purl"].split("/")[-1].split("@")[0]
        dep_mods[name].add(r["module_id"])
        dep_owner[name].add(owner.get(r["module_id"], "unknown"))
    for name, mods in dep_mods.items():
        if len(mods) >= 2 and len(dep_owner[name]) >= 2:
            members = [{"module": m, "direction": "USES", "tier": "HIGH"} for m in sorted(mods)]
            caps.append(_finalize(Capability(
                id=f"dependency:{name}", dimension="dependency",
                label=f"Shared library {name}", members=members, tier="HIGH"),
                owner, coupling_map))

    caps.sort(key=lambda c: (-c.opportunity, -_TIER_RANK.get(c.tier, 0)))
    return caps


def summarize(caps: List[Capability]) -> dict:
    by_dim: Dict[str, int] = defaultdict(int)
    for c in caps:
        by_dim[c.dimension] += 1
    return {"total": len(caps), "by_dimension": dict(by_dim)}
