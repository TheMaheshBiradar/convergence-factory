"""Unit tests for DB-schema probe and SQL column lineage."""
import os
import tempfile
import unittest

from convergence_factory.core.schema import IntegrationFact, Module, Project, Provenance
from convergence_factory.core.store import Store
from convergence_factory.probes.integration.lang_sql import (
    extract_sql_columns,
    extract_sql_lineage,
)
from convergence_factory.probes.schema.schema_probe import analyze_schema


class TestSchemaProbe(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.store = Store(self.db_path)

        self.mod_dir = os.path.join(self.temp_dir.name, "sql_mod")
        os.makedirs(self.mod_dir, exist_ok=True)

        self.store.add_project(Project(
            id="proj-db", repo_url="local:db", name="Warehouse",
            owner_team="data-team", langs=["sql"], loc=300
        ))
        self.store.add_module(Module(
            id="proj-db:sql", project_id="proj-db", path=self.mod_dir,
            name="schema-ddl", kind="library", lang="sql", build_system="sql"
        ))

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_analyze_schema_fk_and_orphans(self):
        """Verify DDL extraction finds foreign key relations and flags orphan tables."""
        ddl = """
        CREATE TABLE customers (
            id INT PRIMARY KEY,
            name VARCHAR(100)
        );

        CREATE TABLE orders (
            id INT PRIMARY KEY,
            customer_id INT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE TABLE order_items (
            item_id INT PRIMARY KEY,
            order_id INT REFERENCES orders(id),
            sku VARCHAR(50)
        );

        CREATE TABLE deprecated_orphan_audit (
            id INT PRIMARY KEY,
            log_message TEXT
        );
        """
        with open(os.path.join(self.mod_dir, "schema.sql"), "w", encoding="utf-8") as f:
            f.write(ddl)

        res = analyze_schema(self.store)
        tables = res["tables"]
        self.assertIn("customers", tables)
        self.assertIn("orders", tables)
        self.assertIn("order_items", tables)
        self.assertIn("deprecated_orphan_audit", tables)

        # Foreign key edges: child -> parent
        fk_edges = res["fk_edges"]
        self.assertIn(("orders", "customers"), fk_edges)
        self.assertIn(("order_items", "orders"), fk_edges)

        # Orphan detection: deprecated_orphan_audit is neither child nor parent
        self.assertIn("deprecated_orphan_audit", res["orphan_tables"])
        self.assertNotIn("customers", res["orphan_tables"])
        self.assertNotIn("orders", res["orphan_tables"])

    def test_shared_table_prevents_orphan(self):
        """Verify tables touched across multiple modules are not flagged as orphans."""
        ddl = """
        CREATE TABLE shared_events (
            id INT PRIMARY KEY,
            payload TEXT
        );
        """
        with open(os.path.join(self.mod_dir, "events.sql"), "w", encoding="utf-8") as f:
            f.write(ddl)

        # Two modules touch shared_events
        self.store.add_integration([
            IntegrationFact(module_id="mod-a", direction="WRITES", resource_type="SQL_TABLE", resource_id="shared_events", tier="HIGH", provenance=Provenance(file="events.sql", snippet="test")),
            IntegrationFact(module_id="mod-b", direction="READS", resource_type="SQL_TABLE", resource_id="shared_events", tier="HIGH", provenance=Provenance(file="events.sql", snippet="test")),
        ])

        res = analyze_schema(self.store)
        self.assertIn("shared_events", res["shared_tables"])
        self.assertNotIn("shared_events", res["orphan_tables"])

    def test_extract_sql_lineage(self):
        """Verify table-level lineage extraction across diverse SQL statements."""
        sql = """
        INSERT INTO order_summary (order_id, total)
        SELECT o.id, SUM(i.price)
        FROM orders o
        JOIN order_items i ON o.id = i.order_id
        WHERE o.status = 'COMPLETED';
        """
        lineage = extract_sql_lineage(sql)
        lineage_by_table = {table: direction for direction, table in lineage}
        self.assertEqual(lineage_by_table.get("order_summary"), "WRITES")
        self.assertEqual(lineage_by_table.get("orders"), "READS")
        self.assertEqual(lineage_by_table.get("order_items"), "READS")

    def test_extract_sql_columns_create_and_insert(self):
        """Verify column-level lineage extraction from CREATE TABLE and INSERT INTO."""
        create_sql = """
        CREATE TABLE users (
            user_id INT PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            created_at TIMESTAMP,
            CONSTRAINT uq_email UNIQUE (email)
        );
        """
        create_cols = extract_sql_columns(create_sql)
        col_names = [c for _dir, c in create_cols]
        self.assertIn("users.user_id", col_names)
        self.assertIn("users.email", col_names)
        self.assertIn("users.created_at", col_names)
        # Constraints must be filtered out
        self.assertNotIn("users.constraint", col_names)

        insert_sql = "INSERT INTO users (user_id, email) VALUES (42, 'test@example.com');"
        insert_cols = extract_sql_columns(insert_sql)
        insert_col_names = [c for _dir, c in insert_cols]
        self.assertIn("users.user_id", insert_col_names)
        self.assertIn("users.email", insert_col_names)


if __name__ == "__main__":
    unittest.main()
