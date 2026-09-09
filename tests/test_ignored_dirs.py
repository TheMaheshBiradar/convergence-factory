"""Unit tests verifying directory exclusions across Node, Python, and Java ecosystems."""
import os
import tempfile
import unittest

from convergence_factory.census import scan
from convergence_factory.ingestion.caching import compute_repo_hash
from convergence_factory.probes.integration.base import is_ignored_dir, walk_files


class TestIgnoredDirectories(unittest.TestCase):
    def test_is_ignored_dir_predicates(self):
        """Verify is_ignored_dir correctly flags build, cache, and virtualenv artifacts."""
        # Node.js
        self.assertTrue(is_ignored_dir("node_modules"))
        self.assertTrue(is_ignored_dir(".next"))
        self.assertTrue(is_ignored_dir(".turbo"))
        self.assertTrue(is_ignored_dir("coverage"))
        self.assertTrue(is_ignored_dir(".nyc_output"))
        self.assertTrue(is_ignored_dir("bower_components"))

        # Python
        self.assertTrue(is_ignored_dir(".venv"))
        self.assertTrue(is_ignored_dir("venv"))
        self.assertTrue(is_ignored_dir("env"))
        self.assertTrue(is_ignored_dir("__pycache__"))
        self.assertTrue(is_ignored_dir(".pytest_cache"))
        self.assertTrue(is_ignored_dir(".tox"))
        self.assertTrue(is_ignored_dir("sample_pkg.egg-info"))
        self.assertTrue(is_ignored_dir("sample_pkg.dist-info"))

        # Java
        self.assertTrue(is_ignored_dir("target"))
        self.assertTrue(is_ignored_dir("build"))
        self.assertTrue(is_ignored_dir(".gradle"))
        self.assertTrue(is_ignored_dir("out"))
        self.assertTrue(is_ignored_dir("bin"))

        # Valid source directories must not be ignored
        self.assertFalse(is_ignored_dir("src"))
        self.assertFalse(is_ignored_dir("app"))
        self.assertFalse(is_ignored_dir("lib"))
        self.assertFalse(is_ignored_dir("controllers"))
        self.assertFalse(is_ignored_dir("target_service"))
        self.assertFalse(is_ignored_dir("outbound"))

    def test_walk_files_skips_ignored_dirs(self):
        """Verify walk_files traverses valid code and prunes node_modules, target, venv, and out."""
        with tempfile.TemporaryDirectory() as td:
            # Valid source files
            os.makedirs(os.path.join(td, "src", "main", "java"), exist_ok=True)
            valid_java = os.path.join(td, "src", "main", "java", "App.java")
            with open(valid_java, "w") as f:
                f.write("public class App {}\n")

            os.makedirs(os.path.join(td, "app"), exist_ok=True)
            valid_py = os.path.join(td, "app", "main.py")
            with open(valid_py, "w") as f:
                f.write("print('hello')\n")

            # Artifacts to ignore: Node, Python, Java
            os.makedirs(os.path.join(td, "node_modules", "pkg"), exist_ok=True)
            with open(os.path.join(td, "node_modules", "pkg", "index.js"), "w") as f:
                f.write("module.exports = {};\n")

            os.makedirs(os.path.join(td, "target", "classes"), exist_ok=True)
            with open(os.path.join(td, "target", "classes", "Generated.java"), "w") as f:
                f.write("public class Generated {}\n")

            os.makedirs(os.path.join(td, "out", "production"), exist_ok=True)
            with open(os.path.join(td, "out", "production", "OutClass.java"), "w") as f:
                f.write("public class OutClass {}\n")

            os.makedirs(os.path.join(td, ".venv", "lib"), exist_ok=True)
            with open(os.path.join(td, ".venv", "lib", "site.py"), "w") as f:
                f.write("# venv file\n")

            os.makedirs(os.path.join(td, "pkg.egg-info"), exist_ok=True)
            with open(os.path.join(td, "pkg.egg-info", "top_level.py"), "w") as f:
                f.write("# egg-info\n")

            found = walk_files(td, (".java", ".py", ".js"))
            self.assertIn(valid_java, found)
            self.assertIn(valid_py, found)
            # Ensure none of the ignored directories leaked
            self.assertEqual(len(found), 2)

    def test_compute_repo_hash_ignores_build_artifacts(self):
        """Verify compute_repo_hash produces identical hash when target/node_modules/venv change."""
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "App.java"), "w") as f:
                f.write("public class App {}\n")

            hash_before = compute_repo_hash(td)

            # Add node_modules and target
            os.makedirs(os.path.join(td, "node_modules", "lodash"), exist_ok=True)
            with open(os.path.join(td, "node_modules", "lodash", "lodash.js"), "w") as f:
                f.write("module.exports = {};\n")

            os.makedirs(os.path.join(td, "target"), exist_ok=True)
            with open(os.path.join(td, "target", "app.jar"), "w") as f:
                f.write("binary-jar-bytes\n")

            hash_after = compute_repo_hash(td)
            self.assertEqual(hash_before, hash_after)

    def test_census_scan_skips_ignored_root_dirs(self):
        """Verify census.scan ignores node_modules or venv folders placed in the repos directory."""
        with tempfile.TemporaryDirectory() as root:
            # Valid repo
            repo_dir = os.path.join(root, "my-service")
            os.makedirs(repo_dir, exist_ok=True)
            with open(os.path.join(repo_dir, "app.py"), "w") as f:
                f.write("print(1)\n")

            # Ignored folder at root
            os.makedirs(os.path.join(root, "node_modules"), exist_ok=True)
            with open(os.path.join(root, "node_modules", "dep.js"), "w") as f:
                f.write("console.log(1)\n")

            os.makedirs(os.path.join(root, "target"), exist_ok=True)
            with open(os.path.join(root, "target", "build.sql"), "w") as f:
                f.write("SELECT 1;\n")

            scans = scan(root)
            self.assertEqual(len(scans), 1)
            self.assertEqual(scans[0].project.id, "my-service")


if __name__ == "__main__":
    unittest.main()
