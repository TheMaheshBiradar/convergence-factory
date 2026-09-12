# Enterprise readiness & SOLID

## SOLID mapping

| Principle | How the factory applies it |
|---|---|
| **S**ingle responsibility | Each stage/module does one thing: `core/schema` = the contract, `core/store` = persistence, `core/capability` = analysis (the spine), `core/graph` = affinity, `exporters/*` = views, `probes/*` = extraction, `remediation/*` = actions. Views render; they do not analyse. |
| **O**pen/closed | New technology = a new file, not a core edit. Language plugins self-register in `probes/integration/base.REGISTRY`; portfolio probes self-register in `probes/registry` (`FACT_PROBES` / `REPORT_PROBES`). The orchestrator iterates the registries and never names a probe. |
| **L**iskov substitution | Every `LanguagePlugin` is interchangeable through the same `detect/modules/facts` SPI; every `Judge` / `Embedder` / `Summarizer` is interchangeable through its Protocol (heuristic ↔ REST LLM with no caller change). |
| **I**nterface segregation | Small, role-specific abstractions in `core/interfaces` (`FactStore`, `PortfolioProbe`) and `probes/semantic` (`Embedder`, `Judge`, `Summarizer`). A stage depends only on the methods it uses. |
| **D**ependency inversion | `pipeline.run(config, judge=…, embedder=…, store_factory=…)` depends on abstractions, not concretions; defaults wire the concrete SQLite store and heuristic judge. `core` never imports from `probes` / `exporters` / `remediation` — dependencies point inward. |

## The six-stage pipeline (single orchestrator)

`INGEST → EXTRACT → CAPABILITIES → FINDINGS → VIEWS → REMEDIATE` (`pipeline.py`).
One `PipelineConfig` drives a run; `cli` and `pipelines/flow.py` are thin wrappers
over the same `run()`. The **capability** stage is the analytical spine — each
shared resource / clone group / semantic group is one capability keyed by a
single dimension, so the output is a scannable modules×capabilities matrix, never
a merged blob (a size guard drops over-large fuzzy components).

## Enterprise-readiness checklist

- **Tests**: `pytest` suite (93 tests) covering schema, probes, capability spine,
  matrix/graph views, judge, ratchets, rewrite, heal, and the pipeline end-to-end.
  Scoped by `pytest.ini` (`testpaths = tests`, benchmarks excluded); tests use
  in-memory stores and `tmp_path` isolation.
- **CI**: `.github/workflows/ci.yml` runs the suite + calibration eval + a pipeline
  smoke on every push/PR.
- **Configuration**: one typed `PipelineConfig` — no scattered positional args or
  ad-hoc env reads on the hot path.
- **Zero-dependency core**: runs on the standard library; optional parsers
  (sqlglot, tree-sitter, PyYAML) sharpen probes and **degrade gracefully** to
  regex when absent.
- **Auditability**: every extracted fact carries `Provenance` (file, line, snippet)
  and a confidence `tier`; the calibration eval reports precision / recall /
  resolution so numbers are defensible.
- **Scale**: validated on a 140-repo synthetic portfolio (`scripts/generate_portfolio.py`)
  — full run in ~2s, 69 clean per-dimension capabilities.

## Known limitations (honest)

- The **heuristic judge over-confirms at scale** (lexical overlap); trustworthy
  functional matching needs the `RestJudge` LLM. The blob guard keeps the matrix
  honest in the meantime, and the deterministic dimensions carry the result.
- The **Java backend** is tree-sitter (single-file, no type resolution); full
  fidelity is the JVM JavaParser/Spoon sidecar.
