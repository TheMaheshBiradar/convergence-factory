import json
import os
import shutil
import tempfile
import unittest

from convergence_factory import census
from convergence_factory.connectors.gitlab import GitLabConnector, parse_inventory


class TestGitLabConnector(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sample_inventory = {
            "groups": [
                {
                    "id": 100,
                    "full_path": "org/core",
                    "subgroups": [
                        {
                            "id": 101,
                            "projects": [
                                {"id": 1, "path_with_namespace": "org/core/service-a", "http_url_to_repo": "https://gitlab.com/org/core/service-a.git"},
                                {"id": 2, "path_with_namespace": "org/core/service-b", "http_url_to_repo": "https://gitlab.com/org/core/service-b.git"}
                            ]
                        }
                    ],
                    "projects": [
                        {"id": 3, "path_with_namespace": "org/core/gateway", "http_url_to_repo": "https://gitlab.com/org/core/gateway.git"},
                        {"id": 1, "path_with_namespace": "org/core/service-a"}  # duplicate id 1
                    ]
                }
            ]
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_nested_inventory(self):
        deduped = parse_inventory(self.sample_inventory)
        self.assertEqual(len(deduped), 3)
        ids = {p["id"] for p in deduped}
        self.assertEqual(ids, {1, 2, 3})

    def test_parse_flat_inventory(self):
        flat = [{"id": "p1"}, {"id": "p2"}]
        deduped = parse_inventory(flat)
        self.assertEqual(len(deduped), 2)

    def test_scan_inventory_local_matching(self):
        # Create matching local directory for service-a
        svc_a_dir = os.path.join(self.temp_dir, "service-a")
        os.makedirs(svc_a_dir)
        with open(os.path.join(svc_a_dir, "app.py"), "w") as f:
            f.write("import os\n")

        items = parse_inventory(self.sample_inventory)
        scans = census.scan_inventory(items, self.temp_dir)
        self.assertEqual(len(scans), 1)
        scan = scans[0]
        self.assertEqual(scan.project.id, "service-a")
        self.assertEqual(scan.project.repo_url, "https://gitlab.com/org/core/service-a.git")
        self.assertEqual(scan.project.langs, ["python"])


if __name__ == "__main__":
    unittest.main()
