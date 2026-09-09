"""Unit tests for BOM (Bill of Materials) probe."""
import json
import os
import tempfile
import unittest

from convergence_factory.core.schema import Dependency, Module, Project
from convergence_factory.core.store import Store
from convergence_factory.probes.bom import (
    build_sbom,
    parse_requirements_txt,
    run_bom,
    shared_dependency_report,
)


class TestBomProbe(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.store = Store(self.db_path)

        # Setup sample projects and modules across two teams
        self.store.add_project(Project(
            id="proj-orders", repo_url="local:orders", name="Orders",
            owner_team="team-checkout", langs=["java", "python"], loc=1000
        ))
        self.store.add_project(Project(
            id="proj-inventory", repo_url="local:inventory", name="Inventory",
            owner_team="team-logistics", langs=["java"], loc=800
        ))

        self.store.add_module(Module(
            id="proj-orders:svc", project_id="proj-orders", path=self.temp_dir.name,
            name="orders-svc", kind="service", lang="java", build_system="maven"
        ))
        self.store.add_module(Module(
            id="proj-inventory:svc", project_id="proj-inventory", path=self.temp_dir.name,
            name="inventory-svc", kind="service", lang="java", build_system="maven"
        ))

        # Shared dependency across teams: spring-kafka
        # Unshared dependency: commons-io only in orders
        self.store.add_dependencies([
            Dependency(module_id="proj-orders:svc", purl="pkg:maven/org.springframework.kafka/spring-kafka@3.0.0", scope="runtime", tier="HIGH"),
            Dependency(module_id="proj-orders:svc", purl="pkg:maven/commons-io/commons-io@2.11.0", scope="runtime", tier="HIGH"),
            Dependency(module_id="proj-inventory:svc", purl="pkg:maven/org.springframework.kafka/spring-kafka@3.0.0", scope="runtime", tier="HIGH"),
        ])

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_build_sbom_cyclonedx(self):
        """Verify CycloneDX 1.5 JSON SBOMs are generated per project."""
        out_dir = os.path.join(self.temp_dir.name, "sboms")
        sbom_files = build_sbom(self.store, out_dir)
        self.assertEqual(len(sbom_files), 2)

        # Check orders SBOM structure
        orders_sbom = [f for f in sbom_files if "proj-orders.cdx.json" in f][0]
        self.assertTrue(os.path.exists(orders_sbom))
        with open(orders_sbom, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["bomFormat"], "CycloneDX")
        self.assertEqual(data["specVersion"], "1.5")
        self.assertEqual(data["metadata"]["component"]["name"], "proj-orders")
        component_names = {c["name"] for c in data["components"]}
        self.assertIn("spring-kafka", component_names)
        self.assertIn("commons-io", component_names)

    def test_shared_dependency_report(self):
        """Verify shared dependencies across >= 2 teams are flagged."""
        shared = shared_dependency_report(self.store, min_owners=2)
        self.assertEqual(len(shared), 1)
        item = shared[0]
        self.assertEqual(item["dependency"], "spring-kafka")
        self.assertEqual(item["count"], 2)
        self.assertEqual(sorted(item["owners"]), ["team-checkout", "team-logistics"])

    def test_run_bom_orchestration(self):
        """Verify run_bom end-to-end orchestrator produces sbom files and shared report."""
        out_dir = os.path.join(self.temp_dir.name, "bom_out")
        res = run_bom(self.store, out_dir)
        self.assertIn("sbom_files", res)
        self.assertIn("shared_dependencies", res)
        self.assertEqual(len(res["sbom_files"]), 2)
        self.assertEqual(len(res["shared_dependencies"]), 1)

    def test_parse_requirements_txt(self):
        """Verify parse_requirements_txt parses dependencies, versions, and comments."""
        req_path = os.path.join(self.temp_dir.name, "requirements.txt")
        with open(req_path, "w", encoding="utf-8") as f:
            f.write("# Sample requirements\nflask>=2.0.0\nrequests==2.28.1\n\n# Comment\npytest\n")

        deps = parse_requirements_txt(req_path, module_id="test:mod")
        self.assertEqual(len(deps), 3)
        purls = [d.purl for d in deps]
        self.assertIn("pkg:pypi/flask", purls)
        self.assertIn("pkg:pypi/requests", purls)
        self.assertIn("pkg:pypi/pytest", purls)

    def test_parse_requirements_txt_missing_file(self):
        """Verify handling of nonexistent requirements.txt file."""
        self.assertEqual(parse_requirements_txt("/nonexistent/file.txt", "m"), [])


if __name__ == "__main__":
    unittest.main()
