# Handover & delivery guide

For a delivery-partner engineering team receiving the Convergence Factory. Read
this first; it gets you from zero to a report on your own repositories, and
points to everything else.

## 1. What it is

A layered evidence pipeline that takes a portfolio of heterogeneous repositories
and produces a ranked map of **duplicate functionality**, the **tech standard**,
and a **convergence plan** (what to unify into). It answers *"which projects do
the same thing, and what should we consolidate them into?"* across languages —
including at the wiring level (same Kafka topic, same SQL table, same endpoint),
not just copied code.

## 2. What you receive

```
src/convergence_factory/   the product (core + probes + exporters + remediation)
fixtures/                  sample repos + expected facts (calibration set)
tests/                     100+ tests (unit + integration)
docs/                      architecture, probes, extending, enterprise, this guide
Dockerfile, Makefile       reproducible build & common tasks
constraints.txt            pinned probe backends (identical stack for everyone)
.github/workflows/ci.yml   CI: tests + eval + pipeline smoke
LICENSE, SECURITY.md, CONTRIBUTING.md, CODEOWNERS, CHANGELOG.md
```

## 3. Quickstart (5 minutes)

**Option A — Make (local Python 3.10+):**
```bash
make install        # package + pinned probe backends
make test           # confirm the suite is green in your environment
make matrix ROOT=fixtures/repos OUT=.factory
open .factory/site/dashboard.html
```

**Option B — Docker (no local Python):**
```bash
make docker-build
docker run --rm -v "$PWD/repos:/repos:ro" -v "$PWD/out:/out" \
  convergence-factory:latest /repos --out /out
open out/site/dashboard.html
```

**Option C — pip:**
```bash
pip install -r constraints.txt && pip install .
python -m convergence_factory.pipeline /path/to/repos --out .factory
```

## 4. Run it on your repositories

The factory scans a directory whose entries are repos (it splits monorepos by
package and never treats `examples/`/`docs/` as projects):

```bash
make matrix ROOT=/path/to/cloned/repos OUT=.portfolio
```

To ingest a whole GitLab group, export an inventory JSON and pass it:

```bash
python -m convergence_factory run /path/to/clones --inventory gitlab_inventory.json --out .portfolio
```

Clone with **read-only, scoped tokens** (see [SECURITY.md](../SECURITY.md)).

## 5. What it produces (`<out>/site/`)

| File | What it is |
|------|-----------|
| `dashboard.html` | **Start here** — KPIs, filters (dimension/play/tier/team), drill-down |
| `matrix.html` | dense modules × capabilities grid + convergence plan |
| `convergence.json` | per-duplicate canonical target + what converges into it |
| `tech.json` | golden stack: standard library per category + outliers |
| `capability-graph.json` | bipartite module↔capability graph (Cytoscape/Gephi) |
| `sbom/*.cdx.json` | CycloneDX SBOM per project |

`make run` instead produces the legacy redundancy-map (`index.html`) and can also
generate CI **ratchets** and **OpenRewrite recipes** (`--ratchet --rewrite`).

## 6. Configuration

The deterministic pipeline needs no configuration. The optional semantic layer
uses a **self-hosted** model via environment variables:

| Env var | Purpose |
|---------|---------|
| `CONVERGENCE_LLM_ENDPOINT` | LLM endpoint for the pairwise judge |
| `CONVERGENCE_LLM_MODEL` | model name |
| `CONVERGENCE_LLM_KEY` | auth token (if any) |

Without them, the factory uses the conservative heuristic judge (deterministic,
offline). Tune blob-guard size and matrix width via `PipelineConfig`.

## 7. Extend it

Add a language (Go, C#, …) by dropping a plugin in `probes/integration/` — the
core never changes. Full guide: [extending.md](extending.md). SOLID seams and
the stage contract: [architecture.md](architecture.md), [enterprise.md](enterprise.md).

## 8. Quality & support

- **CI** runs the suite + eval + a pipeline smoke on every PR; keep it green.
- **Calibration**: `make eval` reports precision/recall/resolution against the
  fixtures — the bar you trust the numbers against.
- **Known limitations** are documented honestly in
  [maintainability.md](maintainability.md) (three orchestrators; heuristic judge
  needs the LLM for functional matching at scale; scale ceilings ~1–2k modules).

## 9. Handover checklist

- [ ] `make install && make test` green in your environment
- [ ] `make docker-build` succeeds; container runs on a sample repo dir
- [ ] Ran `make matrix` on one of your own repos and opened the dashboard
- [ ] Confirmed the LICENSE holder/terms with your legal counsel
- [ ] Set `CODEOWNERS` to your team; wired CI into your fork
- [ ] Reviewed SECURITY.md (read-only tokens, self-hosted LLM, secret scanning)
- [ ] Read maintainability.md so the known limitations are understood
