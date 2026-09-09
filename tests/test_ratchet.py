import json
import os
import shutil
import tempfile
import unittest

from convergence_factory.ratchet import (
    generate_all_ratchets,
    generate_archunit_rule,
    generate_dependency_cruiser_rule,
    generate_import_linter_contract,
)


class TestRatchetGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sample_cluster = {
            "members": ["svc-inventory:java", "inventory-sync:python"],
            "shared": [("KAFKA_TOPIC", "inventory.updated")],
            "play": "RETIRE",
            "label": "Publishes event · inventory.updated",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_archunit_rule(self):
        rule = generate_archunit_rule(self.sample_cluster)
        self.assertIn("package com.acme.governance;", rule)
        self.assertIn("class ConvergenceRatchetTest", rule)
        self.assertIn("noClasses().should().dependOnClassesThat()", rule)
        self.assertIn("inventory", rule)

    def test_generate_import_linter_contract(self):
        contract = generate_import_linter_contract(self.sample_cluster)
        self.assertIn("[importlinter]", contract)
        self.assertIn("type = forbidden", contract)
        self.assertIn("svc_inventory", contract)

    def test_generate_dependency_cruiser_rule(self):
        rule = generate_dependency_cruiser_rule(self.sample_cluster)
        self.assertEqual(rule["severity"], "error")
        self.assertIn("svc-inventory", rule["name"])
        self.assertIn("svc-inventory", rule["to"]["path"])

    def test_generate_all_ratchets(self):
        clusters = [
            self.sample_cluster,
            {
                "members": ["mod-clean:python"],
                "shared": [],
                "play": "LEAVE",  # LEAVE should not generate ratchets
                "label": "Clean module",
            },
        ]
        res = generate_all_ratchets(clusters, self.temp_dir)
        self.assertEqual(len(res["archunit"]), 1)
        self.assertEqual(len(res["import_linter"]), 1)
        self.assertEqual(len(res["dependency_cruiser"]), 1)

        # Verify files exist on disk
        self.assertTrue(os.path.exists(res["archunit"][0]))
        self.assertTrue(os.path.exists(res["import_linter"][0]))
        self.assertTrue(os.path.exists(res["dependency_cruiser"][0]))

        # Verify JSON validity for dependency cruiser
        with open(res["dependency_cruiser"][0]) as f:
            data = json.load(f)
            self.assertIn("forbidden", data)
            self.assertEqual(len(data["forbidden"]), 1)


if __name__ == "__main__":
    unittest.main()
