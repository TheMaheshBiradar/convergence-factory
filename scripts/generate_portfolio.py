"""Generate a synthetic multi-language repository portfolio for scale testing.

Creates N repos across several business domains and four languages
(Python/Java/SQL/Node). Repos in the same domain deliberately share a Kafka topic
and a SQL table, so the factory finds real cross-repo, cross-language duplicates;
owners are randomized so both RETIRE (same team) and STANDARDIZE (cross-team)
plays appear.

    python scripts/generate_portfolio.py <out_dir> [n]
"""
from __future__ import annotations

import os
import random
import sys

DOMAINS = ["orders", "payments", "inventory", "shipping", "customers",
           "catalog", "billing", "notifications", "auth", "pricing",
           "returns", "loyalty"]
TEAMS = ["team-alpha", "team-beta", "team-gamma", "team-delta", "team-omega"]
LANGS = ["python", "java", "sql", "node"]


def _w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def gen_python(repo, domain, topic, table):
    _w(f"{repo}/app.py", f'''from kafka import KafkaProducer
import psycopg2

{domain.upper()}_TOPIC = "{topic}"


def publish(producer, event):
    producer.send({domain.upper()}_TOPIC, event)


def save(conn, row):
    cur = conn.cursor()
    cur.execute("INSERT INTO {table} (id, name, status) VALUES (%s, %s, %s)", row)
    conn.commit()
''')
    _w(f"{repo}/requirements.txt", "kafka-python==2.0.2\npsycopg2-binary==2.9.9\nrequests==2.31.0\n")


def gen_java(repo, domain, topic, table):
    cls = domain.capitalize() + "Service"
    _w(f"{repo}/src/{cls}.java", f'''package com.acme.{domain};

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.data.jpa.repository.Query;

public class {cls} {{
    @Value("${{kafka.topic.{domain}}}")
    private String topic;

    private KafkaTemplate<String, String> kafkaTemplate;

    public void emit(String event) {{
        kafkaTemplate.send(topic, event);
    }}

    @Query("SELECT x FROM {table} x")
    public Object all() {{ return null; }}
}}
''')
    _w(f"{repo}/src/application.yml", f"kafka:\n  topic:\n    {domain}: {topic}\n")
    _w(f"{repo}/pom.xml", '''<project><modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId><artifactId>svc</artifactId><version>1.0.0</version>
  <dependencies>
    <dependency><groupId>org.springframework.kafka</groupId><artifactId>spring-kafka</artifactId><version>3.1.0</version></dependency>
    <dependency><groupId>org.springframework.data</groupId><artifactId>spring-data-jpa</artifactId><version>3.2.0</version></dependency>
  </dependencies></project>
''')


def gen_sql(repo, domain, topic, table):
    _w(f"{repo}/schema.sql", f'''CREATE TABLE IF NOT EXISTS {table} (
    id     INTEGER PRIMARY KEY,
    name   TEXT,
    status TEXT
);
''')


def gen_node(repo, domain, topic, table):
    _w(f"{repo}/index.js", f'''const {{ Kafka }} = require("kafkajs");
const axios = require("axios");

const {domain.upper()}_TOPIC = "{topic}";

async function run(producer, event) {{
  await producer.send({{ topic: {domain.upper()}_TOPIC, messages: [{{ value: event }}] }});
  await axios.get("http://gateway/{domain}");
}}

module.exports = {{ run }};
''')
    _w(f"{repo}/package.json",
       '{\n  "name": "%s-svc",\n  "dependencies": {"kafkajs": "^2.2.4", "axios": "^1.6.0"}\n}\n' % domain)


GEN = {"python": gen_python, "java": gen_java, "sql": gen_sql, "node": gen_node}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "portfolio"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    rng = random.Random(42)
    os.makedirs(out, exist_ok=True)

    made = 0
    for i in range(n):
        domain = DOMAINS[i % len(DOMAINS)]
        lang = rng.choice(LANGS)
        topic = f"{domain}.changed"
        table = domain
        # ~25% of repos are "unique" (own topic/table) -> not shared duplicates
        if rng.random() < 0.25:
            topic = f"{domain}.internal{i}"
            table = f"{domain}_{i}"
        name = f"{domain}-{lang}-{i:03d}"
        repo = os.path.join(out, name)
        GEN[lang](repo, domain, topic, table)
        _w(f"{repo}/OWNER", rng.choice(TEAMS) + "\n")
        made += 1

    print(f"generated {made} repos in {out}")


if __name__ == "__main__":
    main()
