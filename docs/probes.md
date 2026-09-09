# Probe catalogue

A **probe** extracts one kind of evidence and writes normalized facts to the
store. Language plugins run per-module during extraction; cross-cutting probes
run as analyses over the store. Every probe prefers a real parser and degrades
to regex only if the parser/grammar is unavailable.

## Integration probes (language plugins)

Emit the "wiring" signal — a module's connections to shared infrastructure —
plus dependencies and an internal-coupling metric.

| Plugin | Backend | Detects |
|--------|---------|---------|
| `lang-python` | stdlib `ast` | kafka `send`/`produce`/`KafkaConsumer`, embedded SQL (tables + columns), `requests`/`httpx` calls, `requirements.txt` deps |
| `lang-java` | tree-sitter (JVM sidecar = max-fidelity upgrade) | Spring `kafkaTemplate.send`, `@KafkaListener`, `@Query`/native SQL, `RestTemplate`, `@Value` topics resolved via `application.yml`, Maven deps |
| `lang-sql` | sqlglot (regex fallback) | table read/write lineage **and column-level lineage** (`CREATE`/`INSERT` column lists); also the shared `extract_sql_lineage` / `extract_sql_columns` services other plugins call |
| `lang-node` | tree-sitter JS (regex fallback) | kafkajs `producer.send({topic})` / `consumer.subscribe`, `fetch`/`axios` calls, npm deps, relative-import coupling |

Topic/URL expressions run through the shared **resolver**, so a literal is
`HIGH` and a value sourced from config/env is `MED`. Unresolved references are
recorded as tracked **gaps**, never dropped — the report shows a resolution rate.

## Clone probe (`probes/clones`)

Type 1 (exact) and Type 2 (renamed/parameterized) cross-module clones via
tokenized, comment-stripped line hashing. Emits `ClonePair` at tier `HIGH`;
feeds `CLONE_TYPE_*` edges into the graph.

## BOM probe (`probes/bom`)

Turns dependency facts into (a) a **CycloneDX 1.5 SBOM per project** under
`.factory/sbom/`, and (b) a **shared-dependency report** — libraries used across
modules owned by ≥2 teams, the stack-standardization candidates. Syft +
license/CVE enrichment is the production upgrade; the output shape is unchanged.

## API / contract probe (`probes/contracts`)

Scans each repo for **OpenAPI** (yaml/json), **gRPC** `.proto`, and **GraphQL**
SDL. Emits `ApiSurface` (the catalogue) and `IntegrationFact(direction=SERVES,
HTTP_ENDPOINT)`. Two services exposing the same operation cluster as a
`DUP_ENDPOINT` — a duplicate service surface. Runs before graph build.

## DB-schema probe (`probes/schema`)

Static analysis of DDL: builds the table-level **foreign-key graph** (blast
radius) and flags **orphan tables** — created but neither referenced by a FK nor
shared across modules. A live-DB SchemaCrawler run is the production upgrade.

## Semantic probe + judge (`probes/semantic`)

The cross-language net for functional overlap that shares no infrastructure.

1. **Recall** — summarize each module (language-neutral), embed the *summary*
   (not raw code), and surface nearest-neighbour candidate pairs. Recall only;
   candidates are `MED`/`LOW`, never promoted on their own.
2. **Judge** — `HeuristicJudge` (default) or `RestJudge` (self-hosted/OpenAI-style
   LLM). The heuristic is **conservative by design**: it confirms only on shared
   *domain* terms (`order`, `customer`), never on generic structural vocabulary
   (`publish`, `event`, `kafka`, `table`), so it does not launder low-confidence
   recall into "confirmed." Confirmed pairs are promoted into clusters at their
   recall tier.

Point the LLM judge at your endpoint with `--llm` (env
`CONVERGENCE_LLM_ENDPOINT` / `CONVERGENCE_LLM_MODEL` / `CONVERGENCE_LLM_KEY`); it
falls back to the heuristic if the server is unreachable.
