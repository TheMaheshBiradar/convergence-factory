# Maintainability, readability & scalability — an honest read

Written as due-diligence would see it. Verdict first, evidence under it.

## Verdict

| Dimension | Grade | One-line |
|---|---|---|
| Readable | **B+** | The new analytical spine is clean, typed and documented; three files >500 LOC are the weak spots. |
| Maintainable | **B−** | Strong extension model (schema contract + probe registries), but real structural redundancy that must be consolidated before sale. |
| Scalable | **B** | Architecture scales; proven fast to a few hundred repos; two O(n²) hotspots + SQLite are the 10k ceiling, with standard, well-understood fixes. |

**Sellable?** Yes — *with this debt register attached.* The bones are sound (SOLID
seams, layered `core` with no upward deps, a green 93-test suite + CI, graceful
degradation). The debt is bounded and understood, which is what a technical buyer
wants to see far more than a claim of perfection.

## Evidence

- **Size**: ~6,900 LOC in `src`. Biggest files: `exporters/report.py` (669 — mixes
  Python + inline HTML/JS), `probes/semantic/judge.py` (666), `cli.py` (507),
  `probes/integration/lang_java.py` (404). The new spine is small and focused:
  `core/capability.py` 219, `pipeline.py` 206, `exporters/matrix.py` 141.
- **Lint**: `pyflakes` reports 96 findings, but the owned spine modules are
  **clean**; the rest are facade `import *` re-exports (expected) and the big
  concurrently-edited files.
- **Tests**: 93 passing, isolated (in-memory store, `tmp_path`), scoped by
  `pytest.ini`. CI runs suite + eval + pipeline smoke.

## Debt register (what a reviewer will flag)

1. **Three orchestrators** encode the run sequence separately — `cli.cmd_run`,
   `pipeline.run`, `pipelines/flow.run_pipeline`. "Which is the real entry point?"
2. ~~**`graph.json` is written in ~3 places**, and `export_graph_json` is dead.~~
   **FIXED** — `report.render` now routes through `graphify.export_graph_json`
   (the inline duplicate is gone, the dead import is live); `graph.json` output
   unchanged, 93 tests still green. The new bipartite `capability-graph.json`
   remains a separate, intentional artifact — both live in `graphify`.
3. **Two graph models coexist** — the old union-into-components `core/graph` and
   the new capability spine. The old one should become a derived affinity view or go.
4. **`report.py` mixes concerns** — Python, an HTML template, and JS in one 669-LOC file.

None of these are correctness bugs; all are consolidation refactors doable behind
the existing test suite.

## Remediation plan (prioritized, non-breaking)

- **P1 — one orchestrator.** `cli` and `flow` delegate to `pipeline.run(PipelineConfig)`; delete the bespoke sequences. (Tests + eval guard it.)
- **P1 — one graph writer. ✅ DONE** — report now calls `graphify.export_graph_json`; inline duplicate removed, dead import resolved.
- **P2 — retire the union graph** as primary; keep only as an optional affinity projection.
- **P2 — split `report.py`** into template + graph-shaping + renderer modules.
- **P3 — scale to 10k** (the ceilings, with fixes):
  - semantic recall is O(n²) pairwise → **ANN / vector index** (FAISS/hnswlib).
  - clone probe compares all module pairs holding full token sets → **MinHash + LSH**.
  - SQLite fact store → **DuckDB/Parquet** for columnar scans.
  - census is serial → **parallel** extraction (the runner is already per-repo).
- **P3 — lint gate** in CI (`pyflakes`/`ruff`); give facades explicit `__all__`.

## Scale evidence & ceiling

Validated on a **140-repo** synthetic portfolio: full run ~2s, 69 clean
per-dimension capabilities. The deterministic path (extract → capability grouping)
is effectively linear in facts. The O(n²) recall/clone steps are comfortable to
the low hundreds; past ~1–2k modules they need the P3 upgrades above. This is a
known ceiling with off-the-shelf fixes, not an architectural dead end.
