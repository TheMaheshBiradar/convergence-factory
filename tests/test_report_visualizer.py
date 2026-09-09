import os
import shutil
import tempfile
import unittest

from convergence_factory.report import generate_mermaid_diagram, render
from convergence_factory.schema import IntegrationFact, Module, Project, Provenance
from convergence_factory.store import Store


class TestReportVisualizer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_report.db")
        self.store = Store(self.db_path)

        p = Project(id="p1", repo_url="/p1", owner_team="team-a")
        self.store.add_project(p)
        m = Module(id="p1:srv", project_id="p1", path="/p1", name="srv-a", lang="python")
        self.store.add_module(m)

        f = IntegrationFact(
            module_id="p1:srv", direction="PRODUCES",
            resource_type="KAFKA_TOPIC", resource_id="events.order",
            tier="HIGH", provenance=Provenance(file="app.py")
        )
        self.store.add_integration([f])

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_mermaid_diagram(self):
        diag = generate_mermaid_diagram(self.store, [])
        self.assertIn("graph LR", diag)
        self.assertIn("p1_srv", diag)
        self.assertIn("events_order", diag)
        self.assertIn("-->|produces|", diag)

    def test_render_interactive_elements(self):
        graph = {
            "clusters": [{
                "members": ["p1:srv"],
                "owners": ["team-a"],
                "shared": [("KAFKA_TOPIC", "events.order")],
                "tier": "HIGH",
                "tier_mix": ["HIGH"],
                "score": 4,
                "coupling": 0.0,
                "opportunity": 4.0,
                "play": "STANDARDIZE",
                "label": "Publishes event · events.order"
            }],
            "edges": []
        }
        res = render(self.store, graph, [], self.temp_dir)
        self.assertTrue(os.path.exists(res["site"]))

        with open(res["site"]) as fh:
            content = fh.read()
            self.assertIn("mermaid", content)
            self.assertIn("filterSearch", content)
            self.assertIn("events.order", content)
            self.assertIn("STANDARDIZE", content)


if __name__ == "__main__":
    unittest.main()
