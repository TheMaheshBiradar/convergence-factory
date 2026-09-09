"""M1.6 — the redundancy map.

Renders a self-contained static site (what would be published to GitLab Pages).
Production swaps the front-end for the TypeScript app in report/; this generator
proves the output and is what the pipeline emits today. Every row is confidence-
tiered, and the tier filter is the same pipeline serving three audiences:
exec (HIGH only), prioritization (+MED), exploratory (all).
"""
from __future__ import annotations

import html
import os
from typing import List

from .store import Store

_TIER_LABEL = {"HIGH": "high", "MED": "med", "LOW": "low"}


def _esc(s) -> str:
    return html.escape(str(s))


def render(store: Store, graph: dict, candidates: List[dict], out_dir: str) -> dict:
    counts = store.counts()
    total_refs = counts["integration_facts"] + counts["gaps"]
    resolution = (counts["integration_facts"] / total_refs * 100) if total_refs else 100.0
    clusters = graph["clusters"]
    module_name = {m.id: m.name for m in store.modules()}
    module_lang = {m.id: m.lang for m in store.modules()}

    def member_html(mids):
        return " ".join(
            f'<span class="mem">{_esc(module_name.get(m, m))}'
            f'<i>{_esc(module_lang.get(m, "?"))}</i></span>' for m in mids)

    rows = []
    for i, c in enumerate(clusters, 1):
        shared = ", ".join(f"{_esc(rid)}" for _rt, rid in c["shared"])
        mix = " ".join(f'<span class="tier t-{_TIER_LABEL[t]}">{t}</span>' for t in c["tier_mix"])
        coupling_disp = "&mdash;" if c["coupling"] is None else f"{c['coupling']}"
        rows.append(f"""
      <tr data-tier="{_TIER_LABEL[c['tier']]}">
        <td class="rank">{i}</td>
        <td><b>{_esc(c['label'])}</b><div class="shared">{shared}</div></td>
        <td>{member_html(c['members'])}</td>
        <td>{_esc(len(c['owners']))} team{'s' if len(c['owners'])!=1 else ''}<div class="shared">{_esc(', '.join(c['owners']))}</div></td>
        <td><span class="play p-{c['play'].lower()}">{c['play']}</span></td>
        <td>{mix}</td>
        <td class="num">{coupling_disp}</td>
        <td class="num">{c['opportunity']}</td>
      </tr>""")

    cand_rows = []
    for c in candidates:
        cand_rows.append(f"""
      <tr>
        <td>{_esc(module_name.get(c['a'], c['a']))} &harr; {_esc(module_name.get(c['b'], c['b']))}</td>
        <td class="num">{c['similarity']}</td>
        <td><span class="tier t-{_TIER_LABEL[c['tier']]}">{c['tier']}</span></td>
      </tr>""")

    doc = _TEMPLATE.format(
        projects=counts["projects"], modules=counts["modules"],
        facts=counts["integration_facts"], gaps=counts["gaps"],
        resolution=f"{resolution:.0f}", clusters=len(clusters),
        cluster_rows="".join(rows) or '<tr><td colspan="8">No duplicate clusters found.</td></tr>',
        cand_rows="".join(cand_rows) or '<tr><td colspan="3">No candidates above threshold.</td></tr>',
    )
    site = os.path.join(out_dir, "site")
    os.makedirs(site, exist_ok=True)
    path = os.path.join(site, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return {"resolution_rate": round(resolution, 1), "clusters": len(clusters),
            "candidates": len(candidates), "site": path, **counts}


_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Redundancy Map</title>
<style>
  :root{{--bg:#F3F5F8;--surface:#fff;--surface2:#EAEEF3;--ink:#15202C;--muted:#5C6A78;
    --line:#D3DBE3;--accent:#B5561C;--high:#1F4E6B;--med:#4E7E9C;--low:#93A9B8;
    --mono:'IBM Plex Mono',ui-monospace,monospace;--sans:'IBM Plex Sans',system-ui,sans-serif;}}
  @media(prefers-color-scheme:dark){{:root{{--bg:#0F141A;--surface:#161D26;--surface2:#1C2530;
    --ink:#E7ECF1;--muted:#93A2B0;--line:#2A3540;--accent:#E08A44;--high:#7FB6D8;--med:#5687A6;--low:#54697A;}}}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.6;
    padding:clamp(1rem,4vw,3rem)}}
  .wrap{{max-width:1080px;margin:0 auto}}
  h1{{font-size:clamp(1.7rem,4vw,2.4rem);margin:0 0 .2rem;letter-spacing:-.02em}}
  h1 span{{color:var(--accent)}}
  .sub{{color:var(--muted);margin:0 0 1.8rem;font-size:.95rem}}
  .metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--line);
    border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:2rem}}
  .metrics div{{background:var(--surface);padding:1rem}}
  .metrics .v{{font-size:1.7rem;font-weight:700;font-variant-numeric:tabular-nums}}
  .metrics .k{{font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}}
  @media(max-width:720px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}
  h2{{font-size:1.15rem;margin:2.2rem 0 .3rem}}
  .filters{{display:flex;gap:.5rem;margin:.8rem 0}}
  .filters button{{font-family:var(--mono);font-size:.72rem;padding:.35rem .8rem;border-radius:20px;
    border:1px solid var(--line);background:var(--surface);color:var(--muted);cursor:pointer}}
  .filters button.on{{background:var(--accent);color:#fff;border-color:var(--accent)}}
  table{{width:100%;border-collapse:collapse;font-size:.88rem;background:var(--surface);
    border:1px solid var(--line);border-radius:10px;overflow:hidden}}
  th,td{{text-align:left;padding:.65rem .8rem;border-bottom:1px solid var(--line);vertical-align:top}}
  th{{font-family:var(--mono);font-size:.62rem;letter-spacing:.08em;text-transform:uppercase;
    color:var(--muted);background:var(--surface2)}}
  .rank{{font-family:var(--mono);color:var(--muted)}}
  .num{{font-variant-numeric:tabular-nums;text-align:right;font-family:var(--mono)}}
  .shared{{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-top:.2rem}}
  .mem{{display:inline-block;background:var(--surface2);border:1px solid var(--line);border-radius:6px;
    padding:.1rem .45rem;margin:.1rem .2rem .1rem 0;font-size:.8rem}}
  .mem i{{font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-left:.35rem;font-style:normal}}
  .tier{{font-family:var(--mono);font-size:.62rem;font-weight:600;padding:.08rem .4rem;border-radius:4px;color:#fff}}
  .t-high{{background:var(--high)}}.t-med{{background:var(--med)}}.t-low{{background:var(--low);color:var(--ink)}}
  .play{{font-family:var(--mono);font-size:.66rem;font-weight:600;padding:.15rem .5rem;border-radius:5px;
    border:1px solid var(--line);background:var(--surface2)}}
  .p-retire{{color:#fff;background:var(--accent);border-color:var(--accent)}}
  .p-standardize{{color:var(--accent)}}
  footer{{margin-top:2.5rem;color:var(--muted);font-family:var(--mono);font-size:.72rem}}
</style></head><body><div class="wrap">
  <h1>Redundancy <span>Map</span></h1>
  <p class="sub">Convergence Factory · Phase 1 output. Every signal is confidence-tiered — filter to the audience.</p>
  <div class="metrics">
    <div><div class="v">{projects}</div><div class="k">Projects</div></div>
    <div><div class="v">{modules}</div><div class="k">Modules</div></div>
    <div><div class="v">{facts}</div><div class="k">Integration facts</div></div>
    <div><div class="v">{clusters}</div><div class="k">Duplicate clusters</div></div>
    <div><div class="v">{resolution}%</div><div class="k">Resolution rate</div></div>
  </div>

  <h2>Convergence opportunities</h2>
  <div class="filters">
    <button data-f="high" class="on">Exec · HIGH</button>
    <button data-f="med">Prioritization · +MED</button>
    <button data-f="all">Exploratory · all</button>
  </div>
  <table id="clusters"><thead><tr><th>#</th><th>Capability</th><th>Members</th><th>Ownership</th><th>Play</th><th>Confidence</th><th>Coupling</th><th>Opportunity</th></tr></thead>
  <tbody>{cluster_rows}</tbody></table>

  <h2>Semantic candidates <span style="font-weight:400;color:var(--muted);font-size:.8rem">— recall only, unconfirmed</span></h2>
  <table><thead><tr><th>Module pair</th><th>Similarity</th><th>Tier</th></tr></thead>
  <tbody>{cand_rows}</tbody></table>

  <p style="color:var(--muted);font-size:.8rem;margin-top:1.2rem">Unresolved references (config/dynamic): <b>{gaps}</b> — tracked gaps, not silent misses.</p>
  <footer>Generated by the Convergence Factory · deterministic probes + semantic recall</footer>
</div>
<script>
  var order={{all:['high','med','low'],med:['high','med'],high:['high']}};
  function apply(f){{
    var allow=order[f];
    document.querySelectorAll('#clusters tbody tr').forEach(function(tr){{
      tr.style.display = allow.indexOf(tr.dataset.tier)>=0 ? '' : 'none';
    }});
    document.querySelectorAll('.filters button').forEach(function(b){{
      b.classList.toggle('on', b.dataset.f===f);
    }});
  }}
  document.querySelectorAll('.filters button').forEach(function(b){{
    b.addEventListener('click', function(){{apply(b.dataset.f);}});
  }});
  apply('high');
</script>
</body></html>"""
