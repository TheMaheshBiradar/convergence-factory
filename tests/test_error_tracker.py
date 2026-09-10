import os
import shutil
import tempfile
import unittest

from convergence_factory.core.errors import ErrorTracker, FrameworkError, ERROR_TRACKER


class TestErrorTracker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tracker = ErrorTracker()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_error_and_warning(self):
        self.assertEqual(self.tracker.count(), 0)
        self.assertFalse(self.tracker.has_errors())

        # Record warning
        w = self.tracker.record_warning(
            phase="probe:semantic:judge",
            source="http://localhost:11434",
            warning_type="TimeoutWarning",
            message="LLM call timed out after 60s",
            details="Traceback: ReadTimeout",
            remediation="Increase timeout or check Ollama health"
        )
        self.assertIsInstance(w, FrameworkError)
        self.assertEqual(w.severity, "WARNING")
        self.assertEqual(self.tracker.count(), 1)
        self.assertFalse(self.tracker.has_errors())

        # Record error
        e = self.tracker.record(
            phase="probe:integration",
            source="billing/pom.xml",
            error_type="SchemaError",
            message="Invalid XML element",
            details="Line 42: <unknown>",
            remediation="Verify maven schema",
            severity="ERROR"
        )
        self.assertIsInstance(e, FrameworkError)
        self.assertEqual(e.severity, "ERROR")
        self.assertEqual(self.tracker.count(), 2)
        self.assertTrue(self.tracker.has_errors())

    def test_format_log_healthy(self):
        log = self.tracker.format_log()
        self.assertIn("CONVERGENCE FACTORY - FRAMEWORK ERROR & FEEDBACK LOG", log)
        self.assertIn("Status: HEALTHY (0 framework errors or warnings recorded)", log)

    def test_format_log_with_issues(self):
        self.tracker.record(
            phase="probe:integration",
            source="repo/module-a",
            error_type="PluginCrash",
            message="Unhandled exception in AST visitor",
            details="IndexError: list index out of range",
            remediation="Fix plugin parser",
            severity="ERROR"
        )
        log = self.tracker.format_log()
        self.assertIn("Total Issues Recorded: 1 (1 Errors, 0 Warnings)", log)
        self.assertIn("[ERROR #1]", log)
        self.assertIn("Phase       : probe:integration", log)
        self.assertIn("Source      : repo/module-a", log)
        self.assertIn("Type        : PluginCrash", log)
        self.assertIn("Message     : Unhandled exception in AST visitor", log)
        self.assertIn("Remediation : Fix plugin parser", log)
        self.assertIn("IndexError: list index out of range", log)

    def test_write_to_file_directory_and_site_sync(self):
        self.tracker.record(
            phase="census",
            source="/repos/bad-repo",
            error_type="ParseError",
            message="Invalid pom.xml",
            severity="ERROR"
        )
        site_dir = os.path.join(self.temp_dir, "site")
        os.makedirs(site_dir, exist_ok=True)

        # Write to directory
        target = self.tracker.write_to_file(self.temp_dir)
        self.assertTrue(target.endswith("error.txt"))
        self.assertTrue(os.path.isfile(target))

        # Check content in root target
        with open(target, "r", encoding="utf-8") as fh:
            text = fh.read()
            self.assertIn("ParseError", text)
            self.assertIn("/repos/bad-repo", text)

        # Check that it synced to site/error.txt
        site_error_txt = os.path.join(site_dir, "error.txt")
        self.assertTrue(os.path.isfile(site_error_txt))
        with open(site_error_txt, "r", encoding="utf-8") as fh:
            site_text = fh.read()
            self.assertIn("ParseError", site_text)

    def test_clear(self):
        self.tracker.record("p", "s", "t", "m")
        self.assertEqual(self.tracker.count(), 1)
        self.tracker.clear()
        self.assertEqual(self.tracker.count(), 0)
        self.assertFalse(self.tracker.has_errors())


if __name__ == "__main__":
    unittest.main()
