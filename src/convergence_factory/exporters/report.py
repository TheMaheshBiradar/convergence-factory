"""M1.6 — the redundancy map.

Renders a self-contained interactive static site (what would be published to GitLab Pages).
Includes interactive capability filtering, search, and Mermaid.js wiring topology.
Every row is confidence-tiered, serving three audiences:
exec (HIGH only), prioritization (+MED), exploratory (all).
"""
from __future__ import annotations

import html
import os
from typing import List

from convergence_factory.core.store import Store
import html
import os
import shutil
from typing import Dict, List, Tuple

from convergence_factory.core.errors import ERROR_TRACKER
from convergence_factory.core.store import Store
from .graphify import export_graph_json
from .mermaid import generate_mermaid_diagram

_TIER_LABEL = {"HIGH": "high", "MED": "med", "LOW": "low"}


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _cluster_next_steps(c: dict) -> dict:
    play = c.get("play", "LEAVE")
    members = c.get("members", [])
    owners = c.get("owners", [])

    if play == "RETIRE":
        canonical = members[0] if members else "canonical-service"
        deprecated = members[1:] if len(members) > 1 else members
        dep_names = ", ".join(m.split(":")[0] for m in deprecated)
        return {
            "badge": "❌ Deprecate &amp; Cutover",
            "action_class": "act-retire",
            "summary": f"Deprecate duplicate service(s) ({_esc(dep_names)}) and converge traffic to {_esc(canonical.split(':')[0])}.",
            "rationale": f"Single team ({', '.join(owners)}) owns duplicate implementations. Low friction to retire legacy paths.",
            "step_1": f"Designate <code>{_esc(canonical)}</code> as canonical service; freeze feature additions on <code>{_esc(dep_names)}</code>.",
            "step_2": f"Reroute inbound API/consumer traffic to <code>{_esc(canonical)}</code>.",
            "step_3": "Run generated ArchUnit barrier or import linter in <code>ratchets/</code> to prevent regressions."
        }
    elif play == "STANDARDIZE":
        return {
            "badge": "⚡ Extract &amp; Standardize",
            "action_class": "act-standardize",
            "summary": f"Cross-team duplicate across {len(owners)} teams. Converge on shared library or unified service.",
            "rationale": f"Multiple independent teams ({', '.join(owners)}) re-implemented identical capability. High ROI for harmonization.",
            "step_1": f"Form architecture contract between teams ({', '.join(owners)}).",
            "step_2": "Apply automated OpenRewrite declarative recipe in <code>recipes/rewrite.yml</code>.",
            "step_3": "Lock one-way CI/CD governance ratchet in <code>ratchets/</code> to enforce standard implementation."
        }
    elif play == "EXTRACT":
        return {
            "badge": "📦 Extract Shared SDK/API",
            "action_class": "act-extract",
            "summary": "Shared resource coupling detected. Extract shared access layer into dedicated SDK or microservice.",
            "rationale": "Modules share database tables or queues. Extracting an access layer decouples database internals.",
            "step_1": "Isolate database tables or queues into a dedicated bounded service.",
            "step_2": "Publish versioned client library (SDK) with backward-compatible contracts.",
            "step_3": "Replace direct database/queue coupling with REST or gRPC client calls."
        }
    else:  # LEAVE
        return {
            "badge": "✓ Accept Divergence",
            "action_class": "act-leave",
            "summary": "Intentional or low-friction divergence. Keep modules separate under existing ownership.",
            "rationale": "High coupling friction or distinct bounded contexts make convergence cost exceed consolidation value.",
            "step_1": "Document architectural decision record (ADR) noting distinct bounded contexts.",
            "step_2": "Maintain independent release pipelines without cross-team locking.",
            "step_3": "Monitor coupling metrics during quarterly portfolio reviews."
        }


def _cluster_why_matched(c: dict) -> Tuple[str, str, List[str]]:
    """Returns (inline_html_badges, tooltip_detailed_text, details_list_items)."""
    shared = c.get("shared", [])
    badges = []
    details = []

    for rtype, rid in shared:
        if rtype == "KAFKA_TOPIC":
            badges.append(f'<span class="ev-badge ev-kafka" title="Kafka Topic">⚡ {_esc(rid)}</span>')
            details.append(f'<li><b style="color:#1b588c;">⚡ Kafka Topic:</b> <code>{_esc(rid)}</code></li>')
        elif rtype == "SQL_TABLE":
            badges.append(f'<span class="ev-badge ev-sql" title="SQL Table">🗄️ {_esc(rid)}</span>')
            details.append(f'<li><b style="color:#a44c13;">🗄️ SQL Table:</b> <code>{_esc(rid)}</code></li>')
        elif rtype == "HTTP_ENDPOINT":
            badges.append(f'<span class="ev-badge ev-http" title="REST Endpoint">🌐 {_esc(rid)}</span>')
            details.append(f'<li><b style="color:#1f6b38;">🌐 HTTP Endpoint:</b> <code>{_esc(rid)}</code></li>')
        elif rtype == "CODE_CLONE":
            badges.append(f'<span class="ev-badge ev-clone" title="Code Clone">🧬 {_esc(rid)}</span>')
            details.append(f'<li><b style="color:#6d2c8e;">🧬 Code Clone:</b> <code>{_esc(rid)}</code></li>')
        else:
            badges.append(f'<span class="ev-badge ev-other">{_esc(rtype)}: {_esc(rid)}</span>')
            details.append(f'<li><b>{_esc(rtype)}:</b> <code>{_esc(rid)}</code></li>')

    if not badges:
        badges.append(f'<span class="ev-badge ev-semantic">🎯 {_esc(c.get("label", "Semantic match"))}</span>')
        details.append(f'<li><b style="color:#2b4e68;">🎯 Semantic Intent Match:</b> {_esc(c.get("label", ""))}</li>')

    if len(badges) > 2:
        shown_badges = "".join(badges[:2]) + f'<span class="ev-badge ev-more">+{len(badges)-2} more</span>'
    else:
        shown_badges = "".join(badges)

    raw_items = [f"• {rtype}: {rid}" for rtype, rid in shared] if shared else [f"• Semantic: {c.get('label', '')}"]
    tooltip_text = _esc("<b style='color:#15202C;'>Why Matched (Evidence):</b><br>" + "<br>".join(raw_items))
    return shown_badges, tooltip_text, details


def member_html(mids, module_name, module_lang, module_path, summaries) -> Tuple[str, str, List[str]]:
    pills = []
    details = []
    summary_items = []

    for m in mids:
        name = module_name.get(m, m)
        lang = module_lang.get(m, "?")
        path = module_path.get(m, "")
        summary = summaries.get(m, "")
        pills.append(f'<span class="mem">{_esc(name)}<i>{_esc(lang)}</i></span>')
        details.append(f"• <b>{_esc(name)}</b> [{_esc(lang)}] — <code>{_esc(path or m)}</code>")
        summary_items.append(f'<li><b>{_esc(name)}</b>: {_esc(summary or "No capability summary available")}</li>')

    if len(pills) > 2:
        inline = "".join(pills[:2]) + f'<span class="mem mem-more">+{len(pills)-2} more</span>'
    else:
        inline = "".join(pills)

    tip = _esc(f"<b>Participating Modules ({len(mids)}):</b><br>" + "<br>".join(details))
    return inline, tip, summary_items


def render(store: Store, graph: dict, candidates: List[dict], out_dir: str) -> dict:
    counts = store.counts()
    total_refs = counts["integration_facts"] + counts["gaps"]
    resolution = (counts["integration_facts"] / total_refs * 100) if total_refs else 100.0
    clusters = graph["clusters"]
    module_name = {m.id: m.name for m in store.modules()}
    module_lang = {m.id: m.lang for m in store.modules()}
    module_path = {m.id: m.path for m in store.modules()}
    summaries = {row["module_id"]: row["summary"] for row in store.db.execute("SELECT module_id, summary FROM capability_summaries")}

    site = os.path.join(out_dir, "site")
    os.makedirs(site, exist_ok=True)

    # Copy / generate error.txt in site directory as well
    error_log_source = os.path.join(out_dir, "error.txt")
    site_error_log = os.path.join(site, "error.txt")
    if os.path.exists(error_log_source):
        shutil.copy2(error_log_source, site_error_log)
    else:
        ERROR_TRACKER.write_to_file(site_error_log)

    errors_count = ERROR_TRACKER.count()
    has_errors = ERROR_TRACKER.has_errors()
    diag_class = "diag-warn" if has_errors else ("diag-info" if errors_count > 0 else "diag-ok")
    err_badge_class = "metric-err" if has_errors else ("metric-warn" if errors_count > 0 else "metric-ok")
    diag_msg = (
        f"⚠️ {errors_count} framework issues recorded across pipeline stages."
        if errors_count > 0
        else "✅ Clean run — zero framework errors recorded across all probes."
    )

    rows = []
    for i, c in enumerate(clusters, 1):
        mem_inline, mem_tip, member_summaries_list = member_html(c["members"], module_name, module_lang, module_path, summaries)
        why_inline, why_tip, why_details_list = _cluster_why_matched(c)
        next_info = _cluster_next_steps(c)

        coupling = c.get("coupling")
        coupling_disp = "—" if coupling is None else f"{coupling:.2f}"
        play_class = c['play'].lower()

        cap_tip = _esc(f"<b>Cluster {i}: {_esc(c['label'])}</b><br>Play: {c['play']}<br>Opportunity: {c['opportunity']}")
        how_tip = _esc(
            f"<b>How Decided (Decision Engine):</b><br>"
            f"• Overlap Score: {c.get('score', 0)}<br>"
            f"• Coupling Friction: {coupling_disp}<br>"
            f"• Opportunity Formula: Overlap × (1 - Coupling) = {c.get('opportunity', 0)}<br>"
            f"• Confidence Tier: {c.get('tier', 'MED')} (mix: {', '.join(c.get('tier_mix', []))})"
        )
        next_tip = _esc(
            f"<b>Actionable Playbook ({c['play']}):</b><br>"
            f"• Step 1: {next_info['step_1']}<br>"
            f"• Step 2: {next_info['step_2']}<br>"
            f"• Step 3: {next_info['step_3']}"
        )

        rows.append(f"""
      <tr data-tier="{_TIER_LABEL[c['tier']]}" data-play="{c['play']}" class="cluster-summary-row" onclick="toggleDetails('{i}')">
        <td class="rank">{i}</td>
        <td class="trim-col has-tip" data-tip="{cap_tip}">
          <b class="cell-title">{_esc(c['label'])}</b>
          <div class="cell-sub">{_esc(', '.join(c['owners']))}</div>
        </td>
        <td class="trim-col has-tip" data-tip="{mem_tip}">
          <div class="mem-pills">{mem_inline}</div>
          <div class="cell-sub">{len(c['owners'])} team{'s' if len(c['owners'])!=1 else ''}</div>
        </td>
        <td class="trim-col has-tip" data-tip="{why_tip}">
          <div class="ev-pills">{why_inline}</div>
        </td>
        <td class="trim-col has-tip" data-tip="{how_tip}">
          <span class="play p-{play_class}">{c['play']}</span>
          <div class="metric-line">
            <span class="metric-tag opp">Opp: {c['opportunity']}</span>
            <span class="tier t-{_TIER_LABEL[c['tier']]}">{c['tier']}</span>
          </div>
        </td>
        <td class="trim-col has-tip" data-tip="{next_tip}">
          <span class="action-pill {next_info['action_class']}">{next_info['badge']}</span>
          <div class="cell-sub">{_esc(next_info['summary'][:50])}...</div>
        </td>
        <td style="text-align:center;">
          <button type="button" class="btn-detail" id="btn-{i}" onclick="event.stopPropagation(); toggleDetails('{i}')">Details ▾</button>
        </td>
      </tr>
      <tr class="detail-row" id="detail-{i}" style="display:none;" data-tier="{_TIER_LABEL[c['tier']]}" data-play="{c['play']}">
        <td colspan="7">
          <div class="deep-dive-grid">
            <div class="dd-card dd-why">
              <h4>🔍 Why Did These Match?</h4>
              <div class="dd-content">
                <p class="dd-section-title">Shared Architectural Evidence ({len(c['shared'])} items):</p>
                <ul class="dd-list">
                  {"".join(why_details_list) or "<li>Semantic intent match</li>"}
                </ul>
                <p class="dd-section-title">Member Module Summaries:</p>
                <ul class="dd-list">
                  {"".join(member_summaries_list)}
                </ul>
              </div>
            </div>
            <div class="dd-card dd-how">
              <h4>⚙️ How Was This Decided?</h4>
              <div class="dd-content">
                <div class="dd-metrics-bar">
                  <div><span class="dd-label">Opportunity Score</span><span class="dd-val">{c['opportunity']}</span></div>
                  <div><span class="dd-label">Overlap Score</span><span class="dd-val">{c['score']}</span></div>
                  <div><span class="dd-label">Coupling Friction</span><span class="dd-val">{coupling_disp}</span></div>
                  <div><span class="dd-label">Confidence Tier</span><span class="dd-val">{c['tier']}</span></div>
                </div>
                <p class="dd-explanation">
                  <b>Mathematical Formulation:</b> Overlap ({c['score']}) &times; (1 &minus; Coupling ({coupling_disp})) = <b>{c['opportunity']}</b>
                </p>
                <p class="dd-explanation">
                  <b>Play Rationale ({c['play']}):</b> {next_info['rationale']}
                </p>
              </div>
            </div>
            <div class="dd-card dd-next">
              <h4>🚀 What Is The Next Step?</h4>
              <div class="dd-content">
                <ol class="dd-steps">
                  <li><b>Step 1 (Governance):</b> {next_info['step_1']}</li>
                  <li><b>Step 2 (Refactoring):</b> {next_info['step_2']}</li>
                  <li><b>Step 3 (Continuous CI Guardrail):</b> {next_info['step_3']}</li>
                </ol>
                <div class="dd-actions">
                  <span class="dd-chip">🛡️ One-Way Ratchet: <code>ratchets/</code></span>
                  <span class="dd-chip">🛠️ OpenRewrite Recipe: <code>recipes/rewrite.yml</code></span>
                </div>
              </div>
            </div>
          </div>
        </td>
      </tr>""")

    cand_rows = []
    for c in candidates:
        a_name = module_name.get(c['a'], c['a'])
        b_name = module_name.get(c['b'], c['b'])
        sum_a = summaries.get(c['a'], "")
        sum_b = summaries.get(c['b'], "")

        cand_tip = _esc(
            f"<b>Candidate Pair:</b><br>"
            f"• {a_name}: {_esc(sum_a or 'No summary')}<br>"
            f"• {b_name}: {_esc(sum_b or 'No summary')}<br>"
            f"<b>Similarity:</b> {c['similarity']}"
        )

        why_text = f"Semantic similarity {c['similarity']} across functional capabilities"
        next_text = "Run with --judge to evaluate with LLM / heuristic pairwise judge"

        cand_rows.append(f"""
      <tr>
        <td class="trim-col has-tip" data-tip="{cand_tip}">
          <b>{_esc(a_name)}</b> &harr; <b>{_esc(b_name)}</b>
        </td>
        <td class="num">{c['similarity']}</td>
        <td><span class="tier t-{_TIER_LABEL.get(c['tier'], 'med')}">{c['tier']}</span></td>
        <td class="trim-col has-tip" data-tip="{cand_tip}">
          <div class="cell-title">{_esc(why_text)}</div>
          <div class="cell-sub">{_esc(next_text)}</div>
        </td>
      </tr>""")

    mermaid_graph = generate_mermaid_diagram(store, clusters)

    doc = _TEMPLATE.format(
        projects=counts["projects"], modules=counts["modules"],
        facts=counts["integration_facts"], gaps=counts["gaps"],
        resolution=f"{resolution:.0f}", clusters=len(clusters),
        errors_count=errors_count,
        err_badge_class=err_badge_class,
        diag_class=diag_class,
        diag_msg=diag_msg,
        cluster_rows="".join(rows) or '<tr><td colspan="7">No duplicate clusters found.</td></tr>',
        cand_rows="".join(cand_rows) or '<tr><td colspan="4">No candidates above threshold.</td></tr>',
        mermaid_graph=mermaid_graph,
    )

    path = os.path.join(site, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)

    # Graphify / Cytoscape interoperability: emit graph.json
    import json
    nodes = {}
    edges_list = []
    for m in store.modules():
        nodes[m.id] = {"id": m.id, "label": m.name, "type": "module", "lang": m.lang}
    for f in store.integration_facts():
        res_key = f"{f.resource_type}:{f.resource_id}"
        if res_key not in nodes:
            nodes[res_key] = {"id": res_key, "label": f.resource_id, "type": "resource", "resource_type": f.resource_type}
        src = f.module_id if f.direction in ("PRODUCES", "WRITES") else res_key
        tgt = res_key if f.direction in ("PRODUCES", "WRITES") else f.module_id
        edges_list.append({"source": src, "target": tgt, "direction": f.direction, "tier": f.tier})

    graph_json_path = os.path.join(site, "graph.json")
    with open(graph_json_path, "w", encoding="utf-8") as gfh:
        json.dump({"nodes": list(nodes.values()), "edges": edges_list, "clusters": clusters}, gfh, indent=2)

    return {
        "resolution_rate": round(resolution, 1),
        "clusters": len(clusters),
        "candidates": len(candidates),
        "site": path,
        "graph_json": graph_json_path,
        "errors_count": errors_count,
        **counts
    }


_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Redundancy Map · Convergence Factory</title>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'neutral',
    maxTextSize: 5000000,
    securityLevel: 'loose',
    flowchart: {{ useMaxWidth: true, htmlLabels: true }}
  }});
</script>
<style>
  :root{{--bg:#F3F5F8;--surface:#fff;--surface2:#EAEEF3;--ink:#15202C;--muted:#5C6A78;
    --line:#D3DBE3;--accent:#B5561C;--high:#1F4E6B;--med:#4E7E9C;--low:#93A9B8;
    --mono:'IBM Plex Mono',ui-monospace,monospace;--sans:'IBM Plex Sans',system-ui,sans-serif;}}
  @media(prefers-color-scheme:dark){{:root{{--bg:#0F141A;--surface:#161D26;--surface2:#1C2530;
    --ink:#E7ECF1;--muted:#93A2B0;--line:#2A3540;--accent:#E08A44;--high:#7FB6D8;--med:#5687A6;--low:#54697A;}}}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.6;
    padding:clamp(1rem,4vw,3rem)}}
  .wrap{{max-width:1200px;margin:0 auto}}
  h1{{font-size:clamp(1.7rem,4vw,2.4rem);margin:0 0 .2rem;letter-spacing:-.02em}}
  h1 span{{color:var(--accent)}}
  .sub{{color:var(--muted);margin:0 0 1.8rem;font-size:.95rem}}
  .metrics{{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line);
    border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:1.5rem}}
  .metrics div{{background:var(--surface);padding:1rem}}
  .metrics .v{{font-size:1.7rem;font-weight:700;font-variant-numeric:tabular-nums}}
  .metrics .k{{font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}}
  .metric-ok{{color:#1F6B38}}
  .metric-warn{{color:#A44C13}}
  .metric-err{{color:#B3261E}}
  @media(max-width:850px){{.metrics{{grid-template-columns:repeat(3,1fr)}}}}

  .diag-banner{{display:flex;align-items:center;justify-content:space-between;padding:.75rem 1.2rem;
    border-radius:8px;margin-bottom:2rem;font-size:.85rem;border:1px solid var(--line)}}
  .diag-ok{{background:rgba(31,107,56,0.08);border-color:#C9EBD2}}
  .diag-warn{{background:rgba(164,76,19,0.08);border-color:#FCD9C0}}
  .btn-error-txt{{font-family:var(--mono);font-size:.75rem;padding:.3rem .75rem;border-radius:6px;
    background:var(--surface);border:1px solid var(--line);color:var(--ink);text-decoration:none;font-weight:600}}
  .btn-error-txt:hover{{background:var(--surface2)}}

  h2{{font-size:1.15rem;margin:2.2rem 0 .3rem}}
  .controls{{display:flex;gap:1rem;margin:.8rem 0;flex-wrap:wrap;align-items:center;justify-content:space-between}}
  .filters{{display:flex;gap:.5rem;flex-wrap:wrap}}
  .filters button{{font-family:var(--mono);font-size:.72rem;padding:.35rem .8rem;border-radius:20px;
    border:1px solid var(--line);background:var(--surface);color:var(--muted);cursor:pointer}}
  .filters button.on{{background:var(--accent);color:#fff;border-color:var(--accent)}}
  .search-box{{flex:1;max-width:320px;min-width:200px}}
  .search-box input{{width:100%;padding:.4rem .8rem;font-family:var(--sans);font-size:.85rem;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink)}}
  
  .graph-card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:1.5rem;overflow-x:auto;margin-top:.8rem}}
  
  table{{width:100%;border-collapse:collapse;font-size:.88rem;background:var(--surface);
    border:1px solid var(--line);border-radius:10px;overflow:hidden;table-layout:fixed}}
  th,td{{text-align:left;padding:.7rem .8rem;border-bottom:1px solid var(--line);vertical-align:middle}}
  th{{font-family:var(--mono);font-size:.64rem;letter-spacing:.08em;text-transform:uppercase;
    color:var(--muted);background:var(--surface2)}}
  
  .rank{{font-family:var(--mono);color:var(--muted);width:38px}}
  .num{{font-variant-numeric:tabular-nums;text-align:right;font-family:var(--mono)}}
  
  /* Trimming & Tooltips */
  .trim-col{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}}
  .cell-title{{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .cell-sub{{color:var(--muted);font-size:.75rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px}}
  .has-tip{{cursor:help;position:relative}}
  
  .mem-pills, .ev-pills{{display:flex;gap:4px;overflow:hidden;white-space:nowrap;align-items:center}}
  .mem{{display:inline-flex;align-items:center;background:var(--surface2);border:1px solid var(--line);border-radius:6px;
    padding:.1rem .45rem;font-size:.78rem;white-space:nowrap}}
  .mem i{{font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-left:.35rem;font-style:normal}}
  .mem-more, .ev-more{{background:var(--surface2);border:1px solid var(--line);border-radius:6px;padding:.1rem .4rem;font-size:.72rem;color:var(--muted)}}
  
  /* Evidence Badges */
  .ev-badge{{display:inline-flex;align-items:center;font-family:var(--mono);font-size:.72rem;padding:.12rem .45rem;border-radius:5px;white-space:nowrap}}
  .ev-kafka{{background:#E8F4FD;color:#1B588C;border:1px solid #C4E0F9}}
  .ev-sql{{background:#FEF3EB;color:#A44C13;border:1px solid #FCD9C0}}
  .ev-http{{background:#EBF7EE;color:#1F6B38;border:1px solid #C9EBD2}}
  .ev-clone{{background:#F5EEFA;color:#6D2C8E;border:1px solid #E4CEF2}}
  .ev-semantic{{background:#EDF3F7;color:#2B4E68;border:1px solid #D2E0EB}}
  .ev-other{{background:var(--surface2);color:var(--ink);border:1px solid var(--line)}}

  /* Decision & Metrics */
  .metric-line{{display:flex;gap:4px;align-items:center;margin-top:3px}}
  .metric-tag{{font-family:var(--mono);font-size:.64rem;padding:.08rem .35rem;border-radius:4px;border:1px solid var(--line);background:var(--surface2)}}
  .tier{{font-family:var(--mono);font-size:.62rem;font-weight:600;padding:.08rem .4rem;border-radius:4px;color:#fff}}
  .t-high{{background:var(--high)}}.t-med{{background:var(--med)}}.t-low{{background:var(--low);color:var(--ink)}}
  
  /* Play & Action Badges */
  .play{{font-family:var(--mono);font-size:.66rem;font-weight:600;padding:.15rem .5rem;border-radius:5px;
    border:1px solid var(--line);background:var(--surface2);display:inline-block}}
  .p-retire{{color:#fff;background:var(--accent);border-color:var(--accent)}}
  .p-standardize{{color:var(--accent)}}
  .action-pill{{font-family:var(--mono);font-size:.68rem;padding:.15rem .5rem;border-radius:5px;display:inline-block;font-weight:600;white-space:nowrap}}
  .act-retire{{background:#FEECEB;color:#B3261E;border:1px solid #F9C8C6}}
  .act-standardize{{background:#FEF3EB;color:#A44C13;border:1px solid #FCD9C0}}
  .act-extract{{background:#E8F4FD;color:#1B588C;border:1px solid #C4E0F9}}
  .act-leave{{background:#F1F4F6;color:#5C6A78;border:1px solid #D9E0E6}}

  .btn-detail{{background:var(--surface2);border:1px solid var(--line);border-radius:5px;
    padding:.25rem .6rem;font-size:.72rem;font-family:var(--mono);color:var(--ink);cursor:pointer}}
  .btn-detail:hover{{background:var(--line)}}

  /* Accordion Detail Row */
  .cluster-summary-row{{cursor:pointer;transition:background .15s ease}}
  .cluster-summary-row:hover{{background:var(--surface2)}}
  .detail-row td{{padding:0;background:var(--surface2);border-bottom:1px solid var(--line)}}
  .deep-dive-grid{{display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:14px;padding:16px}}
  .dd-card{{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px}}
  .dd-card h4{{margin:0 0 10px;font-size:.9rem;color:var(--ink);display:flex;align-items:center;gap:6px}}
  .dd-section-title{{font-family:var(--mono);font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:8px 0 4px}}
  .dd-list{{margin:0 0 8px;padding-left:18px;font-size:.82rem;color:var(--ink);line-height:1.5}}
  .dd-steps{{margin:0 0 10px;padding-left:18px;font-size:.82rem;line-height:1.6;color:var(--ink)}}
  .dd-explanation{{font-size:.82rem;line-height:1.5;color:var(--ink);margin:6px 0}}
  .dd-metrics-bar{{display:grid;grid-template-columns:repeat(2, 1fr);gap:8px;margin-bottom:10px}}
  .dd-metrics-bar div{{background:var(--surface2);border-radius:6px;padding:8px 10px}}
  .dd-label{{display:block;font-family:var(--mono);font-size:.62rem;color:var(--muted);text-transform:uppercase}}
  .dd-val{{display:block;font-size:1.05rem;font-weight:700;color:var(--ink)}}
  .dd-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
  .dd-chip{{font-family:var(--mono);font-size:.72rem;background:var(--surface2);border:1px solid var(--line);border-radius:5px;padding:.2rem .5rem}}

  /* Floating Tooltip */
  #floating-tooltip{{position:fixed;display:none;background:var(--surface);color:var(--ink);
    border:1px solid var(--line);box-shadow:0 12px 28px rgba(0,0,0,0.16);border-radius:8px;
    padding:10px 14px;font-size:.82rem;line-height:1.45;max-width:380px;z-index:999999;
    pointer-events:none;white-space:normal;word-break:break-word}}

  footer{{margin-top:2.5rem;color:var(--muted);font-family:var(--mono);font-size:.72rem}}
</style></head><body>
<div id="floating-tooltip"></div>
<div class="wrap">
  <h1>Redundancy <span>Map</span></h1>
  <p class="sub">Convergence Factory · Layered evidence pipeline, why-matching diagnostics &amp; actionable remediation.</p>
  
  <div class="metrics">
    <div><div class="v">{projects}</div><div class="k">Projects</div></div>
    <div><div class="v">{modules}</div><div class="k">Modules</div></div>
    <div><div class="v">{facts}</div><div class="k">Integration facts</div></div>
    <div><div class="v">{clusters}</div><div class="k">Duplicate clusters</div></div>
    <div><div class="v">{resolution}%</div><div class="k">Resolution rate</div></div>
    <div><div class="v {err_badge_class}">{errors_count}</div><div class="k">Framework Issues</div></div>
  </div>

  <div class="diag-banner {diag_class}">
    <div class="diag-text">{diag_msg}</div>
    <a href="error.txt" target="_blank" class="btn-error-txt">Inspect error.txt ↗</a>
  </div>

  <h2>Integration Topology &amp; Wiring Graph</h2>
  <div class="graph-card">
    <pre class="mermaid">
{mermaid_graph}
    </pre>
  </div>

  <h2>Convergence Opportunities</h2>
  <div class="controls">
    <div class="filters">
      <button data-f="high" class="on">Exec · HIGH</button>
      <button data-f="med">Prioritization · +MED</button>
      <button data-f="all">Exploratory · all</button>
    </div>
    <div class="search-box">
      <input type="text" id="filterSearch" placeholder="Search clusters, resources, teams..." />
    </div>
  </div>
  <table id="clusters">
    <thead>
      <tr>
        <th style="width:38px;">#</th>
        <th style="width:200px;">Capability &amp; Intent</th>
        <th style="width:190px;">Members &amp; Teams</th>
        <th style="width:190px;">Why Matched?</th>
        <th style="width:150px;">How Decided?</th>
        <th style="width:180px;">What Is Next Step?</th>
        <th style="width:70px;text-align:center;">Action</th>
      </tr>
    </thead>
    <tbody>{cluster_rows}</tbody>
  </table>

  <h2>Semantic Candidates <span style="font-weight:400;color:var(--muted);font-size:.8rem">— recall only, unconfirmed</span></h2>
  <table id="candidates">
    <thead>
      <tr>
        <th style="width:280px;">Module pair</th>
        <th style="width:110px;text-align:right;">Similarity</th>
        <th style="width:100px;">Tier</th>
        <th>Why Suggested &amp; Next Step</th>
      </tr>
    </thead>
    <tbody>{cand_rows}</tbody>
  </table>

  <p style="color:var(--muted);font-size:.8rem;margin-top:1.2rem">Unresolved references (config/dynamic): <b>{gaps}</b> — tracked gaps, not silent misses.</p>
  <footer>Generated by the Convergence Factory · deterministic probes + semantic recall · framework diagnostics in error.txt</footer>
</div>

<script>
  var order = {{all:['high','med','low'], med:['high','med'], high:['high']}};
  var currentFilter = 'high';
  var searchInput = document.getElementById('filterSearch');

  function toggleDetails(id) {{
    var row = document.getElementById('detail-' + id);
    var btn = document.getElementById('btn-' + id);
    if (!row) return;
    if (row.style.display === 'none' || !row.style.display) {{
      row.style.display = 'table-row';
      if (btn) btn.innerText = 'Details ▴';
    }} else {{
      row.style.display = 'none';
      if (btn) btn.innerText = 'Details ▾';
    }}
  }}
  window.toggleDetails = toggleDetails;

  function updateView() {{
    var allow = order[currentFilter];
    var q = searchInput ? searchInput.value.toLowerCase().trim() : '';
    document.querySelectorAll('#clusters tbody tr.cluster-summary-row').forEach(function(tr) {{
      var matchesTier = allow.indexOf(tr.dataset.tier) >= 0;
      var matchesText = !q || tr.innerText.toLowerCase().indexOf(q) >= 0;
      var show = matchesTier && matchesText;
      tr.style.display = show ? '' : 'none';
      var id = tr.getAttribute('onclick') ? tr.getAttribute('onclick').replace(/[^0-9]/g, '') : '';
      var detail = document.getElementById('detail-' + id);
      if (detail && !show) detail.style.display = 'none';
    }});
  }}

  document.querySelectorAll('.filters button').forEach(function(b) {{
    b.addEventListener('click', function() {{
      currentFilter = b.dataset.f;
      document.querySelectorAll('.filters button').forEach(function(btn) {{
        btn.classList.toggle('on', btn === b);
      }});
      updateView();
    }});
  }});

  if (searchInput) {{
    searchInput.addEventListener('input', updateView);
  }}

  // Floating Tooltip Event Handlers
  var tipBox = document.getElementById('floating-tooltip');
  document.addEventListener('mouseover', function(e) {{
    var tipTarget = e.target.closest('[data-tip]');
    if (tipTarget && tipBox) {{
      var tipHtml = tipTarget.getAttribute('data-tip');
      if (tipHtml) {{
        tipBox.innerHTML = tipHtml;
        tipBox.style.display = 'block';
      }}
    }}
  }});

  document.addEventListener('mousemove', function(e) {{
    if (tipBox && tipBox.style.display === 'block') {{
      var x = e.clientX + 14;
      var y = e.clientY + 14;
      if (x + tipBox.offsetWidth > window.innerWidth) x = window.innerWidth - tipBox.offsetWidth - 12;
      if (y + tipBox.offsetHeight > window.innerHeight) y = window.innerHeight - tipBox.offsetHeight - 12;
      tipBox.style.left = x + 'px';
      tipBox.style.top = y + 'px';
    }}
  }});

  document.addEventListener('mouseout', function(e) {{
    var tipTarget = e.target.closest('[data-tip]');
    if (tipTarget && tipBox) {{
      tipBox.style.display = 'none';
    }}
  }});

  updateView();
</script>
</body></html>"""

