"""Tests for the orchestrator, the matrix view, the bipartite graph, and the
portfolio-probe registry."""
import os

from convergence_factory import pipeline
from convergence_factory.core.capability import Capability
from convergence_factory.core.interfaces import PipelineConfig
from convergence_factory.exporters import matrix as matrix_view
from convergence_factory.exporters.graphify import build_capability_graph
from convergence_factory.probes.registry import FACT_PROBES, REPORT_PROBES

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIX = os.path.join(_REPO, "fixtures", "repos")


def test_pipeline_runs_all_stages_on_fixtures(tmp_path):
    out = str(tmp_path / "out")
    summary = pipeline.run(PipelineConfig(root=_FIX, out=out, semantic=False))
    assert summary["projects"] >= 3
    assert summary["capabilities"] > 0
    assert os.path.exists(summary["matrix_html"])
    assert os.path.exists(os.path.join(out, "site", "capability-graph.json"))


def test_capability_graph_is_bipartite():
    caps = [Capability(
        id="messaging:t", dimension="messaging", label="Publishes t",
        members=[{"module": "a:py", "direction": "PRODUCES", "tier": "HIGH"},
                 {"module": "b:py", "direction": "PRODUCES", "tier": "HIGH"}],
        tier="HIGH")]
    g = build_capability_graph(caps)
    assert g["bipartite"] is True
    assert {n["type"] for n in g["nodes"]} == {"module", "capability"}
    assert all(e["target"].startswith("cap::") for e in g["edges"])  # module -> capability only


def test_matrix_render_writes_scannable_grid(tmp_path):
    caps = [Capability(
        id="data:customers", dimension="data", label="Writes customers",
        members=[{"module": "a:py", "direction": "WRITES", "tier": "HIGH"},
                 {"module": "b:sql", "direction": "WRITES", "tier": "HIGH"}],
        tier="HIGH", play="STANDARDIZE", opportunity=4.0)]
    res = matrix_view.render(caps, str(tmp_path / "o"))
    assert res["capabilities"] == 1
    assert os.path.exists(res["matrix_html"])
    assert "customers" in open(res["matrix_html"], encoding="utf-8").read()


def test_portfolio_probe_registry_is_populated():
    fact_names = {n for n, _ in FACT_PROBES}
    report_names = {n for n, _ in REPORT_PROBES}
    assert {"api", "clones"} <= fact_names
    assert {"bom", "schema"} <= report_names
