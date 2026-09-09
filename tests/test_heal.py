import os
import shutil
import tempfile
import unittest

from convergence_factory import census, graph
from convergence_factory.heal import heal_cluster, run_self_healing
from convergence_factory.runner import extract
from convergence_factory.store import Store


class TestSelfHealing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.r1 = os.path.join(self.temp_dir, "order-service")
        self.r2 = os.path.join(self.temp_dir, "billing-service")
        os.makedirs(self.r1)
        os.makedirs(self.r2)

        # repo 1: Python service producing "payment.executed"
        with open(os.path.join(self.r1, "OWNER"), "w") as f:
            f.write("team-orders\n")
        with open(os.path.join(self.r1, "app.py"), "w") as f:
            f.write('from confluent_kafka import Producer\n\nTOPIC = "payment.executed"\n\ndef emit(p, data):\n    p.produce(TOPIC, data)\n')

        # repo 2: Python service also producing "payment.executed"
        with open(os.path.join(self.r2, "OWNER"), "w") as f:
            f.write("team-billing\n")
        with open(os.path.join(self.r2, "app.py"), "w") as f:
            f.write('from confluent_kafka import Producer\n\nTOPIC = "payment.executed"\n\ndef emit(p, data):\n    p.produce(TOPIC, data)\n')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_self_healing(self):
        # 1. Before healing: 1 cluster exists
        store = Store(":memory:")
        for s in census.scan(self.temp_dir):
            extract(store, s)
        g = graph.build(store)
        self.assertEqual(len(g["clusters"]), 1)
        cluster = g["clusters"][0]
        self.assertEqual(cluster["play"], "STANDARDIZE")
        self.assertGreater(cluster["opportunity"], 0.0)
        store.close()

        # 2. Run automated self-healing
        report = run_self_healing(self.temp_dir)
        self.assertEqual(report.initial_clusters, 1)
        self.assertEqual(report.remaining_clusters, 0)
        self.assertTrue(report.all_healed)
        self.assertGreater(report.total_recovered, 0.0)

        # 3. Verify one service became canonical and the duplicate was decommissioned
        with open(os.path.join(self.r1, "app.py")) as f:
            content1 = f.read()
        with open(os.path.join(self.r2, "app.py")) as f:
            content2 = f.read()

        combined = content1 + content2
        self.assertIn("canonical.payment.executed", combined)
        self.assertIn("[CONVERGED: retired duplicate publisher", combined)

        # 4. Verify ratchets were installed into the repositories
        self.assertTrue(os.path.exists(os.path.join(self.r1, ".importlinter")))
        self.assertTrue(os.path.exists(os.path.join(self.r2, ".importlinter")))


if __name__ == "__main__":
    unittest.main()
