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

---

## 2. The 5 Evidence Probes

| # | Probe | Technique | Target Artifacts | Primary Signal |
|---|---|---|---|---|
| 1 | **Integration / Dataflow** | Framework AST + Config resolver | Kafka producers/consumers, JPA/SQL, HTTP clients | Shared event topics, database tables, downstream services |
| 2 | **Capability / Semantic** | LLM Summarizer + Vector Embeddings | Function/class summaries embedded into vector space | Cross-language semantic similarity (recall) |
| 3 | **API / Contract** | AST & OpenAPI parser | Spring `@RestController`, FastAPI routes, gRPC stubs | Identical endpoint paths, payloads, or schemas |
| 4 | **Dependency / BOM** | Build file parsers | `pom.xml`, `requirements.txt`, `package.json` | Shared frameworks, divergence in library versions |
| 5 | **Code Clone** | Token/AST similarity | Raw source trees | Direct copy-paste / fork divergence |

---

## 3. Confidence Tiers & Defensibility

Every fact emitted carries a strict **confidence tier** to preserve executive defensibility:
* **`HIGH` (Deterministic)**: Extracted from literal string constants or verified AST signatures (e.g., `kafkaTemplate.send("order.created", msg)`).
* **`MED` (Config-Resolved / Proximity)**: Extracted via property lookup (e.g., `@Value("${kafka.topic.order}")` resolved from `application.yml`) or high-confidence embedding similarity.
* **`LOW` (Exploratory Recall)**: Unconfirmed LLM-generated assertions or tentative semantic matches requiring human / judge confirmation.

The Redundancy Map UI provides immediate tier-based filtering:
1. **Exec View (`HIGH`)**: Only undeniable, hard-evidence overlaps.
2. **Prioritization View (`+MED`)**: Adds config-resolved relationships for portfolio planning.
3. **Exploratory View (`ALL`)**: Full candidate recall for deep investigation.

---

## 4. Opportunity Scoring & Coupling Discounting

Raw duplication does not equal easy convergence. If two duplicate capabilities are deeply entangled in their respective codebases, the cost of convergence exceeds the benefit.

$$\text{Opportunity} = \text{Score}_{\text{raw}} \times (1 - \text{Coupling})$$

Where:
* $\text{Score}_{\text{raw}} = |\text{Shared Resources}| \times |\text{Members}| + (2 \text{ if duplicate writer/producer else } 0)$
* $\text{Coupling} \in [0.0, 1.0]$: Internal import graph density of the module ($\frac{\text{directed edges}}{n(n-1)}$).
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

---

## 6. The "One-Way Ratchet" Governance Strategy

A critical challenge in enterprise rationalization is **post-convergence regression**: once duplicate systems are merged or retired, developers unconsciously recreate the duplicate functionality in new services.

The **One-Way Ratchet** solves this by installing automated CI guardrails at convergence time:

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
