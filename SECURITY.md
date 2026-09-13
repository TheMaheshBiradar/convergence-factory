# Security

## Data handling — runs in your boundary

The factory is designed to keep source code inside the partner's environment:

- The analytical core and all deterministic probes run **locally** — no source
  code leaves the machine.
- The semantic layer is optional. When enabled it uses a **self-hosted** LLM/
  embedding endpoint you configure (`CONVERGENCE_LLM_ENDPOINT`); nothing is sent
  to a third party unless you point it at one.
- Outputs (matrix, dashboard, `*.json`, SBOMs) are written to a local directory
  you choose.

## Handling repositories safely

- Clone with **read-only, scoped tokens**; the factory only reads.
- Run secret-scanning on ingested repos out of band — the factory does not strip
  secrets, and its outputs (provenance snippets) may quote source lines.
- The container image runs the analysis only; mount repos read-only where
  possible (`-v "$PWD/repos:/repos:ro"`).

## Dependencies

- The core requires no third-party packages. Optional probe backends are pinned
  in `constraints.txt` for reproducibility; review and re-pin on your schedule.
- SBOMs for the *analyzed* portfolio are produced under `<out>/sbom/`.

## Reporting a vulnerability

Report suspected vulnerabilities privately to the project owner through your
delivery-agreement contact, not via public issues. Include a description, repro
steps, and impact. Please allow reasonable time to remediate before disclosure.
