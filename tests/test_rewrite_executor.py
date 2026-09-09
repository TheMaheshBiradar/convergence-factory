import os
import shutil
import tempfile
import unittest

from convergence_factory.executors.rewrite import (
    generate_all_rewrite_recipes,
    generate_class_migration_recipe,
    generate_topic_standardization_recipe,
)


class TestRewriteExecutor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sample_clusters = [
            {
                "members": ["java-billing:java", "py-orders:python"],
                "shared": [("KAFKA_TOPIC", "order.created"), ("SQL_TABLE", "customers")],
                "play": "STANDARDIZE",
                "label": "Publishes event · order.created",
            },
            {
                "members": ["svc-inventory:java"],
                "shared": [("KAFKA_TOPIC", "inventory.updated")],
                "play": "LEAVE",  # LEAVE should be skipped
                "label": "Inventory",
            }
        ]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_topic_standardization_recipe(self):
        recipe = generate_topic_standardization_recipe("StandardizeOrder", "order.created", "canonical.order.created")
        self.assertIn("type: specs.openrewrite.org/v1beta/recipe", recipe)
        self.assertIn("org.openrewrite.text.ChangeText:", recipe)
        self.assertIn("toReplace: \"order.created\"", recipe)
        self.assertIn("replacement: \"canonical.order.created\"", recipe)

    def test_class_migration_recipe(self):
        recipe = generate_class_migration_recipe("MigrateClient", "com.legacy.Client", "com.canonical.Client")
        self.assertIn("org.openrewrite.java.ChangeType:", recipe)
        self.assertIn("oldFullyQualifiedTypeName: \"com.legacy.Client\"", recipe)
        self.assertIn("newFullyQualifiedTypeName: \"com.canonical.Client\"", recipe)

    def test_generate_all_rewrite_recipes(self):
        files = generate_all_rewrite_recipes(self.sample_clusters, self.temp_dir)
        self.assertGreaterEqual(len(files), 2)

        # Check topic and table recipes were created
        topic_recipe = next((f for f in files if "order_created" in f), None)
        table_recipe = next((f for f in files if "customers" in f), None)
        runner_sh = next((f for f in files if f.endswith("run_rewrite.sh")), None)

        self.assertIsNotNone(topic_recipe)
        self.assertIsNotNone(table_recipe)
        self.assertIsNotNone(runner_sh)

        self.assertTrue(os.path.exists(topic_recipe))
        self.assertTrue(os.path.exists(table_recipe))
        self.assertTrue(os.path.exists(runner_sh))

        # Check runner is executable
        self.assertTrue(os.access(runner_sh, os.X_OK))


if __name__ == "__main__":
    unittest.main()
