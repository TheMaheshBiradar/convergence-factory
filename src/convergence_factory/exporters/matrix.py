"""Stage 5 (primary view) — the capability matrix.

Renders modules x capabilities as a per-dimension grid: reading down a column is
a duplication finding. Only capabilities >=2 modules share are columns, and only
participating modules are rows, so the view stays compact even across a large
portfolio — the fix for the "one huge blob" report.
"""
from __future__ import annotations

import html
import json
import os
from collections import defaultdict
from typing import List

from ..core.capability import Capability

_TIER_CLASS = {"HIGH": "t-high", "MED": "t-med", "LOW": "t-low"}
_DIR_ABBR = {"PRODUCES": "P", "CONSUMES": "C", "READS": "R", "WRITES": "W",
             "CALLS": "→", "SERVES": "S", "SHARES": "~", "USES": "u"}
_DIM_ORDER = ["messaging", "data", "column", "api", "code", "functional",
              "dependency", "cache", "other"]


def _esc(s) -> str:
    return html.escape(str(s))


def _convergence_section(conv) -> str:
    if not conv:
        return ""
    rows = []
    for p in conv.get("capability_plans", [])[:40]:
        frm = ", ".join(_esc(s.split(":")[0]) for s in p["migrate_from"]) or "&mdash;"
        rows.append(
            f'<tr><td><span class="play p-{p["play"].lower()}">{p["play"]}</span></td>'
            f'<td>{_esc(p["dimension"])}</td>'
            f'<td><b>{_esc(p["label"])}</b><div class="tgt">{_esc(p["target"])}</div></td>'
            f'<td class="canon">{_esc(p["canonical"].split(":")[0])}</td>'
            f'<td class="from">{frm}</td></tr>')
    for tp in conv.get("tech_plans", [])[:20]:
        frm = ", ".join(_esc(x) for x in tp["migrate_from_libs"]) or "&mdash;"
        rows.append(
            '<tr><td><span class="play p-standardize">STD</span></td><td>tech</td>'
            f'<td><b>{_esc(tp["category"])}</b><div class="tgt">{_esc(tp["target"])}</div></td>'
            f'<td class="canon">{_esc(tp["canonical"])}</td><td class="from">{frm}</td></tr>')
    if not rows:
        return ""
    r = conv.get("rollup", {})
    roll = (f'{r.get("duplicate_capabilities", 0)} duplicate capabilities &rarr; '
            f'{r.get("canonical_targets", 0)} canonical targets + '
            f'{r.get("new_shared_components", 0)} new shared components &middot; '
            f'{r.get("modules_to_migrate", 0)} modules to migrate &middot; '
            f'{r.get("tech_standardizations", 0)} tech standardizations')
    return ('<section class="conv"><h2>Convergence plan '
            '<span class="count">unify into this</span></h2>'
            f'<p class="roll">{roll}</p>'
            '<div class="scroll"><table><thead><tr><th>Play</th><th>Dim</th>'
            '<th>Capability &rarr; unified target</th><th>Canonical</th>'
            '<th>Converge from</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


def render(caps: List[Capability], out_dir: str, max_cols: int = 40,
           convergence=None) -> dict:
    site = os.path.join(out_dir, "site")
    os.makedirs(site, exist_ok=True)

    by_dim = defaultdict(list)
    for c in caps:
        by_dim[c.dimension].append(c)

    sections = []
    for dim in _DIM_ORDER:
        cols = sorted(by_dim.get(dim, []), key=lambda c: -c.opportunity)
        if not cols:
            continue
        shown = cols[:max_cols]
        truncated = len(cols) - len(shown)
        # rows = modules participating in this dimension's shown capabilities
        cell = defaultdict(dict)          # module -> cap.id -> (dir, tier)
        for c in shown:
            for m in c.members:
                cell[m["module"]][c.id] = (m["direction"], m["tier"])
        modules = sorted(cell)

        head = "".join(
            f'<th class="cap"><span class="play p-{c.play.lower()}">{c.play[:4]}</span>'
            f'<div class="clab">{_esc(c.label)}</div>'
            f'<div class="cmeta">opp {c.opportunity} · {len(c.module_ids)} mods</div></th>'
            for c in shown)
        rows = []
        for m in modules:
            cells = []
            for c in shown:
                v = cell[m].get(c.id)
                if v:
                    d, t = v
                    cells.append(f'<td class="{_TIER_CLASS.get(t,"")}" title="{_esc(d)} · {t}">'
                                 f'{_DIR_ABBR.get(d, d[:1])}</td>')
                else:
                    cells.append('<td class="empty"></td>')
            rows.append(f'<tr><th class="mod">{_esc(m.split(":")[0])}</th>{"".join(cells)}</tr>')

        note = f'<p class="trunc">+ {truncated} more {dim} capabilities not shown</p>' if truncated else ""
        sections.append(
            f'<section><h2>{_esc(dim)} <span class="count">{len(cols)}</span></h2>'
            f'<div class="scroll"><table><thead><tr><th class="mod">module</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>{note}</section>')

    dims_present = [d for d in _DIM_ORDER if by_dim.get(d)]
    total_caps = len(caps)
    total_dupe_modules = len({m for c in caps for m in c.module_ids})
    body = _convergence_section(convergence) + \
        ("".join(sections) or "<p>No shared capabilities found.</p>")
    doc = _TEMPLATE.format(
        sections=body, total_caps=total_caps, dims=len(dims_present),
        dupe_modules=total_dupe_modules)
    path = os.path.join(site, "matrix.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)

    # machine-readable
    jpath = os.path.join(site, "matrix.json")
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump({"capabilities": [c.as_dict() for c in caps]}, fh, indent=2)

    return {"matrix_html": path, "matrix_json": jpath,
            "capabilities": total_caps, "dimensions": len(dims_present)}


_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capability Matrix</title>
<style>
  :root{{--bg:#F3F5F8;--surface:#fff;--surface2:#EAEEF3;--ink:#15202C;--muted:#5C6A78;
    --line:#D3DBE3;--accent:#B5561C;--high:#1F4E6B;--med:#4E7E9C;--low:#93A9B8;
    --mono:'IBM Plex Mono',ui-monospace,monospace;--sans:'IBM Plex Sans',system-ui,sans-serif;}}
  @media(prefers-color-scheme:dark){{:root{{--bg:#0F141A;--surface:#161D26;--surface2:#1C2530;
    --ink:#E7ECF1;--muted:#93A2B0;--line:#2A3540;--accent:#E08A44;--high:#7FB6D8;--med:#5687A6;--low:#54697A;}}}}
  *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);
    font-family:var(--sans);padding:clamp(1rem,3vw,2.4rem);line-height:1.5}}
  h1{{font-size:1.9rem;margin:0 0 .1rem;letter-spacing:-.02em}} h1 span{{color:var(--accent)}}
  .sub{{color:var(--muted);margin:0 0 1.6rem;font-size:.9rem}}
  .metrics{{display:flex;gap:1px;background:var(--line);border:1px solid var(--line);
    border-radius:10px;overflow:hidden;margin-bottom:2rem;max-width:560px}}
  .metrics div{{background:var(--surface);padding:.8rem 1.1rem;flex:1}}
  .metrics .v{{font-size:1.5rem;font-weight:700;font-variant-numeric:tabular-nums}}
  .metrics .k{{font-family:var(--mono);font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}}
  section{{margin:0 0 2.2rem}} h2{{font-size:1.05rem;margin:0 0 .6rem;text-transform:capitalize}}
  h2 .count{{font-family:var(--mono);font-size:.7rem;color:var(--muted);border:1px solid var(--line);
    border-radius:20px;padding:.05rem .5rem;margin-left:.4rem}}
  .scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:10px}}
  table{{border-collapse:collapse;font-size:.8rem}}
  th,td{{border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:.35rem .5rem;text-align:center}}
  th.mod,td.mod{{text-align:left;position:sticky;left:0;background:var(--surface);font-family:var(--mono);
    font-size:.72rem;white-space:nowrap;z-index:1}}
  thead th{{background:var(--surface2);vertical-align:bottom;max-width:150px}}
  .clab{{font-size:.72rem;font-weight:600;margin-top:.2rem;white-space:normal}}
  .cmeta{{font-family:var(--mono);font-size:.58rem;color:var(--muted);margin-top:.1rem}}
  td.empty{{background:transparent}}
  td.t-high{{background:var(--high);color:#fff;font-weight:700}}
  td.t-med{{background:var(--med);color:#fff}} td.t-low{{background:var(--low);color:var(--ink)}}
  .play{{font-family:var(--mono);font-size:.55rem;font-weight:700;padding:.05rem .3rem;border-radius:3px;
    background:var(--surface);border:1px solid var(--line);color:var(--muted)}}
  .p-retire{{color:#fff;background:var(--accent);border-color:var(--accent)}}
  .p-standardize{{color:var(--accent)}}
  .trunc{{color:var(--muted);font-size:.75rem;font-family:var(--mono);margin:.4rem 0 0}}
  section.conv{{margin-bottom:2.4rem}}
  .conv .roll{{font-family:var(--mono);font-size:.78rem;color:var(--muted);margin:.2rem 0 .8rem}}
  .conv td{{text-align:left}} .conv .tgt{{font-size:.72rem;color:var(--muted);margin-top:.15rem}}
  .conv td.canon{{font-family:var(--mono);font-weight:700;color:var(--accent)}}
  .conv td.from{{font-family:var(--mono);font-size:.72rem;color:var(--muted)}}
</style></head><body>
  <h1>Capability <span>Matrix</span></h1>
  <p class="sub">Modules &times; shared capabilities, per dimension. A column with &ge;2 filled cells is a duplication finding. Cell = direction (P/C/R/W/S/~), colour = confidence tier.</p>
  <div class="metrics">
    <div><div class="v">{total_caps}</div><div class="k">Shared capabilities</div></div>
    <div><div class="v">{dupe_modules}</div><div class="k">Modules involved</div></div>
    <div><div class="v">{dims}</div><div class="k">Dimensions</div></div>
  </div>
  {sections}
</body></html>"""
