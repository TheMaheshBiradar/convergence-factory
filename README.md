# Convergence Factory

A layered evidence pipeline that turns a portfolio of heterogeneous repositories
into a ranked **redundancy map** of duplicate functionality and convergence
opportunities. Built to answer the question off-the-shelf tools don't: *"which
projects do the same thing?"* — across languages, including at the wiring level
(the same Kafka topic, the same SQL table), not just copied code.

See the architecture blueprint and the phase plan for the full design.

## Design in one line

The **normalized schema is the contract**. Plugins read a repo in their language
and emit normalized facts; the core consumes only those and never learns a
language. Adding a technology touches only `plugins/` and `fixtures/` — never
`core/`.

```
core/                the parts built once (schema, runner, graph, analytics, resolver)
plugins/             lang-python (ast) · lang-sql (sqlglot) · lang-java (JVM sidecar)
semantic/            embeddings + LLM summaries — cross-language recall
report/ (report.py)  the redundancy map (static site / GitLab Pages)
fixtures/            calibration repos + expected facts (golden tests)
pipelines/           orchestration over the portfolio
```

## Run it

No third-party dependencies required — it runs on the standard library.

```bash
# full pipeline over the bundled Java + Python + SQL fixtures -> redundancy map
PYTHONPATH=src python3 -m convergence_factory run

# the project manifest only (census)
PYTHONPATH=src python3 -m convergence_factory census

# the calibration eval (precision / recall / resolution rate)
PYTHONPATH=src python3 -m convergence_factory eval
```

The map is written to `.factory/site/index.html`.

### Sharper probes (optional)

```bash
pip install -e ".[sql,config]"   # sqlglot for real SQL parsing, pyyaml for config
```

Point `semantic/embedder.RestEmbedder` and `semantic/summarizer.RestSummarizer`
at your self-hosted models for the semantic layer; the `Hashing`/`Heuristic`
defaults keep local runs dependency-free and reproducible.

## Confidence tiers

Every fact carries a tier — `HIGH` (literal/deterministic), `MED`
(config-resolved / embedding similarity), `LOW` (LLM-asserted, unconfirmed). The
report's tier filter is the same pipeline serving three audiences: exec (HIGH),
prioritization (+MED), exploratory (all).
