import os
import shutil
import tempfile
import unittest

from convergence_factory.plugins.lang_python import PythonPlugin


class TestPythonCoupling(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_single_file_coupling_is_zero(self):
        with open(os.path.join(self.temp_dir, "app.py"), "w") as f:
            f.write("import os\nprint('hello')\n")
        self.assertEqual(PythonPlugin._coupling(self.temp_dir), 0.0)

    def test_multimodule_import_density(self):
        pkg_dir = os.path.join(self.temp_dir, "pkg")
        os.makedirs(pkg_dir)

        # 4 modules: a, b, c, d (n = 4 -> max directed edges = 12)
        # a -> b, c, d (3)
        # b -> c (1)
        # c -> none (0)
        # d -> b (1)
        # Total distinct directed edges = 5 -> 5/12 = 0.417
        with open(os.path.join(pkg_dir, "a.py"), "w") as f:
            f.write("from pkg import b\nfrom pkg import c\nimport pkg.d\n")
        with open(os.path.join(pkg_dir, "b.py"), "w") as f:
            f.write("from pkg import c\n")
        with open(os.path.join(pkg_dir, "c.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(pkg_dir, "d.py"), "w") as f:
            f.write("from pkg import b\n")

        coupling = PythonPlugin._coupling(self.temp_dir)
        self.assertEqual(coupling, 0.417)

    def test_syntax_error_resilience(self):
        pkg_dir = os.path.join(self.temp_dir, "pkg")
        os.makedirs(pkg_dir)

        with open(os.path.join(pkg_dir, "valid.py"), "w") as f:
            f.write("from pkg import broken\n")
        with open(os.path.join(pkg_dir, "broken.py"), "w") as f:
            f.write("def broken syntax! :::\n")

        # Shouldn't raise SyntaxError; broken is a local node but parse errors are skipped
        coupling = PythonPlugin._coupling(self.temp_dir)
        self.assertIsInstance(coupling, float)

    def test_submodule_import_matching(self):
        pkg_dir = os.path.join(self.temp_dir, "service")
        sub_dir = os.path.join(pkg_dir, "utils")
        os.makedirs(sub_dir)

        with open(os.path.join(pkg_dir, "main.py"), "w") as f:
            f.write("from service.utils import helper\n")
        with open(os.path.join(sub_dir, "helper.py"), "w") as f:
            f.write("def help(): pass\n")

        # 2 modules: service.main and service.utils.helper
        # n = 2 -> max directed edges = 2*1 = 2
        # service.main -> service.utils.helper = 1 edge -> 1/2 = 0.5
        coupling = PythonPlugin._coupling(self.temp_dir)
        self.assertEqual(coupling, 0.5)


if __name__ == "__main__":
    unittest.main()
