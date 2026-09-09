import json
import os
import shutil
import tempfile
import unittest

from convergence_factory.plugins.lang_node import NodePlugin, _coupling


class TestNodePlugin(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.plugin = NodePlugin()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_node_project(self):
        # Empty dir -> None
        self.assertIsNone(self.plugin.detect(self.temp_dir))

        # With package.json -> detected
        pkg_path = os.path.join(self.temp_dir, "package.json")
        with open(pkg_path, "w") as f:
            json.dump({"name": "test-node", "dependencies": {"express": "^4.18.2"}}, f)

        det = self.plugin.detect(self.temp_dir)
        self.assertIsNotNone(det)
        self.assertIn("javascript", det["claims"])
        self.assertEqual(det["build"], "npm")

    def test_facts_dependencies_and_coupling(self):
        pkg_path = os.path.join(self.temp_dir, "package.json")
        with open(pkg_path, "w") as f:
            json.dump({
                "name": "service-node",
                "dependencies": {"express": "^4.18.2", "axios": "1.6.0"},
                "devDependencies": {"jest": "^29.0.0"}
            }, f)

        # Create two JS files with relative import
        f1 = os.path.join(self.temp_dir, "app.js")
        with open(f1, "w") as f:
            f.write("const utils = require('./utils');\nconst axios = require('axios');\naxios.get('https://api.internal/v1/orders');\n")

        f2 = os.path.join(self.temp_dir, "utils.js")
        with open(f2, "w") as f:
            f.write("module.exports = { helper: () => true };\n")

        modules = self.plugin.modules(self.temp_dir, "proj-node")
        self.assertEqual(len(modules), 1)
        mod = modules[0]

        bundle = self.plugin.facts(mod, self.temp_dir)
        self.assertEqual(len(bundle.dependencies), 3)
        self.assertEqual(len(bundle.integration), 1)
        self.assertEqual(bundle.integration[0].resource_type, "HTTP_ENDPOINT")
        self.assertEqual(bundle.integration[0].resource_id, "https://api.internal/v1/orders")

        coupling = _coupling(self.temp_dir)
        self.assertGreater(coupling, 0.0)


if __name__ == "__main__":
    unittest.main()
