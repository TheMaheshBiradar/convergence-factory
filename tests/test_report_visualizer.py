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
            self.assertIn("maxTextSize: 5000000", content)
            self.assertIn("filterSearch", content)
            self.assertIn("events.order", content)
            self.assertIn("STANDARDIZE", content)

            # Assert intuitive column headers requested by user
            self.assertIn("Why Matched?", content)
            self.assertIn("How Decided?", content)
            self.assertIn("What Is Next Step?", content)

            # Assert column trimming and tooltips
            self.assertIn("trim-col", content)
            self.assertIn("data-tip=", content)
            self.assertIn("id=\"floating-tooltip\"", content)

            # Assert expandable accordion deep dive
            self.assertIn("id=\"detail-1\"", content)
            self.assertIn("Why Did These Match?", content)
            self.assertIn("How Was This Decided?", content)
            self.assertIn("What Is The Next Step?", content)

            # Assert error.txt integration and diagnostics link
            self.assertIn("href=\"error.txt\"", content)
            self.assertIn("Framework Issues", content)

            # Assert Export graph.json button is present
            self.assertIn("href=\"graph.json\"", content)
            self.assertIn("Export graph.json", content)

        # Assert site/error.txt exists
        site_error_file = os.path.join(os.path.dirname(res["site"]), "error.txt")
        self.assertTrue(os.path.exists(site_error_file))

    def test_second_table_excludes_self_mapping_to_own_project(self):
        """Verify that candidate table rejects self-mappings within the same project."""
        p2 = Project(id="p2", repo_url="/p2", owner_team="team-b")
        self.store.add_project(p2)

        # Module in same project p1
        m_same = Module(id="p1:client", project_id="p1", path="/p1/client", name="srv-a", lang="javascript")
        # Module in different project p2
        m_diff = Module(id="p2:srv", project_id="p2", path="/p2", name="srv-b", lang="python")
        self.store.add_module(m_same)
        self.store.add_module(m_diff)

        candidates = [
            # Self mapping (same project p1)
            {"a": "p1:srv", "b": "p1:client", "similarity": 0.95, "tier": "HIGH"},
            # Cross project mapping (p1 and p2)
            {"a": "p1:srv", "b": "p2:srv", "similarity": 0.88, "tier": "HIGH"},
        ]
        res = render(self.store, {"clusters": []}, candidates, self.temp_dir)
        with open(res["site"]) as fh:
            html_text = fh.read()

        # The candidate table should contain cross-project pair p1 <-> p2
        self.assertIn("srv-b", html_text)
        # The candidate table should NOT contain self-mapping p1:srv <-> p1:client
        # which would have displayed as srv-a <-> srv-a
        cand_section = html_text.split('<table id="candidates">')[1]
        self.assertNotIn("srv-a</b> &harr; <b>srv-a", cand_section)



    def test_mermaid_deduplication_and_budget(self):
        """Verify identical facts are deduplicated into single edges and edge budget triggers Estate Summary."""
        # Add 10 duplicate facts from same module to same topic
        dups = [
            IntegrationFact(
                module_id="p1:srv", direction="PRODUCES",
                resource_type="KAFKA_TOPIC", resource_id="events.order",
                tier="HIGH", provenance=Provenance(file=f"file_{i}.py")
            )
            for i in range(10)
        ]
        self.store.add_integration(dups)

        # Generate diagram with max_edges=1
        diag = generate_mermaid_diagram(self.store, [], max_edges=1)
        # Should only have 1 produces edge, not 10
        edge_count = diag.count("-->|produces|")
        self.assertEqual(edge_count, 1)

        # Now add 5 distinct facts and check max_edges budget notice
        distinct_facts = [
            IntegrationFact(
                module_id="p1:srv", direction="CALLS",
                resource_type="HTTP_ENDPOINT", resource_id=f"/api/v1/resource/{i}",
                tier="MED", provenance=Provenance(file="client.py")
            )
            for i in range(5)
        ]
        self.store.add_integration(distinct_facts)
        budget_diag = generate_mermaid_diagram(self.store, [], max_edges=3)
        self.assertIn("Estate Summary", budget_diag)
        self.assertIn("Showing top 3 core shared resources", budget_diag)

    def test_mermaid_special_characters_sanitization(self):
        """Verify complex URLs with query params, braces, and quotes do not break Mermaid syntax."""
        f = IntegrationFact(
            module_id="p1:srv", direction="CALLS",
            resource_type="HTTP_ENDPOINT", resource_id="/api/orders/{id}?active=true&sort=\"desc\"",
            tier="LOW", provenance=Provenance(file="api.py")
        )
        self.store.add_integration([f])
        diag = generate_mermaid_diagram(self.store, [])
        # Quotes should be escaped or stripped in label
        self.assertNotIn('sort="desc"', diag)
        self.assertIn("sort='desc'", diag)


if __name__ == "__main__":
    unittest.main()
