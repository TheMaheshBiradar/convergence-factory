import os
import shutil
import tempfile
import unittest

from convergence_factory import graph
from convergence_factory.schema import CapabilitySummary, Module, Project
from convergence_factory.semantic.judge import HeuristicJudge, JudgeResult, judge_candidates
from convergence_factory.store import Store


class TestPairwiseJudge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_judge.db")
        self.store = Store(self.db_path)
        self.judge = HeuristicJudge(confidence_threshold=0.70)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_heuristic_judge_confirmed_same_owner(self):
        cand = {"a": "svc-a", "b": "svc-b", "similarity": 0.82}
        sum_a = "Inventory synchronization and stock tracking service"
        sum_b = "Inventory management and warehouse stock updates"
        res = self.judge.evaluate(cand, sum_a, sum_b, owner_a="team-warehouse", owner_b="team-warehouse")

        self.assertTrue(res.confirmed)
        self.assertGreaterEqual(res.confidence, 0.70)
        self.assertEqual(res.play, "RETIRE")
        self.assertIn("Shares functional domain", res.reason)

    def test_heuristic_judge_confirmed_cross_owner(self):
        cand = {"a": "billing", "b": "checkout", "similarity": 0.76}
        sum_a = "Processes customer order payments and invoices"
        sum_b = "Order processing and customer payment checkout"
        res = self.judge.evaluate(cand, sum_a, sum_b, owner_a="team-billing", owner_b="team-orders")

        self.assertTrue(res.confirmed)
        self.assertEqual(res.play, "STANDARDIZE")

    def test_heuristic_judge_refuted_low_similarity(self):
        cand = {"a": "billing", "b": "analytics", "similarity": 0.35}
        sum_a = "Processes customer order payments and invoices"
        sum_b = "Data warehouse reporting and aggregations"
        res = self.judge.evaluate(cand, sum_a, sum_b, owner_a="team-billing", owner_b="team-data")

        self.assertFalse(res.confirmed)
        self.assertEqual(res.play, "LEAVE")
        self.assertIn("Insufficient capability overlap", res.reason)

    def test_judge_candidates_and_promotion(self):
        p1 = Project(id="p1", repo_url="/p1", owner_team="team-alpha")
        p2 = Project(id="p2", repo_url="/p2", owner_team="team-beta")
        self.store.add_project(p1)
        self.store.add_project(p2)

        m1 = Module(id="p1:srv", project_id="p1", path="/p1", name="srv-a", kind="service", lang="python")
        m2 = Module(id="p2:srv", project_id="p2", path="/p2", name="srv-b", kind="service", lang="python")
        self.store.add_module(m1)
        self.store.add_module(m2)

        self.store.add_summaries([
            CapabilitySummary(module_id="p1:srv", summary="Authenticates users and validates JWT tokens", tier="MED"),
            CapabilitySummary(module_id="p2:srv", summary="User authentication and OAuth JWT token verification", tier="MED"),
        ])

        candidates = [{"a": "p1:srv", "b": "p2:srv", "similarity": 0.85, "tier": "MED"}]
        evaluated = judge_candidates(self.store, candidates, self.judge)
        self.assertEqual(len(evaluated), 1)
        self.assertTrue(evaluated[0]["confirmed"])
        self.assertEqual(evaluated[0]["play"], "STANDARDIZE")

        # Promote candidates into empty graph
        empty_graph = {"clusters": [], "edges": [], "resource_count": 0}
        promoted = graph.promote_candidates(empty_graph, evaluated, self.store)
        self.assertEqual(len(promoted["clusters"]), 1)
        cl = promoted["clusters"][0]
        self.assertIn("p1:srv", cl["members"])
        self.assertIn("p2:srv", cl["members"])
        self.assertEqual(cl["play"], "STANDARDIZE")
        self.assertEqual(cl["tier"], "MED")
        self.assertGreater(cl["opportunity"], 0)


if __name__ == "__main__":
    unittest.main()
