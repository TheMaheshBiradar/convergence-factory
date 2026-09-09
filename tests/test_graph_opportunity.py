import os
import shutil
import tempfile
import unittest

from convergence_factory import graph
from convergence_factory.schema import IntegrationFact, Module, ModuleMetric, Project, Provenance
from convergence_factory.store import Store


class TestGraphOpportunity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.store = Store(self.db_path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_store_metrics(self):
        metrics = [
            ModuleMetric(module_id="mod1:python", name="coupling", value=0.25),
            ModuleMetric(module_id="mod2:python", name="coupling", value=0.75),
        ]
        self.store.add_metrics(metrics)
        res = self.store.metrics_by_name("coupling")
        self.assertEqual(res.get("mod1:python"), 0.25)
        self.assertEqual(res.get("mod2:python"), 0.75)

    def test_opportunity_discounted_by_coupling(self):
        # Register projects
        p1 = Project(id="proj1", repo_url="/p1", langs=["python"], owner_team="team-a")
        p2 = Project(id="proj2", repo_url="/p2", langs=["python"], owner_team="team-a")
        p3 = Project(id="proj3", repo_url="/p3", langs=["python"], owner_team="team-b")
        p4 = Project(id="proj4", repo_url="/p4", langs=["python"], owner_team="team-b")
        for p in [p1, p2, p3, p4]:
            self.store.add_project(p)

        m1 = Module(id="proj1:python", project_id="proj1", path="/p1", name="p1", kind="service", lang="python")
        m2 = Module(id="proj2:python", project_id="proj2", path="/p2", name="p2", kind="service", lang="python")
        m3 = Module(id="proj3:python", project_id="proj3", path="/p3", name="p3", kind="service", lang="python")
        m4 = Module(id="proj4:python", project_id="proj4", path="/p4", name="p4", kind="service", lang="python")
        for m in [m1, m2, m3, m4]:
            self.store.add_module(m)

        # Cluster 1: clean/decoupled duplicates (coupling = 0.0)
        # Cluster 2: heavily entangled duplicates (coupling = 0.8)
        prov = Provenance(file="a.py", line=1, snippet="")
        facts = [
            IntegrationFact(module_id="proj1:python", direction="PRODUCES", resource_type="KAFKA_TOPIC", resource_id="topic.clean", tier="HIGH", provenance=prov),
            IntegrationFact(module_id="proj2:python", direction="PRODUCES", resource_type="KAFKA_TOPIC", resource_id="topic.clean", tier="HIGH", provenance=prov),
            IntegrationFact(module_id="proj3:python", direction="PRODUCES", resource_type="KAFKA_TOPIC", resource_id="topic.entangled", tier="HIGH", provenance=prov),
            IntegrationFact(module_id="proj4:python", direction="PRODUCES", resource_type="KAFKA_TOPIC", resource_id="topic.entangled", tier="HIGH", provenance=prov),
        ]
        self.store.add_integration(facts)

        # Set coupling metrics
        self.store.add_metrics([
            ModuleMetric(module_id="proj1:python", name="coupling", value=0.0),
            ModuleMetric(module_id="proj2:python", name="coupling", value=0.0),
            ModuleMetric(module_id="proj3:python", name="coupling", value=0.8),
            ModuleMetric(module_id="proj4:python", name="coupling", value=0.8),
        ])

        g = graph.build(self.store)
        clusters = g["clusters"]
        self.assertEqual(len(clusters), 2)

        # Both have identical raw score: 1 shared resource * 2 members + 2 (dup producer) = 4
        # Clean cluster: opportunity = 4 * (1 - 0.0) = 4.0
        # Entangled cluster: opportunity = 4 * (1 - 0.8) = 0.8
        clean_cl = next(c for c in clusters if ("KAFKA_TOPIC", "topic.clean") in c["shared"])
        entangled_cl = next(c for c in clusters if ("KAFKA_TOPIC", "topic.entangled") in c["shared"])

        self.assertEqual(clean_cl["score"], 4)
        self.assertEqual(clean_cl["coupling"], 0.0)
        self.assertEqual(clean_cl["opportunity"], 4.0)

        self.assertEqual(entangled_cl["score"], 4)
        self.assertEqual(entangled_cl["coupling"], 0.8)
        self.assertEqual(entangled_cl["opportunity"], 0.8)

        # Clean cluster must rank first
        self.assertEqual(clusters[0], clean_cl)
        self.assertEqual(clusters[1], entangled_cl)


if __name__ == "__main__":
    unittest.main()
