"""Unit tests verifying the Domain-Driven Architecture and facade parity."""
import os
import tempfile
import unittest

# 1. Core package imports
from convergence_factory.core import Store, schema, resolver, graph
from convergence_factory.core.schema import Project, Module, IntegrationFact, Dependency
from convergence_factory.core.resolver import ResolutionContext, resolve

# 2. Probes package imports
from convergence_factory.probes import integration, semantic, contracts, bom, clones
from convergence_factory.probes.integration import REGISTRY, LanguagePlugin
from convergence_factory.probes.semantic import HeuristicJudge, HashingEmbedder, HeuristicSummarizer, recall
from convergence_factory.probes.contracts import extract_contracts
from convergence_factory.probes.bom import parse_requirements_txt
from convergence_factory.probes.clones import detect_clones

# 3. Remediation package imports
from convergence_factory.remediation import ratchets, refactoring, healing
from convergence_factory.remediation.ratchets import generate_all_ratchets, generate_archunit_rule
from convergence_factory.remediation.refactoring import generate_all_rewrite_recipes
from convergence_factory.remediation.healing import run_self_healing, heal_cluster, HealingReport, HealingAction

# 4. Ingestion package imports
from convergence_factory.ingestion import census, caching, connectors
from convergence_factory.ingestion.caching import compute_repo_hash
from convergence_factory.ingestion.connectors import gitlab, parse_inventory

# 5. Exporters package imports
from convergence_factory.exporters import report, mermaid, graphify
from convergence_factory.exporters.mermaid import generate_mermaid_diagram
from convergence_factory.exporters.graphify import build_graph_data, export_graph_json

# Root Facades for backward compatibility
import convergence_factory.schema as root_schema
import convergence_factory.store as root_store
import convergence_factory.resolver as root_resolver
import convergence_factory.graph as root_graph
import convergence_factory.census as root_census
import convergence_factory.ratchet as root_ratchet
import convergence_factory.heal as root_heal
import convergence_factory.clone_probe as root_clone_probe
import convergence_factory.report as root_report


class TestDomainArchitecture(unittest.TestCase):
    def test_core_package_and_facade_parity(self):
        """Verify core engine symbols and strict identity with root facades."""
        self.assertIs(root_schema.Project, Project)
        self.assertIs(root_schema.Module, Module)
        self.assertIs(root_schema.IntegrationFact, IntegrationFact)
        self.assertIs(root_store.Store, Store)
        self.assertIs(root_resolver.resolve, resolve)
        self.assertIs(root_graph.build, graph.build)

    def test_5_probes_discovery(self):
        """Verify the 5 evidence probes are available and conform to specification."""
        # Probe 1: Integration
        self.assertTrue(len(REGISTRY) > 0)
        # Probe 2: Semantic
        embedder = HashingEmbedder()
        vec = embedder.embed("order payment processing")
        self.assertTrue(len(vec) > 0)
        # Probe 3: Contracts
        m = Module(id="p:m", project_id="p", path="/tmp", name="m", kind="service", lang="python", build_system="none")
        self.assertEqual(extract_contracts(m, "/tmp"), [])
        # Probe 4: BOM
        self.assertEqual(parse_requirements_txt("/nonexistent/requirements.txt", "p:m"), [])
        # Probe 5: Clones
        self.assertIs(root_clone_probe.detect_clones, detect_clones)

    def test_remediation_layer(self):
        """Verify remediation, ratchets, refactoring, and healing engine."""
        self.assertIs(root_ratchet.generate_archunit_rule, generate_archunit_rule)
        self.assertIs(root_heal.run_self_healing, run_self_healing)
        self.assertIs(root_heal.heal_cluster, heal_cluster)

        test_cluster = {
            "members": ["orders-svc:app"],
            "shared": [("KAFKA_TOPIC", "order-events")],
            "play": "RETIRE",
        }
        rule = generate_archunit_rule(test_cluster)
        self.assertIn("package com.acme.governance;", rule)

        with tempfile.TemporaryDirectory() as td:
            recipes = generate_all_rewrite_recipes([test_cluster], td)
            self.assertTrue(any("rewrite" in r for r in recipes))

    def test_ingestion_and_exporters_layer(self):
        """Verify ingestion connectors, hashing, and exporters."""
        self.assertIs(root_census.scan, census.scan)
        self.assertIs(root_report.generate_mermaid_diagram, generate_mermaid_diagram)

        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test.db")
            st = Store(db_path)
            st.add_project(Project(id="p1", repo_url="local:p1", name="p1", owner_team="alpha", langs=["python"], loc=100))
            st.add_module(Module(id="p1:core", project_id="p1", path=td, name="core", kind="service", lang="python", build_system="pip"))

            # Graphify export
            g_path = os.path.join(td, "graph.json")
            export_graph_json(st, [], g_path)
            self.assertTrue(os.path.exists(g_path))

            # Mermaid generation
            diagram = generate_mermaid_diagram(st, [])
            self.assertIn("graph LR", diagram)


if __name__ == "__main__":
    unittest.main()
