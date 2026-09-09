import os
import shutil
import tempfile
import unittest

from convergence_factory.clone_probe import detect_clones
from convergence_factory import graph
from convergence_factory.schema import Module, Project
from convergence_factory.store import Store


class TestCloneProbe(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_clones.db")
        self.store = Store(self.db_path)

        # Setup 2 projects with Type 1 identical clones
        self.p1_dir = os.path.join(self.temp_dir, "p1")
        self.p2_dir = os.path.join(self.temp_dir, "p2")
        self.p3_dir = os.path.join(self.temp_dir, "p3")
        for d in [self.p1_dir, self.p2_dir, self.p3_dir]:
            os.makedirs(d)

        # p1 and p2 have identical duplicate code
        code_p1 = """
def process_data(records):
    results = []
    for r in records:
        if r.get('valid'):
            results.append(r['value'] * 2)
    return results
"""
        with open(os.path.join(self.p1_dir, "worker.py"), "w") as f:
            f.write(code_p1)
        with open(os.path.join(self.p2_dir, "worker.py"), "w") as f:
            f.write(code_p1)  # Identical

        # p3 has completely different code
        with open(os.path.join(self.p3_dir, "worker.py"), "w") as f:
            f.write("import math\nprint(math.pi)\n")

        self.store.add_project(Project(id="p1", repo_url="/p1", owner_team="team-a"))
        self.store.add_project(Project(id="p2", repo_url="/p2", owner_team="team-a"))
        self.store.add_project(Project(id="p3", repo_url="/p3", owner_team="team-b"))

        self.store.add_module(Module(id="p1:py", project_id="p1", path=self.p1_dir, name="p1", lang="python"))
        self.store.add_module(Module(id="p2:py", project_id="p2", path=self.p2_dir, name="p2", lang="python"))
        self.store.add_module(Module(id="p3:py", project_id="p3", path=self.p3_dir, name="p3", lang="python"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_exact_clone(self):
        clones = detect_clones(self.store, threshold=0.70)
        self.assertEqual(len(clones), 1)
        c = clones[0]
        self.assertIn("p1:py", [c.module_a, c.module_b])
        self.assertIn("p2:py", [c.module_a, c.module_b])
        self.assertEqual(c.clone_type, 1)
        self.assertEqual(c.tier, "HIGH")
        self.assertGreaterEqual(c.similarity, 0.90)

    def test_clone_graph_integration(self):
        detect_clones(self.store, threshold=0.70)
        g = graph.build(self.store)
        self.assertEqual(len(g["clusters"]), 1)
        cl = g["clusters"][0]
        self.assertIn("p1:py", cl["members"])
        self.assertIn("p2:py", cl["members"])
        self.assertEqual(cl["play"], "RETIRE")  # same owner (team-a) -> RETIRE
        self.assertEqual(cl["tier"], "HIGH")
        self.assertIn("Code clone", cl["label"])


if __name__ == "__main__":
    unittest.main()
