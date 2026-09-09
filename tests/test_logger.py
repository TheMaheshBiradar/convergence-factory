"""Unit tests for Convergence Factory logger and plugin assignment tracking."""
import io
import logging
import os
import tempfile
import unittest

from convergence_factory.census import scan_project
from convergence_factory.logger import LOGGER, setup_logger
from convergence_factory.runner import extract
from convergence_factory.store import Store


class TestLoggerAndPluginAssignment(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.store = Store(self.db_path)

        # Create a sample Python repo
        self.repo_dir = os.path.join(self.temp_dir.name, "sample-service")
        os.makedirs(self.repo_dir, exist_ok=True)
        with open(os.path.join(self.repo_dir, "OWNER"), "w") as f:
            f.write("team-alpha\n")
        with open(os.path.join(self.repo_dir, "main.py"), "w") as f:
            f.write("print('hello world')\n")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_setup_logger_debug_and_info(self):
        """Verify setup_logger configures logging level and handles streams."""
        logger = setup_logger(verbose=True)
        self.assertEqual(logger.level, logging.DEBUG)

        logger = setup_logger(verbose=False)
        self.assertEqual(logger.level, logging.INFO)

    def test_census_and_extract_logs_plugin_assignment(self):
        """Verify census and extract emit log messages tracking which plugin is assigned to which project."""
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)

        try:
            # 1. Census scan
            scan = scan_project(self.repo_dir, project_id="sample-service")
            self.assertIsNotNone(scan)
            self.assertEqual(scan.primary.name, "lang-python")

            # 2. Extract run
            st = extract(self.store, scan)
            self.assertEqual(st["modules"], 1)

            logs = log_stream.getvalue()
            # Verify census log contains assignment
            self.assertIn("Census 'sample-service': assigned primary plugin 'lang-python'", logs)
            # Verify extraction logs contain start and completion with plugin name
            self.assertIn("Extracting project 'sample-service' -> assigned plugin 'lang-python'", logs)
            self.assertIn("Finished extraction: project 'sample-service' -> plugin 'lang-python'", logs)
        finally:
            LOGGER.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
