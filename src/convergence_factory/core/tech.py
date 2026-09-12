"""Tech-standard analysis — the 'find the golden stack' view.

Across the portfolio, what technology is standard and where does it diverge?
For each capability category (messaging client, http client, db access, test
framework, web framework, ...), the most-used library is the de-facto standard
and the rest are standardization candidates. Also reports the language and
build-system spread. Reads only what the probes already extracted (dependencies,
module langs) — no new parsing.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List

from .store import Store

# category -> the libraries (lowercased) that fulfil it across ecosystems
CATEGORIES: Dict[str, set] = {
    "messaging client": {"kafka-python", "confluent-kafka", "aiokafka", "kafkajs",
                         "spring-kafka", "pika", "amqplib"},
    "http client": {"requests", "httpx", "urllib3", "axios", "node-fetch",
                    "got", "spring-web", "okhttp", "feign"},
    "db access": {"psycopg2", "psycopg2-binary", "sqlalchemy", "spring-data-jpa",
                  "hibernate", "pg", "mysql2", "mongoose", "sequelize", "prisma"},
    "test framework": {"pytest", "unittest", "junit", "junit-jupiter", "jest",
                       "mocha", "vitest", "jasmine"},
    "web framework": {"flask", "fastapi", "django", "express", "koa", "nestjs",
                      "react", "react-dom", "angular", "vue", "spring-boot"},
    "serialization": {"jackson", "gson", "pydantic", "marshmallow", "zod"},
    "auth / jwt": {"pyjwt", "python-jose", "jsonwebtoken", "java-jwt", "jose",
                   "passport", "spring-security"},
}


def _dep_name(purl: str) -> str:
    return purl.split("/")[-1].split("@")[0].lower()


def analyze_tech(store: Store) -> dict:
    """Return language/build spread + per-category standard vs outliers."""
    modules = store.modules()
    languages = dict(Counter(m.lang for m in modules if m.lang).most_common())
    builds = dict(Counter(m.build_system for m in modules if m.build_system).most_common())

    lib_mods: Dict[str, set] = defaultdict(set)
    for r in store.db.execute("SELECT module_id, purl FROM dependencies"):
        lib_mods[_dep_name(r["purl"])].add(r["module_id"])

    categories: List[dict] = []
    for cat, libs in CATEGORIES.items():
        usage = {lib: len(lib_mods[lib]) for lib in libs if lib_mods.get(lib)}
        if not usage:
            continue
        standard = max(usage, key=usage.get)
        outliers = sorted(l for l in usage if l != standard)
        categories.append({
            "category": cat, "standard": standard, "usage": usage,
            "outliers": outliers, "fragmentation": len(usage),
            "outlier_modules": sorted({m for l in outliers for m in lib_mods[l]}),
        })
    categories.sort(key=lambda c: (-c["fragmentation"], c["category"]))

    return {"languages": languages, "builds": builds, "categories": categories}


def summarize(tech: dict) -> dict:
    fragmented = [c["category"] for c in tech["categories"] if c["fragmentation"] > 1]
    return {"languages": tech["languages"],
            "fragmented_categories": fragmented,
            "standards": {c["category"]: c["standard"] for c in tech["categories"]}}
