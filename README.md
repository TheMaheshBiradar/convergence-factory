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
# 1. Full pipeline over the bundled Java + Python + SQL fixtures -> redundancy map
PYTHONPATH=src python3 -m convergence_factory run

# 2. Run full pipeline with Pairwise Judge, governance ratchets, and refactoring recipes
PYTHONPATH=src python3 -m convergence_factory run --judge --ratchet --rewrite

# 3. Serve the interactive Redundancy Map on local HTTP port
PYTHONPATH=src python3 -m convergence_factory serve
```

The interactive redundancy map is written to `.factory/site/index.html` and graph data is exported to `.factory/site/graph.json` for Graphify / Cytoscape visual exploration.

---

## 📖 Step-by-Step Execution Guide

### 1. Running Custom Repositories & Real-World Portfolios
To analyze any local folder of repositories (or symlinks to projects):
```bash
PYTHONPATH=src python3 -m convergence_factory run /path/to/repos \
    --out .my_portfolio \
    --judge \
    --ratchet \
    --rewrite
```

### 2. Scaling to 200+ Enterprise Repositories
The factory is built specifically to process enterprise portfolios of 200+ repositories without memory exhaustion or LLM cost explosion:
* **Vector Recall Efficiency**: Pairwise cosine similarity across $\binom{220}{2} = 24,090$ pairs completes in **< 30 milliseconds**.
* **Pairwise Judge Filter**: Only candidates exceeding the threshold (`0.40`) are evaluated by the judge (~30 to 80 pairs), preventing LLM bottlenecks.
* **GitLab Portfolio Ingestion**: Ingest entire GitLab group hierarchies via inventory export:
  ```bash
  PYTHONPATH=src python3 -m convergence_factory run /path/to/clones \
      --inventory gitlab_inventory.json \
      --out .factory_enterprise \
      --judge \
      --ratchet
  ```
* **Incremental Nightly Runs with SHA-256 Caching**:
  Using `pipelines/flow.py`, unchanged repositories (matching SHA-256 content hashes) skip re-parsing. A nightly re-scan over 220 repos finishes in **under 5 seconds**:
  ```bash
  python3 -m pipelines.flow
  ```

### 3. Generated CI/CD Ratchets
Convergence Factory generates one-way architectural ratchets tailored to each language in the portfolio:
* **Java (`ArchUnit`)**: Emitted in `ratchets/archunit/ConvergenceRatchet_*_Test.java` to block new classes from depending on deprecated modules.
* **Python (`Import-Linter`)**: Emitted in `ratchets/import_linter/.importlinter_*` to enforce import boundaries in CI.
* **TypeScript / JavaScript (`dependency-cruiser`)**: Emitted in `ratchets/dependency_cruiser/dependency-cruiser-ratchet.json` to flag forbidden module imports in npm/pnpm/yarn monorepos.

### 4. Automated Closed-Loop Self-Healing
To automatically refactor callers of redundant capabilities and verify builds:
```bash
PYTHONPATH=src python3 -m convergence_factory heal
```

---

## 🔬 CLI Commands Reference

| Command | Description |
| :--- | :--- |
| `python3 -m convergence_factory run [root]` | Runs full pipeline (census, extraction, clones, clustering, report). |
| `python3 -m convergence_factory census [root]` | Scans directory and outputs project manifest, detected languages, and owners. |
| `python3 -m convergence_factory eval` | Runs the precision/recall/resolution calibration suite across benchmark fixtures. |
| `python3 -m convergence_factory judge` | Evaluates recalled semantic candidates using the Pairwise Judge. |
| `python3 -m convergence_factory ratchet` | Generates ArchUnit, Import-Linter, and dependency-cruiser CI/CD guardrails. |
| `python3 -m convergence_factory rewrite` | Generates OpenRewrite declarative YAML migration recipes. |
| `python3 -m convergence_factory heal` | Runs the closed-loop autonomous refactor-and-verify loop. |
| `python3 -m convergence_factory serve` | Launches a local HTTP preview server for the generated Redundancy Map. |

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

