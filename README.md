# Convergence Factory

A layered evidence pipeline that turns a portfolio of heterogeneous repositories
into a ranked **redundancy map** of duplicate functionality and convergence
opportunities. Built to answer the question off-the-shelf tools don't: *"which
projects do the same thing?"* — across languages, including at the wiring level
(the same Kafka topic, the same SQL table), not just copied code.

See the architecture blueprint: [BLUEPRINT.md](file:///Users/mahesh/Dev/bootcamps/convergence-factory/BLUEPRINT.md) for the full architectural design.

## Design in one line

The **normalized schema is the contract** ([schema.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/schema.py)). Plugins read a repo in their language
and emit normalized facts; the core consumes only those and never learns a
language. Adding a technology touches only `plugins/` and `fixtures/` — never
`core/`.

```
src/convergence_factory/
  schema.py            the normalized fact contract (version 0.1)
  store.py             fact store (SQLite) with SHA-256 incremental caching
  runner.py            orchestrates plugin execution over scanned repos
  graph.py             derives similarity graph and convergence clusters
  clone_probe.py       tokenized line hashing for Type 1 & 2 code clones
  ratchet.py           one-way CI governance ratchet generator
  report.py            redundancy map visualizer (Mermaid.js + live search)
  census.py            manifest scanning and language resolution
  resolver.py          config and constant resolver (properties, YAML)
  eval.py              precision, recall, and resolution benchmark evaluator
  plugins/             lang_python.py · lang_java.py · lang_sql.py
  semantic/            probe.py (vector recall) · judge.py (pairwise LLM judge)
  executors/           rewrite.py (declarative OpenRewrite recipes)
  connectors/          gitlab.py (GitLab inventory connector & shallow clone sync)
pipelines/
  flow.py              Prefect / Dagster orchestration with incremental caching
```

## Run it

No third-party dependencies required — the analytical core runs entirely on the standard library.

```bash
# full pipeline over the bundled Java + Python + SQL fixtures -> redundancy map
PYTHONPATH=src python3 -m convergence_factory run

# run full pipeline with pairwise semantic judge, governance ratchets, and refactoring recipes
PYTHONPATH=src python3 -m convergence_factory run --judge --ratchet --rewrite

# the project manifest only (census)
PYTHONPATH=src python3 -m convergence_factory census

# the calibration eval (precision / recall / resolution rate)
PYTHONPATH=src python3 -m convergence_factory eval

# evaluate semantic candidates with the Pairwise Judge
PYTHONPATH=src python3 -m convergence_factory judge

# generate CI/CD One-Way Governance Ratchets (ArchUnit, Import-Linter, dependency-cruiser)
PYTHONPATH=src python3 -m convergence_factory ratchet

# generate OpenRewrite declarative refactoring recipes
PYTHONPATH=src python3 -m convergence_factory rewrite
```

The interactive redundancy map is written to `.factory/site/index.html`.

### Sharper probes (optional)

```bash
pip install -e ".[sql,config,orchestration]"   # sqlglot, pyyaml, prefect
```

Point `semantic/embedder.RestEmbedder`, `semantic/summarizer.RestSummarizer`, and `semantic/judge.RestJudge`
at your self-hosted models for the semantic layer; the `Hashing`/`Heuristic`
defaults keep local runs dependency-free and reproducible.

## Confidence tiers

Every fact carries a tier — `HIGH` (literal/deterministic / code clone), `MED`
(config-resolved / embedding similarity / judge-confirmed), `LOW` (unconfirmed candidate recall). The
report's tier filter serves three audiences: exec (HIGH),
prioritization (+MED), exploratory (all).

