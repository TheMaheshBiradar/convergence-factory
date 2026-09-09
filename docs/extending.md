# Extending the factory

The invariant: **new technology touches `probes/` and `fixtures/` only — never
`core/`.** A plugin emits normalized facts; the core consumes them without
learning the language.

## Add a language plugin

1. Create `src/convergence_factory/probes/integration/lang_<x>.py`.
2. Subclass `LanguagePlugin` and implement what you can (a partial plugin still
   contributes):

   ```python
   from .base import LanguagePlugin, register, read, walk_files
   from convergence_factory.core.schema import FactBundle, IntegrationFact, Module, Provenance

   class MyPlugin(LanguagePlugin):
       name = "lang-x"
       lang = "x"

       def detect(self, repo_path):
           files = walk_files(repo_path, (".x",))
           return {"claims": ["x"], "build": "…", "score": len(files)} if files else None

       def modules(self, repo_path, project_id):
           return [Module(id=f"{project_id}:x", project_id=project_id,
                          path=repo_path, name=project_id, kind="service", lang="x")]

       def facts(self, module, repo_path):
           bundle = FactBundle(module=module, source_ref=repo_path)
           # …parse (prefer a real AST/grammar; fall back to regex)…
           bundle.integration.append(IntegrationFact(
               module_id=module.id, direction="PRODUCES", resource_type="KAFKA_TOPIC",
               resource_id="some.topic", tier="HIGH",
               provenance=Provenance(file="app.x", line=1)))
           return bundle

   register(MyPlugin())
   ```

3. Add it to `probes/integration/__init__.py` so import registers it.
4. Add a fixture repo under `fixtures/repos/` and (optionally) an expected-facts
   file under `fixtures/expected/<repo>.json`, then run the eval.

**Rules of the road**

- Resolve topic/table/URL expressions through `core.resolver.resolve`; emit a
  `Gap` for anything you can't resolve rather than dropping it.
- Tier honestly: literal = `HIGH`, config/env-resolved = `MED`, guessed = `LOW`.
- Emit only vocabulary the schema allows (see `core/schema.py`); the runner
  validates and skips anything invalid without killing the run.

## Add a cross-cutting probe (analysis over the store)

For probes that aren't language-specific (BOM, API/contract, schema), write a
module under the relevant `probes/<kind>/` package that takes a `Store`, reads
`store.modules()` (each has `.path`), and either writes facts back via
`store.add_integration(...)` / `store.add_api(...)` or returns a report:

```python
def run_myprobe(store):
    for m in store.modules():
        # scan m.path, emit facts or collect findings
        ...
    return summary
```

Wire it into `cli.cmd_run` (and `pipelines/flow.py`) — before `graph.build` if it
emits facts that should cluster (like the API probe's `SERVES` endpoints), or
after if it only reports (like BOM and schema).

## Add a new resource or edge type

Extend the vocabularies in `core/schema.py` (`DIRECTIONS`, `RESOURCE_TYPES`), then
teach `core/graph.py::_edge_type` / `_label` / `_play` about the new duplicate
semantics. Keep it small — most probes reuse the existing types.

## Golden fixtures & eval

Every plugin should ship a sample repo whose expected integration facts are
hand-labelled in `fixtures/expected/<repo>.json`:

```json
{"repo": "my-repo",
 "integration": [["PRODUCES", "KAFKA_TOPIC", "order.created"]]}
```

`convergence-factory eval` reports precision / recall / resolution per repo. This
is where you set a plugin's "done when" bar before trusting its numbers.
