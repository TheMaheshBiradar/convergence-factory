import os
import shutil
import tempfile
import unittest

from convergence_factory.schema import IntegrationFact, Module, Project, Provenance
from convergence_factory.store import Store
from pipelines.flow import compute_repo_hash, run_pipeline


class TestFlowCaching(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.repos_dir = os.path.join(self.temp_dir, "repos")
        self.out_dir = os.path.join(self.temp_dir, "out")
        os.makedirs(self.repos_dir)

        # Create 2 simple sample repos
        self.r1 = os.path.join(self.repos_dir, "repo1")
        os.makedirs(self.r1)
        with open(os.path.join(self.r1, "OWNER"), "w") as f:
            f.write("team-1\n")
        with open(os.path.join(self.r1, "app.py"), "w") as f:
            f.write("import os\n")

        self.r2 = os.path.join(self.repos_dir, "repo2")
        os.makedirs(self.r2)
        with open(os.path.join(self.r2, "OWNER"), "w") as f:
            f.write("team-2\n")
        with open(os.path.join(self.r2, "app.py"), "w") as f:
            f.write("import sys\n")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_compute_repo_hash(self):
        h1 = compute_repo_hash(self.r1)
        self.assertIsInstance(h1, str)
        self.assertEqual(len(h1), 64)

        # Modifying a file changes hash
        with open(os.path.join(self.r1, "app.py"), "a") as f:
            f.write("x = 10\n")
        h2 = compute_repo_hash(self.r1)
        self.assertNotEqual(h1, h2)

    def test_incremental_caching_flow(self):
        # Run 1: cold start -> both extracted
        res1 = run_pipeline(self.repos_dir, self.out_dir, use_cache=True)
        stats1 = res1["pipeline_stats"]
        self.assertEqual(stats1["total_scans"], 2)
        self.assertEqual(stats1["extracted"], 2)
        self.assertEqual(stats1["cached"], 0)

        # Run 2: no changes -> both cached
        res2 = run_pipeline(self.repos_dir, self.out_dir, use_cache=True)
        stats2 = res2["pipeline_stats"]
        self.assertEqual(stats2["total_scans"], 2)
        self.assertEqual(stats2["extracted"], 0)
        self.assertEqual(stats2["cached"], 2)

        # Modify repo1 only
        with open(os.path.join(self.r1, "new_file.py"), "w") as f:
            f.write("def foo(): pass\n")

        # Run 3: repo1 re-extracted, repo2 cached
        res3 = run_pipeline(self.repos_dir, self.out_dir, use_cache=True)
        stats3 = res3["pipeline_stats"]
        self.assertEqual(stats3["total_scans"], 2)
        self.assertEqual(stats3["extracted"], 1)
        self.assertEqual(stats3["cached"], 1)

    def test_store_clear_project(self):
        db_path = os.path.join(self.temp_dir, "test_clear.db")
        store = Store(db_path)
        p = Project(id="p1", repo_url="/p1", name="p1")
        m = Module(id="p1:py", project_id="p1", path="/p1", name="p1")
        f = IntegrationFact(module_id="p1:py", direction="PRODUCES", resource_type="KAFKA_TOPIC", resource_id="t", tier="HIGH", provenance=Provenance(file="a.py"))
        store.add_project(p)
        store.add_module(m)
        store.add_integration([f])
        self.assertEqual(len(store.projects()), 1)
        self.assertEqual(len(store.modules()), 1)
        self.assertEqual(len(store.integration_facts()), 1)

        store.clear_project("p1")
        self.assertEqual(len(store.projects()), 0)
        self.assertEqual(len(store.modules()), 0)
        self.assertEqual(len(store.integration_facts()), 0)
        store.close()


if __name__ == "__main__":
    unittest.main()
