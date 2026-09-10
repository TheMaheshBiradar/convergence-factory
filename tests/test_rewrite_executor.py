import os
import shutil
import tempfile
import unittest

from convergence_factory.executors.rewrite import (
    generate_all_rewrite_recipes,
    generate_class_migration_recipe,
    generate_endpoint_standardization_recipe,
    generate_table_standardization_recipe,
    generate_topic_standardization_recipe,
)


class TestRewriteExecutor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sample_clusters = [
            {
                "members": ["java-billing:java", "py-orders:python"],
                "shared": [
                    ("KAFKA_TOPIC", "order.created"),
                    ("SQL_TABLE", "customers"),
                    ("HTTP_ENDPOINT", "/api/v1/orders"),
                ],
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
        self.assertIn("propertyKey: \"kafka.topic.order\"", recipe)

    def test_table_standardization_recipe_has_no_kafka_pollution(self):
        recipe = generate_table_standardization_recipe("StandardizeCustomers", "customers", "canonical_customers")
        self.assertIn("type: specs.openrewrite.org/v1beta/recipe", recipe)
        self.assertIn("Standardize SQL Table customers to canonical_customers", recipe)
        self.assertIn("toReplace: \"customers\"", recipe)
        self.assertIn("replacement: \"canonical_customers\"", recipe)
        # Verify strictly NO kafka properties are injected into SQL table recipe
        self.assertNotIn("kafka", recipe.lower())

    def test_endpoint_standardization_recipe_has_no_kafka_pollution(self):
        recipe = generate_endpoint_standardization_recipe("StandardizeOrdersAPI", "/api/v1/orders", "/canonical/orders")
        self.assertIn("type: specs.openrewrite.org/v1beta/recipe", recipe)
        self.assertIn("Standardize Endpoint /api/v1/orders to /canonical/orders", recipe)
        self.assertIn("toReplace: \"/api/v1/orders\"", recipe)
        self.assertIn("replacement: \"/canonical/orders\"", recipe)
        self.assertNotIn("kafka", recipe.lower())

    def test_class_migration_recipe(self):
        recipe = generate_class_migration_recipe("MigrateClient", "com.legacy.Client", "com.canonical.Client")
        self.assertIn("org.openrewrite.java.ChangeType:", recipe)
        self.assertIn("oldFullyQualifiedTypeName: \"com.legacy.Client\"", recipe)
        self.assertIn("newFullyQualifiedTypeName: \"com.canonical.Client\"", recipe)

    def test_generate_all_rewrite_recipes(self):
        files = generate_all_rewrite_recipes(self.sample_clusters, self.temp_dir)
        self.assertGreaterEqual(len(files), 3)

        # Check topic, table, endpoint recipes were created
        topic_recipe = next((f for f in files if "order_created" in f), None)
        table_recipe = next((f for f in files if "customers" in f), None)
        endpoint_recipe = next((f for f in files if "api_v1_orders" in f), None)
        runner_sh = next((f for f in files if f.endswith("run_rewrite.sh")), None)

        self.assertIsNotNone(topic_recipe)
        self.assertIsNotNone(table_recipe)
        self.assertIsNotNone(endpoint_recipe)
        self.assertIsNotNone(runner_sh)

        self.assertTrue(os.path.exists(topic_recipe))
        self.assertTrue(os.path.exists(table_recipe))
        self.assertTrue(os.path.exists(endpoint_recipe))
        self.assertTrue(os.path.exists(runner_sh))

        # Check table recipe does NOT have kafka properties
        with open(table_recipe) as f:
            table_content = f.read()
        self.assertNotIn("kafka", table_content.lower())

        # Check runner is executable
        self.assertTrue(os.access(runner_sh, os.X_OK))


if __name__ == "__main__":
    unittest.main()
