# Contributing

For partner engineers extending the factory. The golden rule is the same one the
architecture rests on:

> **New technology touches `probes/` and `fixtures/` — never `core/`.**

## Setup

```bash
make install-dev     # package + pinned probe backends + pytest/ruff
make test            # 100+ tests, must stay green
```

The analytical core is Python-standard-library only. The pinned probe backends
(`constraints.txt`) add real AST/SQL parsing; without them the probes degrade to
regex rather than break.

## Adding a language plugin

1. Add `src/convergence_factory/probes/integration/lang_<x>.py` implementing the
   `LanguagePlugin` SPI (`detect` / `modules` / `facts`) and `register(...)`.
2. Add a fixture repo under `fixtures/repos/` and, ideally, expected facts under
   `fixtures/expected/<repo>.json`.
3. `make eval` to check precision/recall; `make test`.

Full guide: [docs/extending.md](docs/extending.md). Architecture:
[docs/architecture.md](docs/architecture.md).

## Rules of the road

- Resolve topic/table/URL expressions through `core.resolver`; emit a `Gap` for
  anything unresolved rather than dropping it.
- Tier honestly: literal = `HIGH`, config/env-resolved = `MED`, guessed = `LOW`.
- Prefer a real parser (AST/grammar) with a regex fallback; never hard-fail an
  import.
- Paths: exclude **repo-relative** components, never the absolute system prefix
  (a repo under `/tmp` must not be excluded).

## Branch & PR

- Branch off `main`; keep changes focused. Conventional-commit style is used
  (`feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`).
- CI (`.github/workflows/ci.yml`) runs the suite + eval + a pipeline smoke on
  every PR; it must pass before merge.
- End commit messages with the project's attribution trailer.
