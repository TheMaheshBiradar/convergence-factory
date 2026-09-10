import json
import os
import tempfile
import pytest

from convergence_factory.core.store import Store
from convergence_factory.ingestion.census import scan_project
from convergence_factory.runner import extract

def test_polyglot_hybrid_repository_extraction():
    """Validates that a single repository containing Java, JSP, React, Angular, and SQL
    executes all matching plugins, records all modules, and extracts facts from both frontend and backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, "hybrid-order-app")
        os.makedirs(repo_dir)

        # 1. Java backend with pom.xml and Spring Controller
        pom_xml = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>order-backend</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.kafka</groupId>
      <artifactId>spring-kafka</artifactId>
      <version>3.1.0</version>
    </dependency>
  </dependencies>
</project>"""
        with open(os.path.join(repo_dir, "pom.xml"), "w") as f:
            f.write(pom_xml)

        java_dir = os.path.join(repo_dir, "src", "main", "java", "com", "example")
        os.makedirs(java_dir)
        controller_java = """package com.example;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.kafka.core.KafkaTemplate;

@RestController
public class OrderController {
    private KafkaTemplate<String, String> kafkaTemplate;

    @GetMapping("/api/orders")
    public String getOrders() {
        kafkaTemplate.send("order.events", "new order");
        return "orders";
    }
}"""
        with open(os.path.join(java_dir, "OrderController.java"), "w") as f:
            f.write(controller_java)

        # 2. Legacy JSP View with form action and c:url
        jsp_dir = os.path.join(repo_dir, "src", "main", "webapp", "WEB-INF", "jsp")
        os.makedirs(jsp_dir)
        checkout_jsp = """<%@ taglib uri="http://java.sun.com/jsp/jstl/core" prefix="c" %>
<html>
  <body>
    <h2>Checkout Order</h2>
    <form action="/api/checkout" method="POST">
      <input type="submit" value="Submit"/>
    </form>
    <c:url value="/api/orders" var="ordersUrl"/>
    <a href="/api/catalog">Back to catalog</a>
  </body>
</html>"""
        with open(os.path.join(jsp_dir, "checkout.jsp"), "w") as f:
            f.write(checkout_jsp)

        # 3. Modern Frontend in subfolder with package.json (Angular + React)
        frontend_dir = os.path.join(repo_dir, "frontend")
        os.makedirs(os.path.join(frontend_dir, "src"))
        pkg_json = {
            "name": "hybrid-frontend",
            "version": "1.0.0",
            "dependencies": {
                "@angular/core": "^17.0.0",
                "@angular/common": "^17.0.0",
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
                "axios": "^1.6.0"
            }
        }
        with open(os.path.join(frontend_dir, "package.json"), "w") as f:
            json.dump(pkg_json, f)

        # TypeScript file using Angular HttpClient and React/Axios calls
        ts_code = """import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class OrderService {
  constructor(private http: any) {}

  fetchOrders() {
    return this.http.get('/api/orders');
  }

  submitCheckout(payload: any) {
    return axios.post('/api/checkout', payload);
  }
}"""
        with open(os.path.join(frontend_dir, "src", "order.service.ts"), "w") as f:
            f.write(ts_code)

        # 4. SQL schema / migration
        sql_dir = os.path.join(repo_dir, "db")
        os.makedirs(sql_dir)
        sql_code = """CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    customer_id INT,
    amount DECIMAL(10, 2)
);"""
        with open(os.path.join(sql_dir, "001_orders.sql"), "w") as f:
            f.write(sql_code)

        # Perform census scan
        scan = scan_project(repo_dir, project_id="hybrid-order-app")
        assert scan is not None, "scan_project must detect the hybrid project"

        # Check detected languages and claims
        assert "java" in scan.project.langs
        assert "jsp" in scan.project.langs
        assert "react" in scan.project.langs
        assert "angular" in scan.project.langs
        assert "typescript" in scan.project.langs
        assert "sql" in scan.project.langs

        # Check all matching plugins are assigned
        plugin_names = [p.name for p in scan.plugins]
        assert "lang-java" in plugin_names
        assert "lang-node" in plugin_names
        assert "lang-sql" in plugin_names

        # Execute extraction into FactStore
        store = Store()
        stats = extract(store, scan)

        # Verify modules from all plugins were registered
        modules = [m for m in store.modules() if m.project_id == "hybrid-order-app"]
        mod_ids = {m.id for m in modules}
        assert "hybrid-order-app:java" in mod_ids
        assert "hybrid-order-app:node" in mod_ids
        assert "hybrid-order-app:sql" in mod_ids

        # Verify Java & JSP integration facts
        facts = store.integration_facts()
        java_facts = [f for f in facts if f.module_id == "hybrid-order-app:java"]
        java_resources = {f.resource_id: f.direction for f in java_facts}
        # Java Kafka topic
        assert "order.events" in java_resources
        assert java_resources["order.events"] == "PRODUCES"
        # JSP form action & links
        assert "/api/checkout" in java_resources
        assert java_resources["/api/checkout"] == "CALLS"
        assert "/api/orders" in java_resources
        assert "/api/catalog" in java_resources

        # Verify Node / React / Angular integration facts
        node_facts = [f for f in facts if f.module_id == "hybrid-order-app:node"]
        node_resources = {f.resource_id: f.direction for f in node_facts}
        assert "/api/orders" in node_resources
        assert node_resources["/api/orders"] == "CALLS"
        assert "/api/checkout" in node_resources
        assert node_resources["/api/checkout"] == "CALLS"

        # Verify SQL table fact
        sql_facts = [f for f in facts if f.module_id == "hybrid-order-app:sql"]
        sql_resources = {f.resource_id: f.direction for f in sql_facts}
        assert "orders" in sql_resources

        # Verify cross-language dependencies recorded in store
        deps = [d for d in store.dependencies() if d.module_id in mod_ids]
        dep_purls = {d.purl for d in deps}
        assert any("spring-kafka" in p for p in dep_purls)
        assert any("react" in p for p in dep_purls)
        assert any("@angular/core" in p for p in dep_purls)
