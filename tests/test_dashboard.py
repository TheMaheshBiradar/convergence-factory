"""Tests for the portfolio dashboard exporter."""
import os

from convergence_factory.core.capability import build_capabilities
from convergence_factory.core.convergence import build as build_convergence
from convergence_factory.core.schema import (IntegrationFact, Module, Project,
                                              Provenance)
from convergence_factory.core.store import Store
from convergence_factory.core.tech import analyze_tech
from convergence_factory.exporters import dashboard


def _store():
    s = Store(":memory:")
    for pid, owner in [("a", "t1"), ("b", "t2")]:
        s.add_project(Project(id=pid, name=pid, owner_team=owner))
        s.add_module(Module(id=f"{pid}:py", project_id=pid, path="/x", name=pid, lang="python"))
    s.add_integration([
        IntegrationFact("a:py", "PRODUCES", "KAFKA_TOPIC", "order.created", "HIGH", Provenance("f")),
        IntegrationFact("b:py", "PRODUCES", "KAFKA_TOPIC", "order.created", "HIGH", Provenance("f"))])
    return s


def test_dashboard_renders_and_embeds_data(tmp_path):
    s = _store()
    caps = build_capabilities(s)
    res = dashboard.render(caps, build_convergence(s, caps), analyze_tech(s), s,
                           str(tmp_path / "o"))
    assert os.path.exists(res["dashboard_html"])
    html = open(res["dashboard_html"], encoding="utf-8").read()
    assert "Portfolio" in html and "order.created" in html
    assert "/*__DATA__*/null" not in html          # placeholder replaced with data
    assert '"capabilities"' in html and '"stats"' in html
