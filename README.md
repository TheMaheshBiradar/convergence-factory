# Convergence Factory

A layered evidence pipeline that turns a portfolio of heterogeneous repositories
into a ranked **redundancy map** of duplicate functionality and convergence
opportunities. Built to answer the question off-the-shelf tools don't: *"which
projects do the same thing?"* — across languages, including at the wiring level
(the same Kafka topic, the same SQL table), not just copied code.

See the architecture blueprint: [BLUEPRINT.md](file:///Users/mahesh/Dev/bootcamps/convergence-factory/BLUEPRINT.md) for the full architectural design.

## Design in one line

The **normalized schema is the contract** ([schema.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/core/schema.py)). Probes read a repo in their language
and emit normalized facts; the core consumes only those and never learns a
language. Adding a technology touches only `probes/` and `fixtures/` — never
`core/`.

```
src/convergence_factory/
├── core/                        # Pure Analytical Core (Standard Library Only)
│   ├── schema.py                # Normalized Schema Contract (v0.1) & Validation
│   ├── store.py                 # SQLite FactStore with SHA-256 cache
│   ├── resolver.py              # Configuration & constant resolver (YAML/props/env)
│   └── graph.py                 # Union-Find clustering & opportunity formula
│
├── probes/                      # The 5 Blueprint Evidence Probes
│   ├── integration/             # Probe 1: Integration & Dataflow (AST Plugins)
│   │   ├── lang_python.py       # Python AST & import coupling analyzer
│   │   ├── lang_java.py         # Java Tree-Sitter & annotation analyzer
│   │   ├── lang_sql.py          # SQL read/write table lineage extractor
│   │   └── lang_node.py         # JavaScript/TypeScript AST & package.json
│   ├── semantic/                # Probe 2: Capability & Semantic Recall
│   │   ├── probe.py             # Nearest-neighbor vector recall pipeline
│   │   ├── judge.py             # Pairwise Judge (Heuristic & REST LLM)
│   │   ├── embedder.py          # Char-n-gram & embedding adapters
│   │   └── summarizer.py        # Language-neutral capability summarization
│   ├── contracts/               # Probe 3: API & Contract Surfaces (REST, gRPC)
│   ├── bom/                     # Probe 4: Dependency & BOM Manifests
│   └── clones/                  # Probe 5: Code Clone Detection (Type 1 & 2)
│       └── clone_probe.py       # Tokenized line hashing
│
├── remediation/                 # Action, Refactoring & Governance Layer
│   ├── ratchets/                # One-Way CI/CD Ratchet Guardrails
│   │   └── ratchet.py           # ArchUnit, Import-Linter, dependency-cruiser
│   ├── refactoring/             # OpenRewrite Declarative Recipes
│   │   └── rewrite.py           # rewrite.yml & run_rewrite.sh generator
│   └── healing/                 # Automated Closed-Loop Self-Healing Engine
│       └── heal.py              # Closed-loop refactoring, verification & ratcheting
│
├── ingestion/                   # Portfolio Ingestion & Census
│   ├── census.py                # Repository census & primary detection
│   ├── caching.py               # SHA-256 repo content hashing
│   └── connectors/              # Portfolio Source Connectors
│       └── gitlab.py            # GitLab inventory parser & shallow clone sync
│
├── exporters/                   # Visualization & Interoperability
│   ├── report.py                # Redundancy Map generator & HTML template
│   ├── mermaid.py               # Mermaid.js topology generator
│   └── graphify.py              # Graphify & Cytoscape graph.json exporter
│
├── runner.py                    # Multi-language extraction dispatcher
├── eval.py                      # Calibration benchmark evaluator
├── cli.py                       # Unified CLI dispatcher
└── [facades]                    # Root re-exports for 100% backward compatibility
pipelines/
└── flow.py                      # Prefect / Dagster orchestration with incremental caching
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

# run automated closed-loop self-healing
PYTHONPATH=src python3 -m convergence_factory heal

# serve the interactive Redundancy Map on local HTTP port
PYTHONPATH=src python3 -m convergence_factory serve
```

The interactive redundancy map is written to `.factory/site/index.html` and graph data is exported to `.factory/site/graph.json` for Graphify / Cytoscape visual exploration.

### Sharper probes (optional)

```bash
pip install -e ".[sql,config,orchestration]"   # sqlglot, pyyaml, prefect
```

Point `RestEmbedder`, `RestSummarizer`, and `RestJudge`
at your self-hosted models for the semantic layer; the `Hashing`/`Heuristic`
defaults keep local runs dependency-free and reproducible.

## Confidence tiers

Every fact carries a tier — `HIGH` (literal/deterministic / code clone), `MED`
(config-resolved / embedding similarity / judge-confirmed), `LOW` (unconfirmed candidate recall). The
report's tier filter serves three audiences: exec (HIGH),
prioritization (+MED), exploratory (all).
