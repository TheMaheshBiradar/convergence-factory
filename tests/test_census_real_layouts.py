"""Regression tests for census on real-world repo layouts.

Reproduces the bugs found by running on real GitHub repos: standalone repos were
being replaced by their examples/, Node repos were dropped entirely, and repos
got self-duplicated. Each real repo must yield exactly one project (root as
fallback), monorepos split by package, and examples/docs are never projects.
"""
import os

from convergence_factory.ingestion.census import find_project_dirs, scan


def _w(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)


def test_standalone_repo_with_examples_is_one_project(tmp_path):
    repo = tmp_path / "mylib"
    _w(str(repo / "pyproject.toml"), "[project]\nname = 'mylib'\n")
    _w(str(repo / "mylib" / "__init__.py"), "x = 1\n")
    _w(str(repo / "examples" / "demo1" / "app.py"), "print(1)\n")
    _w(str(repo / "examples" / "demo2" / "app.py"), "print(2)\n")
    _w(str(repo / "docs" / "conf.py"), "x = 1\n")
    found = find_project_dirs(str(tmp_path))
    assert len(found) == 1
    assert os.path.basename(found[0]) == "mylib"   # not demo1/demo2/docs


def test_node_repo_is_detected_not_dropped(tmp_path):
    repo = tmp_path / "svc"
    _w(str(repo / "package.json"), '{"name": "svc"}')
    _w(str(repo / "index.js"), "module.exports = {}\n")
    _w(str(repo / "lib" / "a.js"), "1\n")
    _w(str(repo / "examples" / "e.js"), "1\n")
    scans = scan(str(tmp_path))
    assert len(scans) == 1
    assert scans[0].primary.name == "lang-node"


def test_monorepo_splits_into_packages(tmp_path):
    root = tmp_path / "mono"
    _w(str(root / "package.json"), '{"name": "mono", "workspaces": ["packages/*"]}')
    _w(str(root / "packages" / "a" / "package.json"), '{"name": "a"}')
    _w(str(root / "packages" / "a" / "index.js"), "1\n")
    _w(str(root / "packages" / "b" / "package.json"), '{"name": "b"}')
    _w(str(root / "packages" / "b" / "index.js"), "1\n")
    found = find_project_dirs(str(tmp_path))
    assert sorted(os.path.basename(p) for p in found) == ["a", "b"]


def test_flat_set_of_repos_each_one_project(tmp_path):
    for n in ["r1", "r2", "r3", "r4", "r5"]:
        _w(str(tmp_path / n / "pyproject.toml"), f"name = '{n}'\n")
        _w(str(tmp_path / n / "m.py"), "x = 1\n")
    assert len(find_project_dirs(str(tmp_path))) == 5


def test_sql_only_repo_without_manifest_still_found(tmp_path):
    repo = tmp_path / "warehouse"
    _w(str(repo / "schema.sql"), "CREATE TABLE t (id INT);\n")
    _w(str(repo / "OWNER"), "team-data\n")
    found = find_project_dirs(str(tmp_path))
    assert len(found) == 1 and os.path.basename(found[0]) == "warehouse"
