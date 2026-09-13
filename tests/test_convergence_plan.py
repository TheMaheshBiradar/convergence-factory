"""Tests for the convergence plan — the 'unify into this' target."""
from convergence_factory.core.capability import build_capabilities
from convergence_factory.core.convergence import build, build_capability_convergence
from convergence_factory.core.schema import (IntegrationFact, Module, Project,
                                              Provenance)
from convergence_factory.core.store import Store


def _store():
    return Store(":memory:")


def _mod(s, pid, owner):
    s.add_project(Project(id=pid, name=pid, owner_team=owner))
    mid = f"{pid}:py"
    s.add_module(Module(id=mid, project_id=pid, path="/x", name=pid, lang="python"))
    return mid


def _f(mid, d, rt, rid, tier="HIGH"):
    return IntegrationFact(module_id=mid, direction=d, resource_type=rt,
                           resource_id=rid, tier=tier, provenance=Provenance(file="f"))


def test_dup_producer_picks_highest_tier_canonical():
    s = _store()
    a, b = _mod(s, "a", "t1"), _mod(s, "b", "t2")
    s.add_integration([_f(a, "PRODUCES", "KAFKA_TOPIC", "order.created", "HIGH"),
                       _f(b, "PRODUCES", "KAFKA_TOPIC", "order.created", "MED")])
    plans = build_capability_convergence(build_capabilities(s))
    msg = next(p for p in plans if p.dimension == "messaging")
    assert msg.canonical == "a:py"          # HIGH beats MED
    assert msg.migrate_from == ["b:py"]
    assert "canonical producer" in msg.target


def test_extract_targets_a_new_shared_component():
    s = _store()
    a, b = _mod(s, "a", "t1"), _mod(s, "b", "t2")
    s.add_integration([_f(a, "WRITES", "SQL_TABLE", "customers"),
                       _f(b, "READS", "SQL_TABLE", "customers")])
    plans = build_capability_convergence(build_capabilities(s))
    data = next(p for p in plans if p.dimension == "data")
    assert data.play == "EXTRACT"
    assert data.canonical == "(new shared component)"
    assert set(data.migrate_from) == {"a:py", "b:py"}


def test_rollup_counts():
    s = _store()
    a, b = _mod(s, "a", "t1"), _mod(s, "b", "t1")
    s.add_integration([_f(a, "PRODUCES", "KAFKA_TOPIC", "t"),
                       _f(b, "PRODUCES", "KAFKA_TOPIC", "t")])
    r = build(s, build_capabilities(s))["rollup"]
    assert r["duplicate_capabilities"] >= 1
    assert r["modules_to_migrate"] >= 1
