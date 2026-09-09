"""Unit tests for API / contract probe."""
import json
import os
import tempfile
import unittest

from convergence_factory.core.graph import build as build_graph
from convergence_factory.core.schema import Module, Project
from convergence_factory.core.store import Store
from convergence_factory.probes.contracts.api_probe import extract_api


class TestContractsProbe(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.store = Store(self.db_path)

        self.mod1_dir = os.path.join(self.temp_dir.name, "svc1")
        self.mod2_dir = os.path.join(self.temp_dir.name, "svc2")
        os.makedirs(self.mod1_dir, exist_ok=True)
        os.makedirs(self.mod2_dir, exist_ok=True)

        self.store.add_project(Project(
            id="proj1", repo_url="local:svc1", name="Service1",
            owner_team="team-a", langs=["java"], loc=500
        ))
        self.store.add_project(Project(
            id="proj2", repo_url="local:svc2", name="Service2",
            owner_team="team-b", langs=["python"], loc=500
        ))

        self.store.add_module(Module(
            id="proj1:api", project_id="proj1", path=self.mod1_dir,
            name="svc1-api", kind="service", lang="java", build_system="maven"
        ))
        self.store.add_module(Module(
            id="proj2:api", project_id="proj2", path=self.mod2_dir,
            name="svc2-api", kind="service", lang="python", build_system="pip"
        ))

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_extract_openapi_spec(self):
        """Verify OpenAPI yaml and json parsing extracts endpoints with SERVES direction."""
        # Create an openapi.yaml in svc1
        openapi_content = """
openapi: 3.0.0
info:
  title: Order API
  version: 1.0.0
paths:
  /orders:
    get:
      summary: List orders
    post:
      summary: Create order
  /orders/{id}:
    delete:
      summary: Delete order
"""
        with open(os.path.join(self.mod1_dir, "openapi.yaml"), "w", encoding="utf-8") as f:
            f.write(openapi_content)

        # Create swagger.json in svc2 exposing the same POST /orders endpoint
        swagger_json = {
            "swagger": "2.0",
            "paths": {
                "/orders": {
                    "post": {"summary": "Create order duplicate"}
                }
            }
        }
        with open(os.path.join(self.mod2_dir, "swagger.json"), "w", encoding="utf-8") as f:
            json.dump(swagger_json, f)

        count = extract_api(self.store)
        self.assertEqual(count, 4)  # 3 from svc1 + 1 from svc2

        # Check API surfaces stored
        surfaces = self.store.api_surfaces()
        self.assertEqual(len(surfaces), 4)
        signatures = {s.signature for s in surfaces}
        self.assertIn("GET /orders", signatures)
        self.assertIn("POST /orders", signatures)
        self.assertIn("DELETE /orders/{id}", signatures)

        # Verify SERVES integration facts
        facts = self.store.integration_facts()
        serves_facts = [f for f in facts if f.direction == "SERVES"]
        self.assertEqual(len(serves_facts), 4)

        # Check graph clustering for duplicate POST /orders endpoint
        g = build_graph(self.store)
        self.assertEqual(len(g["clusters"]), 1)
        cluster = g["clusters"][0]
        self.assertEqual(sorted(cluster["members"]), ["proj1:api", "proj2:api"])
        dup_edges = [e for e in g["edges"] if e["type"] == "DUP_ENDPOINT"]
        self.assertEqual(len(dup_edges), 1)
        self.assertEqual(dup_edges[0]["resource_id"], "POST /orders")

    def test_extract_grpc_proto(self):
        """Verify protobuf service and rpc extraction."""
        proto_content = """
syntax = "proto3";
package orders;

service OrderProcessingService {
    rpc SubmitOrder (OrderRequest) returns (OrderReply);
    rpc CancelOrder (CancelRequest) returns (CancelReply);
}
"""
        with open(os.path.join(self.mod1_dir, "service.proto"), "w", encoding="utf-8") as f:
            f.write(proto_content)

        count = extract_api(self.store)
        self.assertEqual(count, 2)

        surfaces = self.store.api_surfaces()
        kinds = {s.kind for s in surfaces}
        self.assertIn("GRPC", kinds)
        sigs = {s.signature for s in surfaces}
        self.assertIn("OrderProcessingService/SubmitOrder", sigs)
        self.assertIn("OrderProcessingService/CancelOrder", sigs)

    def test_extract_graphql_schema(self):
        """Verify GraphQL Query and Mutation field extraction."""
        gql_content = """
type Query {
    customer(id: ID!): Customer
    customers: [Customer]
}

type Mutation {
    createCustomer(name: String!): Customer
}
"""
        with open(os.path.join(self.mod2_dir, "schema.graphql"), "w", encoding="utf-8") as f:
            f.write(gql_content)

        count = extract_api(self.store)
        self.assertEqual(count, 3)

        surfaces = self.store.api_surfaces()
        kinds = {s.kind for s in surfaces}
        self.assertIn("GRAPHQL", kinds)
        sigs = {s.signature for s in surfaces}
        self.assertIn("Query.customer", sigs)
        self.assertIn("Query.customers", sigs)
        self.assertIn("Mutation.createCustomer", sigs)


if __name__ == "__main__":
    unittest.main()
