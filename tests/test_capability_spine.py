"""Tests for the capability spine (core/capability.py) — the stage-3 model."""
from convergence_factory.core.capability import build_capabilities
from convergence_factory.core.schema import (IntegrationFact, Module, Project,
                                              Provenance)
from convergence_factory.core.store import Store


def _store():
    return Store(":memory:")


def _mod(s, pid, owner, suffix="py", lang="python"):
    s.add_project(Project(id=pid, name=pid, owner_team=owner))
    m = Module(id=f"{pid}:{suffix}", project_id=pid, path="/x", name=pid, lang=lang)
    s.add_module(m)
    return m.id


def _fact(mid, direction, rtype, rid, tier="HIGH"):
    return IntegrationFact(module_id=mid, direction=direction, resource_type=rtype,
                           resource_id=rid, tier=tier, provenance=Provenance(file="f"))


def test_cross_team_dup_producer_is_standardize():
    s = _store()
    a, b = _mod(s, "a", "team-1"), _mod(s, "b", "team-2")
    s.add_integration([_fact(a, "PRODUCES", "KAFKA_TOPIC", "order.created"),
                       _fact(b, "PRODUCES", "KAFKA_TOPIC", "order.created")])
    caps = build_capabilities(s)
    msg = [c for c in caps if c.dimension == "messaging"]
    assert len(msg) == 1
    assert set(msg[0].module_ids) == {a, b}
    assert msg[0].play == "STANDARDIZE"


def test_single_owner_dup_is_retire():
    s = _store()
    a, b = _mod(s, "a", "team-1"), _mod(s, "b", "team-1")
    s.add_integration([_fact(a, "PRODUCES", "KAFKA_TOPIC", "t"),
                       _fact(b, "PRODUCES", "KAFKA_TOPIC", "t")])
    caps = build_capabilities(s)
    assert caps and caps[0].play == "RETIRE"


def test_single_module_resource_is_not_a_capability():
    s = _store()
    a = _mod(s, "a", "t1")
    s.add_integration([_fact(a, "PRODUCES", "KAFKA_TOPIC", "solo")])
    assert build_capabilities(s) == []


def test_dimensions_stay_separate_not_a_blob():
    s = _store()
    a, b = _mod(s, "a", "t1"), _mod(s, "b", "t2")
    s.add_integration([_fact(a, "PRODUCES", "KAFKA_TOPIC", "tp"),
                       _fact(b, "PRODUCES", "KAFKA_TOPIC", "tp"),
                       _fact(a, "WRITES", "SQL_TABLE", "tbl"),
                       _fact(b, "WRITES", "SQL_TABLE", "tbl")])
    caps = build_capabilities(s)
    dims = {c.dimension for c in caps}
    assert "messaging" in dims and "data" in dims
    assert len(caps) >= 2   # two dimensions, two capabilities — not one merged blob


def test_functional_blob_guard_drops_oversized_component():
    s = _store()
    ids = [_mod(s, f"m{i}", f"t{i % 3}") for i in range(10)]
    big = [(ids[i], ids[j], "LOW") for i in range(len(ids)) for j in range(i + 1, len(ids))]
    caps = build_capabilities(s, semantic_pairs=big, functional_max_size=6)
    assert [c for c in caps if c.dimension == "functional"] == []
    small = build_capabilities(s, semantic_pairs=[(ids[0], ids[1], "LOW")],
                               functional_max_size=6)
    assert any(c.dimension == "functional" for c in small)
