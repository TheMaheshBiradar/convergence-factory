"""The convergence plan — the 'unify to this' target, not just 'these are duplicates'.

Detection (core/capability.py) answers *what overlaps*. This answers *what to
unify into*: for each duplicate capability it names a **canonical** target, the
modules that **converge into** it, and the future unified state; for tech
fragmentation it names the standard library and the outliers to migrate. This is
the bridge from the redundancy map to the target architecture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .store import Store

_TIER = {"HIGH": 3, "MED": 2, "LOW": 1}


@dataclass
class ConvergencePlan:
    capability_id: str
    dimension: str
    label: str
    play: str
    canonical: str            # the surviving target, or "(new shared component)"
    migrate_from: List[str]   # modules that converge into the canonical
    target: str               # one-line description of the unified future state
    rationale: str

    def as_dict(self) -> dict:
        return {"capability_id": self.capability_id, "dimension": self.dimension,
                "label": self.label, "play": self.play, "canonical": self.canonical,
                "migrate_from": self.migrate_from, "target": self.target,
                "rationale": self.rationale}


def _member_tier(cap, module: str) -> str:
    tiers = [m["tier"] for m in cap.members if m["module"] == module]
    return max(tiers, key=lambda t: _TIER.get(t, 0)) if tiers else "LOW"


def _pick_canonical(cap) -> str:
    """The survivor: highest-confidence, least-coupled member (deterministic)."""
    return sorted(
        cap.module_ids,
        key=lambda m: (-_TIER.get(_member_tier(cap, m), 0), cap.coupling or 0.0, m),
    )[0]


def _target(dimension: str, canonical: str) -> str:
    who = canonical.split(":")[0]
    return {
        "messaging": f"One canonical producer ({who}) owns the event; the others consume it.",
        "data": f"One owning service ({who}) writes the table; the others read through it.",
        "column": f"One owning service ({who}) owns the column; the others read through it.",
        "api": f"One service ({who}) serves the endpoint; deprecate + redirect the duplicates.",
        "code": "Extract a shared library; every clone adopts it and the copies are deleted.",
    }.get(dimension, f"Converge on {who}.")


def build_capability_convergence(caps) -> List[ConvergencePlan]:
    plans: List[ConvergencePlan] = []
    for c in caps:
        mods = c.module_ids
        if len(mods) < 2:
            continue
        if c.dimension == "code" or c.play == "EXTRACT":
            # No single owner -> the target is a new shared component.
            canonical = "(new shared component)"
            migrate = mods
            rationale = ("No clear owner: extract a shared library/service and route "
                         "every caller through it.")
        else:
            canonical = _pick_canonical(c)
            migrate = [m for m in mods if m != canonical]
            rationale = (f"Canonical picked by highest confidence tier then lowest "
                         f"coupling: {canonical.split(':')[0]}.")
        plans.append(ConvergencePlan(
            capability_id=c.id, dimension=c.dimension, label=c.label, play=c.play,
            canonical=canonical, migrate_from=migrate,
            target=_target(c.dimension, canonical), rationale=rationale))
    return plans


def build_tech_convergence(store: Store) -> List[dict]:
    """Fragmented tech categories converge on their dominant (standard) library."""
    from .tech import analyze_tech
    tech = analyze_tech(store)
    out = []
    for c in tech["categories"]:
        if c["fragmentation"] > 1:
            out.append({
                "category": c["category"], "canonical": c["standard"],
                "migrate_from_libs": c["outliers"],
                "migrate_from_modules": c["outlier_modules"],
                "target": f"Standardize {c['category']} on {c['standard']}; "
                          f"migrate {', '.join(c['outliers'])}."})
    return out


def build(store: Store, caps) -> dict:
    cap_plans = build_capability_convergence(caps)
    tech_plans = build_tech_convergence(store)
    canonicals = {p.canonical for p in cap_plans}
    migrate_modules = {m for p in cap_plans for m in p.migrate_from}
    rollup = {
        "duplicate_capabilities": len(cap_plans),
        "canonical_targets": len({c for c in canonicals if c != "(new shared component)"}),
        "new_shared_components": sum(1 for p in cap_plans if p.canonical == "(new shared component)"),
        "modules_to_migrate": len(migrate_modules),
        "tech_standardizations": len(tech_plans),
    }
    return {"capability_plans": [p.as_dict() for p in cap_plans],
            "tech_plans": tech_plans, "rollup": rollup}
