# Architecture

The Convergence Factory turns a portfolio of heterogeneous repositories into a
ranked **redundancy map** of duplicate functionality and convergence
opportunities. The design rests on one invariant:

> **The normalized schema is the contract.** Plugins read a repo in their
> language and emit normalized facts; the core consumes only those facts and
> never learns a language. Adding a technology touches `probes/` and
> `fixtures/` — never `core/`.

## Package layout

```
convergence_factory/
  core/          the parts built once
    schema.py      the normalized fact model (the plugin <-> core contract)
    store.py       SQLite fact store (swap for DuckDB/Parquet at scale)
    graph.py       derives the similarity graph, clusters, scores, tags a play
    resolver.py    shared config/constant resolution (topics & tables in config)
  probes/        the evidence extractors (see docs/probes.md)
    integration/   language plugins: lang_python, lang_java, lang_sql, lang_node
    clones/        token-based Type 1/2 clone detection
    bom/           SBOM export + shared-dependency (stack) analysis
    contracts/     OpenAPI / gRPC / GraphQL -> duplicate service surfaces
    schema/        DB foreign-key graph + orphan tables
    semantic/      embeddings recall + the pairwise judge
  ingestion/     census + caching + GitLab connector
  exporters/     the redundancy-map report, mermaid, graph export
  remediation/   ratchets (governance), refactoring recipes (OpenRewrite), heal
  cli.py         the command surface
```

Top-level modules (`schema.py`, `store.py`, `plugins/…`, `semantic/…`) are thin
backward-compatible facades that re-export the canonical modules above.

## Data flow

```
census        scan repos -> Project manifest + primary plugin per repo   (ingestion/)
  |
extract       primary language plugin emits a FactBundle per module       (runner.py)
  |             -> IntegrationFacts, Dependencies, ApiSurface, coupling metric
api            OpenAPI/proto/GraphQL contracts -> SERVES endpoint facts    (probes/contracts)
clones        cross-module token clones -> ClonePair                       (probes/clones)
  |
graph.build   group facts by (resource_type, resource_id) -> edges ->      (core/graph)
              connected components = capability clusters, scored + played
  |
semantic      summarize -> embed -> nearest-neighbour recall (candidates)  (probes/semantic)
judge         confirm/refute each candidate; promote confirmed pairs       (probes/semantic)
  |
report        render the tiered redundancy map (GitLab Pages)              (exporters)
bom / schema  SBOMs + shared-deps; FK graph + orphan tables               (probes/bom, schema)
ratchet /     governance ratchets + OpenRewrite recipes (opt-in)          (remediation)
rewrite
```

## The normalized fact model (`core/schema.py`)

Every extracted fact carries **provenance** (file, line, snippet) and a
**confidence tier**. The controlled vocabularies the core validates against:

- **Tiers:** `HIGH` (literal/deterministic), `MED` (config-resolved / embedding
  similarity), `LOW` (LLM-asserted, unconfirmed).
- **Directions:** `PRODUCES`, `CONSUMES`, `READS`, `WRITES`, `CALLS`, `SERVES`.
- **Resource types:** `KAFKA_TOPIC`, `SQL_TABLE`, `SQL_COLUMN`, `HTTP_ENDPOINT`,
  `JMS_QUEUE`, `CACHE_KEY`.

The graph derives typed edges from co-touched resources:

| Edge | Meaning |
|------|---------|
| `DUP_PRODUCER` | two modules `PRODUCES` the same Kafka topic |
| `DUP_WRITER` | two modules `WRITES` the same table |
| `DUP_ENDPOINT` | two modules `SERVES` the same API endpoint |
| `CLONE_TYPE_1/2` | token-level code clone |
| `SHARES_RESOURCE` | any other shared resource (read/write, client/server) |

Each cluster is scored `opportunity = overlap · (1 − coupling)` and tagged with a
**play**: `RETIRE`, `EXTRACT`, `STANDARDIZE`, or `LEAVE`.

## Confidence tiers serve three audiences

One pipeline, three altitudes, keyed by tier — this is why the report has a tier
filter: **Exec** (HIGH only), **Prioritization** (+MED), **Exploratory** (all).
A guessed capability match is never shown with the authority of a proven token
clone or a literal topic.
