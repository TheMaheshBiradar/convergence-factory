# Convergence Factory — Architecture Blueprint & Design

> A layered evidence pipeline that turns a heterogeneous portfolio of ~200 repositories into a ranked **redundancy map** of duplicate functionality and convergence opportunities.

---

## 1. System Vision & Core Design Principles

Traditional code analysis tools (SonarQube, jscpd, CodeQL) answer single-repo, syntax-bound questions. They do not answer the strategic enterprise question:
> **"Which projects across the organization perform the same business capability?"**

Convergence Factory detects functional duplication across multiple languages (Java, Python, SQL) and across architectural tiers—specifically at the **wiring level** (e.g., publishing to the same Kafka topic, reading/writing the same SQL tables), even when zero lines of code are shared.

```
┌────────────────────────────────────────────────────────────────────────┐
│                          5 EVIDENCE PROBES                             │
│  [Code-Clone]   [BOM/Deps]   [API/Contract]   [Integration]   [Semantic]│
└───────┬──────────────┬──────────────┬───────────────┬──────────────┬───┘
        │              │              │               │              │
        └──────────────┴──────────────┼───────────────┴──────────────┘
                                      ▼
                      ┌───────────────────────────────┐
                      │   Normalized Fact Schema      │
                      │   (Single source of truth)    │
                      └───────────────┬───────────────┘
                                      ▼
                      ┌───────────────────────────────┐
                      │   SQLite Graph & Metrics      │
                      └───────────────┬───────────────┘
                                      ▼
                      ┌───────────────────────────────┐
                      │    Convergence Engine         │
                      │  (Clustering + Opportunity)   │
                      └───────────────┬───────────────┘
                                      ▼
                      ┌───────────────────────────────┐
                      │    Redundancy Map Report      │
                      │  (Executive, Prioritized, All)│
                      └───────────────────────────────┘
```

### Core Tenet: Normalized Schema is the Contract
The core system never learns programming languages.
- **Core modules**: [schema.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/schema.py), [store.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/store.py), [runner.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/runner.py), [graph.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/graph.py), [report.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/report.py). Built once.
- **Language Plugins**: [lang_python.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/plugins/lang_python.py), [lang_java.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/plugins/lang_java.py), [lang_sql.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/plugins/lang_sql.py). Ingest repo ASTs and emit standardized `FactBundle` objects.
- **Code Clones**: [clone_probe.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/clone_probe.py). Detects Type 1 & 2 cross-module clones.
- **Semantic Layer**: [probe.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/semantic/probe.py), [judge.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/semantic/judge.py). Vector recall and LLM pairwise verification.
- **Executors & Bridges**: [ratchet.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/ratchet.py), [rewrite.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/executors/rewrite.py), [gitlab.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/connectors/gitlab.py).

---

## 2. The 5 Evidence Probes

| # | Probe | Technique | Target Artifacts | Primary Signal |
|---|---|---|---|---|
| 1 | **Integration / Dataflow** | Framework AST + Config resolver | Kafka producers/consumers, JPA/SQL, HTTP clients | Shared event topics, database tables, downstream services |
| 2 | **Capability / Semantic** | LLM Summarizer + Vector Embeddings + Pairwise Judge | Function/class summaries embedded into vector space | Cross-language semantic similarity (recall) confirmed by judge |
| 3 | **API / Contract** | AST & OpenAPI parser | Spring `@RestController`, FastAPI routes, gRPC stubs | Identical endpoint paths, payloads, or schemas |
| 4 | **Dependency / BOM** | Build file parsers | `pom.xml`, `requirements.txt`, `package.json` | Shared frameworks, divergence in library versions |
| 5 | **Code Clone** | Tokenized source line hashing | Raw source trees | Direct copy-paste (Type 1) & parameterized clones (Type 2) |

---

## 3. Confidence Tiers & Defensibility

Every fact emitted carries a strict **confidence tier** to preserve executive defensibility:
* **`HIGH` (Deterministic)**: Extracted from literal string constants or verified AST signatures (e.g., `kafkaTemplate.send("order.created", msg)`), or Type 1/2 code clones.
* **`MED` (Config-Resolved / Proximity / Judge-Confirmed)**: Extracted via property lookup (e.g., `@Value("${kafka.topic.order}")` resolved from `application.yml`), high-confidence embedding similarity, or semantic candidate pairs confirmed by the Pairwise Judge.
* **`LOW` (Exploratory Recall)**: Unconfirmed candidate pairs surfaced by embedding nearest neighbors prior to judge evaluation.

The Redundancy Map UI provides immediate tier-based filtering:
1. **Exec View (`HIGH`)**: Only undeniable, hard-evidence overlaps.
2. **Prioritization View (`+MED`)**: Adds config-resolved relationships and confirmed semantic pairs for portfolio planning.
3. **Exploratory View (`ALL`)**: Full candidate recall for deep investigation.

---

## 4. Opportunity Scoring & Coupling Discounting

Raw duplication does not equal easy convergence. If two duplicate capabilities are deeply entangled in their respective codebases, the cost of convergence exceeds the benefit.

$$\text{Opportunity} = \text{Score}_{\text{raw}} \times (1 - \text{Coupling})$$

Where:
* $\text{Score}_{\text{raw}} = |\text{Shared Resources}| \times |\text{Members}| + (2 \text{ if duplicate writer/producer else } 0)$
* $\text{Coupling} \in [0.0, 1.0]$: Internal import graph density of the module ($\frac{\text{directed edges}}{n(n-1)}$), extracted via Python and Java AST parsers.
* **Convergence Plays**:
  * **`STANDARDIZE`**: Multi-team duplication on the same resource (requires cross-team consensus).
  * **`RETIRE`**: Single-team internal duplication (safe to sunset immediately).
  * **`EXTRACT`**: Shared library / common service extraction candidate.
  * **`LEAVE`**: High coupling or negligible overlap.

---

## 5. Architectural Tool Matrix

The following external libraries and analyzers interface with the Convergence Factory:

| Library | Primary Language | Graph / Evidence Output | One-Way Ratchet Support | Dead / Orphan Code | Role in Convergence Factory |
|---|---|---|---|---|---|
| **OpenRewrite** | Java / Build | LST / Recipe trees | ✅ Recipes | ✅ Cleanups | **Strategic Execution**: Full type-attributed Java LST and automated cross-repo refactoring executor for `STANDARDIZE` plays. |
| **SQLGlot** | SQL / Multi-dialect | DAG / Lineage JSON | ❌ | ✅ Unused CTEs | **In-Core Probe**: Extracts table read/write lineage, column-level mapping, and identifies orphaned SQL queries. |
| **Grimp / Import-Linter** | Python | CLI, JSON | ✅ Contracts | ❌ | **Coupling & Ratchet**: Computes Python internal import graphs (coupling factor) and enforces layer boundaries. |
| **dependency-cruiser** | JS / TS | DOT, Mermaid, JSON | ✅ `no-legacy-in-target` | ✅ `no-orphans` | **JS Plugin Engine**: Provides internal module graph, orphan detection, and blast radius calculation for TypeScript/JavaScript. |
| **jQAssistant** | Java / Polyglot | Neo4j / Cypher | ✅ Cypher rules | ✅ Cypher queries | **Scale-Up Graph Store**: Migration target for scaling graph storage beyond local SQLite to enterprise Neo4j. |
| **SchemaCrawler** | Oracle / PostgreSQL | Graphviz, SVG | ✅ Linter rules | ✅ Orphan tables | **Live DB Catalog**: Traverses foreign keys, live database schemas, and flags orphan database tables. |
| **Knip** | JS / TS / React | CLI, JSON | ❌ | ✅ Unused exports | **Dead Code Signal**: Identifies unused exports, dependencies, and dead components in frontend modules. |
| **ArchUnit** | Java | PlantUML, Text | ✅ `FreezingArchRule` | ❌ | **Governance Ratchet**: Enforces Java architectural boundaries in CI/CD via unit tests. |
| **Graphify (graphifyy)** | Polyglot (Tree-sitter) | `graph.json`, `graph.html` | ✅ Path constraints | ✅ Disconnected / God nodes | **Deep Code Knowledge Graph**: Builds intra-repo call and import graphs from AST; provides `graph.json` schema interoperability with Convergence Factory. |

---

## 6. The "One-Way Ratchet" Governance Strategy

A critical challenge in enterprise rationalization is **post-convergence regression**: once duplicate systems are merged or retired, developers unconsciously recreate the duplicate functionality in new services.

The **One-Way Ratchet** solves this by installing automated CI guardrails at convergence time via [ratchet.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/ratchet.py):

```
[Redundancy Map] ──► [Convergence Play: RETIRE] ──► [Install One-Way Ratchet]
                                                             │
                                                             ▼
                                                [CI/CD Build Pipeline]
                                                ├── ArchUnit FreezingRule
                                                ├── Import-Linter Contract
                                                └── dependency-cruiser Rule
                                                             │
                                                             ▼
                                                Blocks new duplication / legacy calls
```

1. **Snapshot Current Debt**: Tools like `ArchUnit` (`FreezingArchRule`) or `Import-Linter` baseline existing violations without breaking existing builds.
2. **Block New Infractions**: Any pull request introducing a new dependency to a retired module or duplicate event topic is automatically rejected.
3. **Ratchet Downward**: As legacy code is eliminated, the baseline is automatically lowered and never permitted to increase.

---

## 7. Phase 1.5: The Pairwise Semantic Judge

Vector embeddings generate wide recall of candidate pairs that may share functional intent without shared code or wiring. The Pairwise Judge ([judge.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/semantic/judge.py)) prevents false-positive hallucinations by performing deep semantic comparison:
- **`HeuristicJudge`**: Zero-dependency domain term tokenizer and overlap scorer for deterministic CI.
- **`RestJudge`**: Pluggable client for self-hosted LLM endpoints (vLLM, Ollama, private cloud).
- **Cluster Promotion**: Confirmed pairs graduate into the formal convergence graph with calculated opportunity scores and assigned plays (`RETIRE` for intra-team duplicates, `STANDARDIZE` for cross-team duplicates).

---

## 8. Phase 2: OpenRewrite Refactoring Executor

Automated convergence is realized through [rewrite.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/executors/rewrite.py):
- Automatically produces declarative `rewrite.yml` recipes for `STANDARDIZE` and `RETIRE` plays.
- Generates `run_rewrite.sh` to execute `mvn rewrite:run` across Java repositories, migrating topic strings, property values, and class types deterministically.

---

## 9. Enterprise Scalability: Connectors & Incremental Caching

- **GitLab Connector**: [gitlab.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/connectors/gitlab.py) ingests GitLab inventory structures and syncs shallow clones.
- **SHA-256 Incremental Caching**: [flow.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/pipelines/flow.py) hashes source trees and reuses extracted facts in `scan_cache`, achieving 100% cache hits on clean repeat runs.
- **Visual Topology**: [report.py](file:///Users/mahesh/Dev/bootcamps/convergence-factory/src/convergence_factory/report.py) embeds real-time Mermaid.js wiring diagrams and live client-side search into the published redundancy map.
