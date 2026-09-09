"""M1.5 — capability summaries.

The production `RestSummarizer` asks a self-hosted LLM for a short, language-
neutral description of what a module does. `HeuristicSummarizer` derives one from
the module's already-extracted facts (topics, tables, calls, deps) and manifest
descriptions (package.json, pom.xml, pyproject.toml, README) — no model
required — which is enough to drive recall across heterogeneous portfolios and
doubles as a dependable fallback when the LLM is unavailable.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Protocol

from convergence_factory.core.schema import IntegrationFact


class Summarizer(Protocol):
    def summarize(self, module_name: str, facts: List[IntegrationFact],
                  deps: List[str], module_path: str = "") -> str: ...


class HeuristicSummarizer:
    def summarize(self, module_name: str, facts: List[IntegrationFact],
                  deps: List[str], module_path: str = "") -> str:
        verbs = {"PRODUCES": "publishes", "CONSUMES": "consumes",
                 "READS": "reads", "WRITES": "writes", "CALLS": "calls"}
        parts = []
        for f in facts:
            noun = {"KAFKA_TOPIC": "event", "SQL_TABLE": "table",
                    "HTTP_ENDPOINT": "endpoint"}.get(f.resource_type, "resource")
            parts.append(f"{verbs.get(f.direction, f.direction.lower())} {noun} {f.resource_id}")

        meta_desc = ""
        if module_path and os.path.exists(module_path):
            # 1. package.json
            pkg = os.path.join(module_path, "package.json")
            if os.path.exists(pkg):
                try:
                    with open(pkg, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                    meta_desc = data.get("description", "")
                except Exception:
                    pass
            # 2. pom.xml
            pom = os.path.join(module_path, "pom.xml")
            if not meta_desc and os.path.exists(pom):
                try:
                    with open(pom, "r", encoding="utf-8", errors="ignore") as f:
                        pom_txt = f.read()
                    m = re.search(r"<description>(.*?)</description>", pom_txt, re.DOTALL)
                    if m:
                        meta_desc = " ".join(m.group(1).split())
                except Exception:
                    pass
            # 3. pyproject.toml / setup.py
            pypr = os.path.join(module_path, "pyproject.toml")
            if not meta_desc and os.path.exists(pypr):
                try:
                    with open(pypr, "r", encoding="utf-8", errors="ignore") as f:
                        pypr_txt = f.read()
                    m = re.search(r'description\s*=\s*["\'](.*?)["\']', pypr_txt)
                    if m:
                        meta_desc = m.group(1).strip()
                except Exception:
                    pass
            # 4. README
            if not meta_desc:
                for rd in ("README.md", "README.rst", "README.txt", "readme.md"):
                    rf = os.path.join(module_path, rd)
                    if os.path.exists(rf):
                        try:
                            with open(rf, "r", encoding="utf-8", errors="ignore") as f:
                                rtext = f.read()
                            m_img = re.search(r'!\[([^\]]{15,})\]', rtext)
                            if m_img:
                                alt = m_img.group(1).strip()
                                if not any(ign in alt.lower() for ign in ("build", "status", "coverage", "license", "badge", "npm", "stars")):
                                    meta_desc = alt
                            if not meta_desc:
                                for line in rtext.splitlines():
                                    clean = re.sub(r'<[^>]+>', '', line).strip()
                                    if clean and len(clean) > 15 and not clean.startswith(("#", "=", "-", "<", "[", "!", ">", "*", ":", "|", "`")):
                                        meta_desc = clean[:200]
                                        break
                        except Exception:
                            pass
                        if meta_desc:
                            break

        summary_parts = [f"{module_name}:"]
        if meta_desc:
            summary_parts.append(meta_desc)
        if parts:
            summary_parts.append("; ".join(sorted(set(parts))))
        if deps:
            summary_parts.append("uses " + ", ".join(sorted(set(deps))[:6]))
        return " ".join(summary_parts)


class RestSummarizer:
    def __init__(self, url: str = ""):
        self.url = url

    def summarize(self, module_name, facts, deps, module_path: str = ""):  # pragma: no cover
        raise NotImplementedError(
            "RestSummarizer is a stub. Point it at your self-hosted LLM, or use "
            "HeuristicSummarizer for a local run.")
