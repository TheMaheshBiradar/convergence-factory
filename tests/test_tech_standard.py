"""Tests for the tech-standard analysis (core/tech.py)."""
from convergence_factory.core.schema import Dependency, Module, Project
from convergence_factory.core.store import Store
from convergence_factory.core.tech import analyze_tech, summarize


def _store_with_libs():
    s = Store(":memory:")
    rows = [("a", "python", "kafka-python"), ("b", "java", "spring-kafka"),
            ("c", "javascript", "kafkajs"), ("d", "python", "kafka-python")]
    for pid, lang, lib in rows:
        s.add_project(Project(id=pid, name=pid, owner_team="t"))
        mid = f"{pid}:{lang[:2]}"
        s.add_module(Module(id=mid, project_id=pid, path="/x", name=pid, lang=lang))
        s.add_dependencies([Dependency(module_id=mid, purl=f"pkg:x/{lib}", scope="runtime")])
    return s


def test_finds_standard_and_outliers():
    t = analyze_tech(_store_with_libs())
    msg = [c for c in t["categories"] if c["category"] == "messaging client"]
    assert msg, "messaging client category should be detected"
    c = msg[0]
    assert c["standard"] == "kafka-python"          # used by 2 modules -> dominant
    assert c["fragmentation"] == 3                   # 3 distinct libs
    assert set(c["outliers"]) == {"kafkajs", "spring-kafka"}
    assert set(t["languages"]) == {"python", "java", "javascript"}


def test_summarize_flags_fragmentation():
    s = summarize(analyze_tech(_store_with_libs()))
    assert "messaging client" in s["fragmented_categories"]
    assert s["standards"]["messaging client"] == "kafka-python"
