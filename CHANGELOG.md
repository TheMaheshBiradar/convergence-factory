# Changelog

All notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.4.0] — 2026-09-13 — Handover release

### Added
- **Capability spine** (`core/capability.py`): per-dimension capabilities replace
  the union-into-blob graph; blob guard on the fuzzy/semantic dimension.
- **Convergence plan** (`core/convergence.py`): per duplicate, the canonical
  target (or new shared component) + what converges into it + rollup.
- **Tech-standard probe** (`core/tech.py`): golden-stack / library fragmentation.
- **Portfolio dashboard** (`exporters/dashboard.py`): stats-first, filterable,
  drill-down single-page report for 200+ projects.
- **Six-stage pipeline** (`pipeline.py`) driven by a typed `PipelineConfig`
  (DIP: injectable store/judge/embedder); unified `matrix` CLI command.
- BOM, API/contract, DB-schema (FK + orphans), column-level SQL lineage probes;
  bipartite capability graph export.
- Handover kit: Dockerfile, Makefile, pinned `constraints.txt`, LICENSE,
  CONTRIBUTING, SECURITY, docs/HANDOVER.md, CI.

### Fixed
- Census now handles real-world repo layouts (examples/docs no longer become
  projects; Node repos no longer dropped; monorepos split by package).
- `lang-node` path exclusion is repo-relative (fixed a Linux-only `/tmp` bug).
- Heuristic judge is conservative (no lexical-overlap false confirmations).

### Known limitations
See `docs/maintainability.md`: three orchestrators still coexist; heuristic judge
needs the LLM for trustworthy functional matching; scale ceilings (~1–2k modules)
need ANN recall / MinHash clones / DuckDB store.
