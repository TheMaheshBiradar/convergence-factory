"""Portfolio dashboard — stats first, then filter, then drill down.

The capability matrix is a wide grid; at 200+ projects you want to start from
KPIs, slice by dimension / play / tier / team, and only then open a specific
capability. This renders a single self-contained interactive HTML page (no server,
no libraries): KPI tiles, clickable dimension/play breakdowns, a filter bar, a
sortable capability table, and per-row drill-down showing members and the
convergence target. All data is embedded; filtering/sorting/drill-down run in the
browser.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from typing import List

from ..core.capability import Capability


def _build_data(caps: List[Capability], convergence: dict, tech: dict, store) -> dict:
    conv_by_id = {p["capability_id"]: p for p in convergence.get("capability_plans", [])}
    rows = []
    for c in caps:
        p = conv_by_id.get(c.id, {})
        rows.append({
            "id": c.id, "label": c.label, "dimension": c.dimension, "play": c.play,
            "tier": c.tier, "opportunity": c.opportunity, "coupling": c.coupling,
            "owners": c.owners, "member_count": len(c.module_ids),
            "members": [{"m": m["module"].split(":")[0], "dir": m["direction"],
                         "tier": m["tier"]} for m in c.members],
            "canonical": (p.get("canonical", "") or "").split(":")[0],
            "target": p.get("target", ""),
            "migrate_from": [x.split(":")[0] for x in p.get("migrate_from", [])],
        })
    owners = store.module_owner()
    return {
        "stats": {
            "projects": len(store.projects()),
            "modules": len(store.modules()),
            "shared_capabilities": len(rows),
            "languages": dict(Counter(m.lang for m in store.modules() if m.lang).most_common()),
            "teams": dict(Counter(o for o in owners.values()).most_common()),
            "by_dimension": dict(Counter(r["dimension"] for r in rows).most_common()),
            "by_play": dict(Counter(r["play"] for r in rows).most_common()),
        },
        "rollup": convergence.get("rollup", {}),
        "capabilities": rows,
        "tech": tech.get("categories", []),
    }


def render(caps: List[Capability], convergence: dict, tech: dict, store,
           out_dir: str) -> dict:
    site = os.path.join(out_dir, "site")
    os.makedirs(site, exist_ok=True)
    data = _build_data(caps, convergence, tech, store)
    payload = json.dumps(data).replace("</", "<\\/")
    doc = _SHELL.replace("/*__DATA__*/null", payload)
    path = os.path.join(site, "dashboard.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return {"dashboard_html": path}


_SHELL = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portfolio Dashboard</title>
<style>
  :root{--bg:#F3F5F8;--surface:#fff;--surface2:#EAEEF3;--ink:#15202C;--muted:#5C6A78;
    --line:#D3DBE3;--accent:#B5561C;--high:#1F4E6B;--med:#4E7E9C;--low:#93A9B8;
    --good:#2F7A5B;--mono:'IBM Plex Mono',ui-monospace,monospace;--sans:'IBM Plex Sans',system-ui,sans-serif;}
  @media(prefers-color-scheme:dark){:root{--bg:#0F141A;--surface:#161D26;--surface2:#1C2530;
    --ink:#E7ECF1;--muted:#93A2B0;--line:#2A3540;--accent:#E08A44;--high:#7FB6D8;--med:#5687A6;--low:#54697A;--good:#5FB98C;}}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
    padding:clamp(1rem,3vw,2.2rem);line-height:1.5}
  h1{font-size:1.7rem;margin:0 0 .1rem;letter-spacing:-.02em} h1 span{color:var(--accent)}
  .sub{color:var(--muted);margin:0 0 1.4rem;font-size:.9rem}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);
    border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:1.6rem}
  .kpi{background:var(--surface);padding:1rem 1.1rem}
  .kpi .v{font-size:1.9rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
  .kpi .k{font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:.3rem}
  .kpi.accent .v{color:var(--accent)}
  .breakout{display:flex;gap:1.4rem;flex-wrap:wrap;margin-bottom:1.2rem}
  .bo h3{font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 .4rem}
  .chips{display:flex;gap:.4rem;flex-wrap:wrap}
  .chip{font-family:var(--mono);font-size:.72rem;padding:.28rem .6rem;border-radius:20px;border:1px solid var(--line);
    background:var(--surface);color:var(--ink);cursor:pointer;white-space:nowrap}
  .chip b{color:var(--muted);margin-left:.35rem;font-weight:600}
  .chip.on{background:var(--accent);color:#fff;border-color:var(--accent)} .chip.on b{color:#fff}
  .filters{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;margin-bottom:1rem}
  .filters input,.filters select{font-family:var(--sans);font-size:.85rem;padding:.4rem .6rem;border-radius:8px;
    border:1px solid var(--line);background:var(--surface);color:var(--ink)}
  .filters input{flex:1;min-width:180px}
  .count{font-family:var(--mono);font-size:.75rem;color:var(--muted);margin-left:auto}
  table{width:100%;border-collapse:collapse;font-size:.86rem;background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
  th,td{text-align:left;padding:.55rem .7rem;border-bottom:1px solid var(--line);vertical-align:top}
  thead th{font-family:var(--mono);font-size:.62rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);background:var(--surface2);cursor:pointer;user-select:none}
  thead th.num,td.num{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--mono)}
  tr.cap{cursor:pointer} tr.cap:hover td{background:var(--surface2)}
  .tier{font-family:var(--mono);font-size:.6rem;font-weight:600;padding:.05rem .4rem;border-radius:4px;color:#fff}
  .t-HIGH{background:var(--high)} .t-MED{background:var(--med)} .t-LOW{background:var(--low);color:var(--ink)}
  .play{font-family:var(--mono);font-size:.62rem;font-weight:600;padding:.1rem .45rem;border-radius:5px;border:1px solid var(--line);background:var(--surface2)}
  .p-RETIRE{color:#fff;background:var(--accent);border-color:var(--accent)} .p-STANDARDIZE{color:var(--accent)}
  .canon{font-family:var(--mono);font-weight:700;color:var(--accent)}
  .detail td{background:var(--surface2)} .detail .box{display:flex;gap:1.6rem;flex-wrap:wrap;font-size:.82rem}
  .detail .tgt{color:var(--good);font-family:var(--mono);font-size:.78rem;margin-bottom:.5rem}
  .mem{display:inline-block;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:.1rem .45rem;margin:.12rem .2rem .12rem 0;font-size:.78rem}
  .mem i{font-family:var(--mono);font-size:.6rem;color:var(--muted);font-style:normal;margin-left:.3rem}
  h2{font-size:1.05rem;margin:2rem 0 .5rem}
  .muted{color:var(--muted)}
</style></head><body>
  <h1>Portfolio <span>Dashboard</span></h1>
  <p class="sub">Stats first &rarr; filter &rarr; drill down. Click a dimension/play chip to filter; click a row to open its members and convergence target.</p>
  <div class="kpis" id="kpis"></div>
  <div class="breakout">
    <div class="bo"><h3>By dimension (click to filter)</h3><div class="chips" id="dimChips"></div></div>
    <div class="bo"><h3>By play (click to filter)</h3><div class="chips" id="playChips"></div></div>
  </div>
  <div class="filters">
    <input id="q" placeholder="Search capability, module, owner...">
    <select id="fTier"><option value="">All tiers</option><option>HIGH</option><option>MED</option><option>LOW</option></select>
    <select id="fTeam"><option value="">All teams</option></select>
    <select id="sort">
      <option value="opportunity">Sort: opportunity</option>
      <option value="member_count">Sort: members</option>
      <option value="label">Sort: name</option>
    </select>
    <span class="count" id="count"></span>
  </div>
  <table id="tbl"><thead><tr>
    <th data-s="play">Play</th><th data-s="dimension">Dim</th><th data-s="label">Capability</th>
    <th data-s="tier">Tier</th><th class="num" data-s="opportunity">Opp</th>
    <th class="num" data-s="member_count">Members</th><th data-s="owners">Owners</th>
    <th data-s="canonical">&rarr; Canonical</th>
  </tr></thead><tbody id="rows"></tbody></table>
  <h2>Tech standards</h2>
  <table><thead><tr><th>Category</th><th>Standard</th><th>Outliers to migrate</th></tr></thead><tbody id="tech"></tbody></table>

<script id="data" type="application/json">/*__DATA__*/null</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('data').textContent) || {stats:{},capabilities:[],tech:[],rollup:{}};
  var caps = D.capabilities || [], S = D.stats || {}, R = D.rollup || {};
  var state = {dim:"", play:"", tier:"", team:"", q:"", sort:"opportunity", dir:-1, open:{}};

  function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}

  // KPI tiles
  var kpis = [
    ["Projects", S.projects||0, ""], ["Modules", S.modules||0, ""],
    ["Shared capabilities", S.shared_capabilities||0, ""],
    ["Duplicate clusters", (caps.length), "accent"],
    ["Modules to migrate", R.modules_to_migrate||0, "accent"],
    ["Canonical targets", R.canonical_targets||0, ""],
    ["New shared components", R.new_shared_components||0, ""],
    ["Tech to standardize", R.tech_standardizations||0, ""]
  ];
  document.getElementById('kpis').innerHTML = kpis.map(function(k){
    return '<div class="kpi '+k[2]+'"><div class="v">'+k[1]+'</div><div class="k">'+k[0]+'</div></div>';}).join('');

  // chips
  function chips(el, obj, key){
    var host=document.getElementById(el);
    host.innerHTML = Object.keys(obj||{}).map(function(k){
      return '<span class="chip" data-k="'+esc(k)+'">'+esc(k)+'<b>'+obj[k]+'</b></span>';}).join('');
    host.querySelectorAll('.chip').forEach(function(c){
      c.addEventListener('click',function(){
        state[key] = (state[key]===c.dataset.k)?"":c.dataset.k; sync(); render();});});
  }
  chips('dimChips', S.by_dimension, 'dim');
  chips('playChips', S.by_play, 'play');

  // team select
  var team=document.getElementById('fTeam');
  Object.keys(S.teams||{}).forEach(function(t){var o=document.createElement('option');o.value=t;o.textContent=t+' ('+S.teams[t]+')';team.appendChild(o);});

  function sync(){
    document.querySelectorAll('#dimChips .chip').forEach(function(c){c.classList.toggle('on',c.dataset.k===state.dim);});
    document.querySelectorAll('#playChips .chip').forEach(function(c){c.classList.toggle('on',c.dataset.k===state.play);});
  }

  function match(r){
    if(state.dim && r.dimension!==state.dim) return false;
    if(state.play && r.play!==state.play) return false;
    if(state.tier && r.tier!==state.tier) return false;
    if(state.team && (r.owners||[]).indexOf(state.team)<0) return false;
    if(state.q){
      var q=state.q.toLowerCase();
      var hay=(r.label+' '+r.canonical+' '+(r.owners||[]).join(' ')+' '+(r.members||[]).map(function(m){return m.m;}).join(' ')).toLowerCase();
      if(hay.indexOf(q)<0) return false;
    }
    return true;
  }

  function render(){
    var list = caps.filter(match);
    var k=state.sort, dir=state.dir;
    list.sort(function(a,b){var x=a[k],y=b[k];if(k==='label'||k==='play'||k==='dimension'||k==='canonical'){x=String(x);y=String(y);return dir*x.localeCompare(y);}return dir*((x||0)-(y||0));});
    document.getElementById('count').textContent = list.length+' of '+caps.length+' capabilities';
    var html = list.map(function(r,i){
      var owners=(r.owners||[]).join(', ');
      var row = '<tr class="cap" data-id="'+esc(r.id)+'">'
        +'<td><span class="play p-'+esc(r.play)+'">'+esc(r.play)+'</span></td>'
        +'<td>'+esc(r.dimension)+'</td>'
        +'<td><b>'+esc(r.label)+'</b></td>'
        +'<td><span class="tier t-'+esc(r.tier)+'">'+esc(r.tier)+'</span></td>'
        +'<td class="num">'+esc(r.opportunity)+'</td>'
        +'<td class="num">'+esc(r.member_count)+'</td>'
        +'<td class="muted">'+esc(owners)+'</td>'
        +'<td class="canon">'+esc(r.canonical||'&mdash;')+'</td></tr>';
      if(state.open[r.id]){
        var mems=(r.members||[]).map(function(m){return '<span class="mem">'+esc(m.m)+'<i>'+esc(m.dir)+' &middot; '+esc(m.tier)+'</i></span>';}).join('');
        var mig=(r.migrate_from||[]).join(', ');
        row += '<tr class="detail"><td colspan="8">'
          +'<div class="tgt">&#9654; Unify into: '+esc(r.canonical||'(new shared component)')+' &mdash; '+esc(r.target)+'</div>'
          +'<div class="box"><div><b>Members</b><br>'+mems+'</div>'
          +(mig?'<div><b>Converge from</b><br><span class="muted">'+esc(mig)+'</span></div>':'')+'</div></td></tr>';
      }
      return row;
    }).join('');
    document.getElementById('rows').innerHTML = html || '<tr><td colspan="8" class="muted">No capabilities match the filter.</td></tr>';
    document.querySelectorAll('#rows tr.cap').forEach(function(tr){
      tr.addEventListener('click',function(){var id=tr.dataset.id;state.open[id]=!state.open[id];render();});});
  }

  // tech table
  document.getElementById('tech').innerHTML = (D.tech||[]).map(function(t){
    return '<tr><td>'+esc(t.category)+'</td><td class="canon">'+esc(t.standard)+'</td><td class="muted">'+esc((t.outliers||[]).join(', ')||'&mdash;')+'</td></tr>';
  }).join('') || '<tr><td colspan="3" class="muted">No fragmented tech categories.</td></tr>';

  // wire filters
  document.getElementById('q').addEventListener('input',function(e){state.q=e.target.value;render();});
  document.getElementById('fTier').addEventListener('change',function(e){state.tier=e.target.value;render();});
  document.getElementById('fTeam').addEventListener('change',function(e){state.team=e.target.value;render();});
  document.getElementById('sort').addEventListener('change',function(e){state.sort=e.target.value;render();});
  document.querySelectorAll('#tbl thead th').forEach(function(th){th.addEventListener('click',function(){
    var s=th.dataset.s; if(!s)return; if(state.sort===s){state.dir*=-1;}else{state.sort=s;state.dir=(s==='label'||s==='play'||s==='dimension'||s==='canonical')?1:-1;} render();});});

  render();
})();
</script>
</body></html>"""
