"""Unit tests verifying multi-level nested group and subgroup project discovery."""
import os
import tempfile
import unittest

from convergence_factory.census import find_project_dirs, scan


class TestNestedCensusDiscovery(unittest.TestCase):
    def test_nested_subgroup_project_discovery(self):
        """Verify discovery across 7-8 root projects with subgroups and leaf microservices."""
        with tempfile.TemporaryDirectory() as root:
            # Simulate: 2 root projects, each 2 subgroups, each 2 microservices
            # Total: 8 microservices
            expected_projects = []
            for r in ["banking", "payments"]:
                for sg in ["core", "gateway"]:
                    for svc in ["order_service", "billing_service"]:
                        proj_dir = os.path.join(root, r, sg, svc)
                        os.makedirs(os.path.join(proj_dir, "src", "main", "java"), exist_ok=True)
                        with open(os.path.join(proj_dir, "pom.xml"), "w") as f:
                            f.write("<project><groupId>com.acme</groupId><artifactId>" + svc + "</artifactId></project>")
                        with open(os.path.join(proj_dir, "src", "main", "java", "App.java"), "w") as f:
                            f.write("package com.acme; public class App {}")
                        with open(os.path.join(proj_dir, "OWNER"), "w") as f:
                            f.write(f"team-{sg}\n")
                        expected_projects.append(os.path.abspath(proj_dir))

            found = find_project_dirs(root)
            self.assertEqual(len(found), 8)
            for ep in expected_projects:
                self.assertIn(ep, found)

            scans = scan(root)
            self.assertEqual(len(scans), 8)

            # Because order_service appears under multiple subgroups, collision slugging applies
            scan_ids = {s.project.id for s in scans}
            self.assertEqual(len(scan_ids), 8)  # All IDs must be unique
            self.assertTrue(any("banking-core-order_service" in sid for sid in scan_ids))

            # Verify primary plugin is correctly assigned
            for s in scans:
                self.assertEqual(s.primary.name, "lang-java")
                self.assertEqual(s.project.deploy_target, "maven")

    def test_group_level_owner_inheritance(self):
        """Verify services inherit OWNER defined at parent group level if missing in leaf."""
        with tempfile.TemporaryDirectory() as root:
            group_dir = os.path.join(root, "wealth-management")
            sub_dir = os.path.join(group_dir, "advisory")
            proj_dir = os.path.join(sub_dir, "portfolio-svc")
            os.makedirs(proj_dir, exist_ok=True)

            # OWNER placed at top group level
            with open(os.path.join(group_dir, "OWNER"), "w") as f:
                f.write("team-wealth\n")

            # Project has package.json and index.js, but no local OWNER
            with open(os.path.join(proj_dir, "package.json"), "w") as f:
                f.write('{"name": "portfolio-svc"}')
            with open(os.path.join(proj_dir, "index.js"), "w") as f:
                f.write("console.log('portfolio');")

            scans = scan(root)
            self.assertEqual(len(scans), 1)
            self.assertEqual(scans[0].project.name, "portfolio-svc")
            self.assertEqual(scans[0].project.owner_team, "team-wealth")
            self.assertEqual(scans[0].primary.name, "lang-node")


if __name__ == "__main__":
    unittest.main()
