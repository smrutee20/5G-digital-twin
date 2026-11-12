/* 5G Core Explorer: behaviour. Content lives in data.js. */
(function () {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs || {}) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const params = new URLSearchParams(location.search);
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ================================================================ model */
const FLAT = [], PROC_RANGE = {};
PROCS.forEach((p, pi) => {
  const a = FLAT.length;
  p.steps.forEach((s, si) => FLAT.push(Object.assign({ proc: p.id, pi, si }, s)));
  PROC_RANGE[p.id] = [a, FLAT.length - 1];
});
const INIT = { net: "powered off", rrc: "— (UE off)", rm: "RM-DEREGISTERED", cm: "CM-IDLE", cell: "—", crnti: "—", ueId: "—", guti: "—", sec: "none",
  pdu: "—", ip: "—", qos: "—", teidUl: "—", teidDl: "—", up: "—", uePos: "g1", serving: "gNB1" };
const STATE_LABELS = [["net", "Network"], ["rrc", "RRC"], ["rm", "RM"], ["cm", "CM"], ["cell", "Serving cell"], ["crnti", "C-RNTI"], ["ueId", "Identity (core)"], ["guti", "5G-GUTI"],
  ["sec", "Security"], ["pdu", "PDU session"], ["ip", "UE IP"], ["qos", "QoS flows"], ["teidUl", "N3 uplink TEID"], ["teidDl", "N3 downlink TEID"], ["up", "User plane"]];
const BEFORE = [], AFTER = [];
{ let c = Object.assign({}, INIT); FLAT.forEach(s => { BEFORE.push(Object.assign({}, c)); if (s.s) Object.assign(c, s.s); AFTER.push(Object.assign({}, c)); }); }

const P = { tab: "map", scope: "all", idx: -1, playing: false, speed: 1, speak: false, cc: true, token: 0, sel: null, iso: false };
const range = () => P.scope === "all" ? [0, FLAT.length - 1] : PROC_RANGE[P.scope];
const stateAt = i => i < 0 ? BEFORE[range()[0]] : AFTER[i];

/* ================================================================ twin link-in */
const twin = { f: +params.get("f") || 3.5, bw: +params.get("bw") || 100, prb: +params.get("prb") || 273, scs: +params.get("scs") || 30, title: params.get("title") };
if (params.get("from") === "twin") {
  $("#back").hidden = false;
  const back = params.get("back");                  // relative page to return to, e.g. ../../twin.html
  if (back && /^[\w./-]+\.html$/.test(back)) $("#back").href = back;
  const tb = $("#twinbar"); tb.hidden = false;
  tb.innerHTML = `Opened from your RAN digital twin${twin.title ? ` · <b>${esc(twin.title)}</b>` : ""} · carrier ${twin.f.toFixed(2)} GHz, ${twin.bw} MHz, ${twin.prb} PRB, ${twin.scs} kHz SCS. The gNBs on this map are what the twin models; this explorer shows everything behind them.`;
}

/* ================================================================ tabs */
function setTab(t) {
  P.tab = t;
  $$("nav.tabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === t));
  ["map", "flow", "api", "air", "gloss"].forEach(k => $("#v-" + k).hidden = k !== t);
  $("#playerbox").hidden = !(t === "map" || t === "flow");
  if (t === "flow") { renderChart(); renderDecode(); }
  if (t === "air") drawAir();
}
$$("nav.tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));

/* ================================================================ map */
const svg = $("#map");
const defs = el("defs", {}, svg);
defs.innerHTML = `<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`;
const gBus = el("g", {}, svg), gLinks = el("g", {}, svg), gLabels = el("g", {}, svg), gNodes = el("g", {}, svg), gFx = el("g", {}, svg);
const KIND = { ue: ["#2a1a12", "#f28c5b"], ran: ["#2a2412", "#f5c64a"], cp: ["#122234", "#6fb1ff"], up: ["#132a1e", "#38c99a"], ext: ["#1a2129", "#93a4b3"] };
const IS_SBI = n => SBI_NODES.includes(n);
const LINK_PLANE = { Uu: "both", N1: "cp", N2: "cp", N3: "up", Xn: "both", N4: "cp", N6: "up", N33: "cp" };
const NODE_W = id => id === "UE" ? 92 : 108, NODE_H = 50;

// service-based bus
el("rect", { class: "bus", x: 420, y: BUS_Y - 9, width: 780, height: 18, rx: 9 }, gBus);
const busLbl = el("text", { x: 410, y: BUS_Y + 4, "text-anchor": "end", fill: "#64768a", "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, gBus);
busLbl.textContent = "SBI bus · HTTP/2";
const busHit = el("rect", { x: 420, y: BUS_Y - 10, width: 780, height: 20, fill: "transparent", style: "cursor:pointer" }, gBus);
busHit.addEventListener("click", () => select({ iface: "SBI" }));
const stubs = {};
SBI_NODES.forEach(n => {
  const N = NODES[n], top = N.y < BUS_Y, y1 = top ? N.y + NODE_H / 2 : N.y - NODE_H / 2;
  const line = el("line", { class: "link", x1: N.x, y1, x2: N.x, y2: BUS_Y }, gBus);
  const g = el("g", { class: "ifl" }, gLabels);
  const txt = "N" + n.toLowerCase(), w = txt.length * 6.6 + 10, ly = (y1 + BUS_Y) / 2;
  el("rect", { x: N.x + 6, y: ly - 9, width: w, height: 17, rx: 4 }, g);
  const t = el("text", { x: N.x + 6 + w / 2, y: ly + 4 }, g); t.textContent = txt;
  g.addEventListener("click", () => select({ iface: "SBI" }));
  stubs[n] = { line, g };
});

// reference-point links
const linkEls = {};
LINKS.forEach(L => {
  const plane = LINK_PLANE[L.iface];
  const path = el("path", { class: "link" + (plane === "up" ? " up" : "") + (L.logical ? " logical" : "") }, gLinks);
  const hit = el("path", { class: "hit" }, gLinks);
  const g = el("g", { class: "ifl" }, gLabels);
  const r = el("rect", { height: 17, rx: 4 }, g);
  const t = el("text", {}, g); t.textContent = L.iface;
  const w = L.iface.length * 6.6 + 10; r.setAttribute("width", w);
  const pick = () => select({ iface: L.iface });
  hit.addEventListener("click", pick); g.addEventListener("click", pick);
  linkEls[L.id] = { L, path, hit, g, r, t, w, plane };
});

function nodeXY(id, st) { return id === "UE" ? UE_POS[(st || INIT).uePos] : [NODES[id].x, NODES[id].y]; }
function layoutLinks(st) {
  Object.values(linkEls).forEach(o => {
    const [ax, ay] = nodeXY(o.L.a, st), [bx, by] = nodeXY(o.L.b, st);
    let d, lx, ly;
    if (o.L.id === "N1") {
      const cx = ax + 140, cy = 150; d = `M${ax},${ay - 25} Q${cx},${cy} ${bx - 54},${by - 8}`;
      lx = 0.25 * ax + 0.5 * cx + 0.25 * (bx - 54); ly = 0.25 * (ay - 25) + 0.5 * cy + 0.25 * (by - 8);
    } else { d = `M${ax},${ay} L${bx},${by}`; lx = (ax + bx) / 2; ly = (ay + by) / 2; }
    if (o.L.id === "N3a" || o.L.id === "N3b") { lx = ax + (bx - ax) * 0.62; ly = ay + (by - ay) * 0.62; }
    if (o.L.id === "N2a" || o.L.id === "N2b") { lx = ax + (bx - ax) * 0.45; ly = ay + (by - ay) * 0.45; }
    o.path.setAttribute("d", d); o.hit.setAttribute("d", d);
    o.r.setAttribute("x", lx - o.w / 2); o.r.setAttribute("y", ly - 9);
    o.t.setAttribute("x", lx); o.t.setAttribute("y", ly + 4);
  });
}

// nodes
const nodeEls = {};
Object.entries(NODES).forEach(([id, N]) => {
  const [fill, stroke] = KIND[N.kind], w = NODE_W(id);
  const g = el("g", { class: "node" + (id === "UE" ? " ue-node" : ""), tabindex: 0, role: "button", "aria-label": `${N.label}: ${(NF_INFO[id] || {}).full || ""}` }, gNodes);
  g.style.transform = `translate(${N.x}px,${N.y}px)`;
  el("rect", { x: -w / 2, y: -NODE_H / 2, width: w, height: NODE_H, rx: id === "UE" ? 14 : 8, fill, stroke }, g);
  const lb = el("text", { class: "lb", y: -2 }, g); lb.textContent = N.label;
  const sb = el("text", { class: "sb", y: 15 }, g); sb.textContent = N.sub;
  g.addEventListener("click", () => select({ node: id }));
  g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select({ node: id }); } });
  nodeEls[id] = { g, rect: g.querySelector("rect"), sb, stroke };
});

/* ---------- routing of a message across the map */
function adjacency(st, keep) {
  const E = [];
  const ok = n => !(n === "gNB1" || n === "gNB2") || n === st.serving || keep.includes(n);
  LINKS.forEach(L => { if (!L.logical && ok(L.a) && ok(L.b)) E.push([L.a, L.b]); });
  SBI_NODES.forEach((a, i) => SBI_NODES.slice(i + 1).forEach(b => E.push([a, b])));
  const A = {}; E.forEach(([a, b]) => { (A[a] = A[a] || []).push(b); (A[b] = A[b] || []).push(a); });
  return A;
}
function bfs(A, a, b) {
  const prev = { [a]: null }, q = [a];
  while (q.length) { const x = q.shift(); if (x === b) break; (A[x] || []).forEach(y => { if (!(y in prev)) { prev[y] = x; q.push(y); } }); }
  if (!(b in prev)) return [a, b];
  const out = []; for (let x = b; x != null; x = prev[x]) out.unshift(x); return out;
}
function routeNodes(step, st) {
  const wps = [step.f].concat(step.via || [], [step.t]);
  const A = adjacency(st, wps); const out = [wps[0]];
  for (let k = 1; k < wps.length; k++) out.push(...bfs(A, wps[k - 1], wps[k]).slice(1));
  return out;
}
function routePoints(nodes, st) {
  const pts = [nodeXY(nodes[0], st)];
  for (let k = 1; k < nodes.length; k++) {
    const a = nodes[k - 1], b = nodes[k];
    if (IS_SBI(a) && IS_SBI(b)) { pts.push([NODES[a].x, BUS_Y], [NODES[b].x, BUS_Y]); }
    pts.push(nodeXY(b, st));
  }
  return pts;
}
function linkBetween(a, b) { return LINKS.find(L => !L.logical && ((L.a === a && L.b === b) || (L.a === b && L.b === a))); }

/* ---------- map render */
function renderMap(animate) {
  const i = P.idx, st = stateAt(i), step = FLAT[i];
  layoutLinks(st);
  const [ux, uy] = UE_POS[st.uePos]; nodeEls.UE.g.style.transform = `translate(${ux}px,${uy}px)`;
  nodeEls.UE.sb.textContent = st.rrc.startsWith("RRC_") ? st.rrc.replace("RRC_", "RRC ").toLowerCase() : "phone + USIM";
  linkEls.Uu1.path.classList.toggle("standby", st.serving !== "gNB1");
  linkEls.Uu2.path.classList.toggle("standby", st.serving !== "gNB2");
  // reset
  Object.values(nodeEls).forEach(o => { o.g.classList.remove("from", "to"); o.rect.style.filter = ""; o.rect.style.stroke = o.stroke; });
  Object.values(linkEls).forEach(o => { o.path.classList.remove("hot"); o.path.style.stroke = ""; });
  Object.values(stubs).forEach(o => { o.line.classList.remove("hot"); o.line.style.stroke = ""; });
  let route = [];
  if (step) {
    const col = PROTO[step.p].color;
    route = routeNodes(step, st);
    for (let k = 1; k < route.length; k++) {
      const a = route[k - 1], b = route[k];
      if (IS_SBI(a) && IS_SBI(b)) [a, b].forEach(n => { stubs[n].line.classList.add("hot"); stubs[n].line.style.stroke = col; });
      else { const L = linkBetween(a, b); if (L) { linkEls[L.id].path.classList.add("hot"); linkEls[L.id].path.style.stroke = col; } }
    }
    if (step.i === "N1") { linkEls.N1.path.classList.add("hot"); linkEls.N1.path.style.stroke = col; }
    nodeEls[step.f].g.classList.add("from"); nodeEls[step.t].g.classList.add("to");
    nodeEls[step.t].rect.style.filter = "url(#glow)";
  }
  applyLayers(route);
  renderSubtitle();
  return step && animate ? animateDot(step, routePoints(route, st)) : (gFx.innerHTML = "", Promise.resolve());
}
function applyLayers(route) {
  const cp = $("#lyCP").checked, up = $("#lyUP").checked;
  Object.values(linkEls).forEach(o => {
    const show = o.plane === "both" ? (cp || up) : o.plane === "up" ? up : cp;
    [o.path, o.hit, o.g].forEach(e => e.style.display = show ? "" : "none");
  });
  Object.values(stubs).forEach(o => { o.line.style.display = cp ? "" : "none"; o.g.style.display = cp ? "" : "none"; });
  gBus.querySelector(".bus").style.display = cp ? "" : "none";
  // isolate
  const iso = P.iso && P.sel;
  const keepN = new Set(), keepL = new Set(); let keepStub = false;
  if (iso && P.sel.node) {
    const n = P.sel.node; keepN.add(n);
    LINKS.forEach(L => { if (L.a === n || L.b === n) { keepL.add(L.id); keepN.add(L.a); keepN.add(L.b); } });
    if (IS_SBI(n)) { keepStub = true; SBI_NODES.forEach(x => keepN.add(x)); }
  }
  if (iso && P.sel.iface) {
    const f = P.sel.iface;
    if (f === "SBI") { keepStub = true; SBI_NODES.forEach(x => keepN.add(x)); }
    LINKS.forEach(L => { if (L.iface === f) { keepL.add(L.id); keepN.add(L.a); keepN.add(L.b); } });
  }
  Object.entries(nodeEls).forEach(([id, o]) => { o.g.classList.toggle("dim", !!iso && !keepN.has(id)); o.g.classList.toggle("sel", !!P.sel && P.sel.node === id); });
  Object.entries(linkEls).forEach(([id, o]) => [o.path, o.g].forEach(e => e.classList.toggle("dim", !!iso && !keepL.has(id))));
  Object.values(stubs).forEach(o => [o.line, o.g].forEach(e => e.classList.toggle("dim", !!iso && !keepStub)));
  gBus.querySelector(".bus").classList.toggle("dim", !!iso && !keepStub);
}
["lyCP", "lyUP"].forEach(id => $("#" + id).onchange = () => renderMap(false));
$("#lyIso").onchange = e => { P.iso = e.target.checked; renderMap(false); };
$("#lyCC").onchange = e => { P.cc = e.target.checked; renderSubtitle(); };

function animateDot(step, pts) {
  gFx.innerHTML = "";
  const col = PROTO[step.p].color;
  const dot = el("circle", { r: 8, fill: col, filter: "url(#glow)" }, gFx);
  const lab = el("g", {}, gFx);
  const name = step.m.length > 42 ? step.m.slice(0, 40) + "…" : step.m;
  const lw = name.length * 6.7 + 16;
  el("rect", { x: -lw / 2, y: -30, width: lw, height: 20, rx: 5, fill: "#0b1016", stroke: col }, lab);
  const lt = el("text", { y: -16, "text-anchor": "middle", fill: col, "font-size": 11.5, "font-family": "IBM Plex Mono, monospace" }, lab); lt.textContent = name;
  const seg = []; let total = 0;
  for (let k = 1; k < pts.length; k++) { const d = Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]); seg.push(d); total += d; }
  const dur = reduceMotion ? 1 : Math.max(700, Math.min(2600, total * 2.2)) / P.speed;
  const tok = P.token;
  return new Promise(res => {
    const t0 = performance.now();
    const place = f => {
      let d = f * total, k = 0; while (k < seg.length - 1 && d > seg[k]) { d -= seg[k]; k++; }
      const a = pts[k], b = pts[k + 1] || a, u = seg[k] ? Math.min(1, d / seg[k]) : 1;
      const x = a[0] + (b[0] - a[0]) * u, y = a[1] + (b[1] - a[1]) * u;
      dot.setAttribute("cx", x); dot.setAttribute("cy", y);
      lab.setAttribute("transform", `translate(${Math.min(1200 - lw / 2, Math.max(lw / 2 + 4, x))},${Math.max(34, y)})`);
    };
    const tick = now => {
      if (tok !== P.token) return res();
      const f = Math.min(1, (now - t0) / dur); place(f < .5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2);
      if (f < 1) requestAnimationFrame(tick); else res();
    };
    place(0); requestAnimationFrame(tick);
  });
}

function renderSubtitle() {
  const box = $("#subtitle"); box.hidden = !P.cc;
  const i = P.idx, s = FLAT[i];
  if (!s) {
    const p = P.scope === "all" ? null : PROCS.find(x => x.id === P.scope);
    box.innerHTML = p ? `<span class="meta">${esc(p.title)}</span>${esc(p.intro)} <em class="note">Press ▶ to start.</em>`
      : `<span class="meta">End-to-end journey · ${FLAT.length} messages in ${PROCS.length} chapters</span>Follow one phone from network start-up through power-on, registration, an internet session, a QoS upgrade, a handover, idle mode and paging, to deregistration. Press <b>▶</b> or use ← →. Click any box or interface label to learn what it is.`;
    return;
  }
  const c = PROCS[s.pi];
  box.innerHTML = `<span class="meta">${esc(c.title)} · ${esc(NODES[s.f].label)} → ${esc(NODES[s.t].label)} · <span style="color:${PROTO[s.p].color}">${esc(PROTO[s.p].label)}</span> over ${esc(s.i)}</span><b>${esc(s.m)}</b> · ${esc(s.n)}`;
}

/* ---------- side panel: selection info and state */
function select(sel) {
  P.sel = sel; renderInfo(); renderMap(false);
  if (P.tab !== "map") setTab("map");
}
function messagesWith(pred) { return FLAT.map((s, i) => [s, i]).filter(([s]) => pred(s)); }
function renderInfo() {
  const box = $("#info");
  const sel = P.sel;
  if (!sel) {
    const s = FLAT[P.idx];
    if (!s) { box.innerHTML = `<h2>How to use</h2><p class="note">• <b>Click any box</b> (network function) to see what it does and the services it offers.<br>• <b>Click an interface label</b> (N2, N3, N4…) to see its protocol stack and specs.<br>• <b>Press ▶</b> to watch messages travel. The <b>Call flow</b> tab shows the same messages as a sequence chart with full decodes.<br>• Search (top right) finds any NF, interface, message or field.</p>`; return; }
    box.innerHTML = `<h2>Current message · ${P.idx + 1}</h2>
      <div class="dhead"><h3>${esc(s.m)}</h3>
      <div class="route">${esc(NODES[s.f].label)} → ${esc(NODES[s.t].label)} <span class="pill" style="color:${PROTO[s.p].color}">${esc(PROTO[s.p].label)}</span> <button class="chip" data-if="${esc(s.i)}">${esc(s.i)}</button></div></div>
      ${s.c ? `<div class="carry">carried in: ${esc(s.c)}</div>` : ""}
      <p class="narr">${esc(s.n)}</p>
      <button class="btn primary" id="toDecode">Open full decode →</button>`;
    $("#toDecode").onclick = () => setTab("flow");
    box.querySelector("[data-if]").onclick = e => select({ iface: e.target.dataset.if });
    return;
  }
  if (sel.node) {
    const id = sel.node, N = NODES[id], F = NF_INFO[id] || {};
    const ifs = [...new Set(LINKS.filter(L => L.a === id || L.b === id).map(L => L.iface).concat(IS_SBI(id) ? ["SBI"] : []))];
    const msgs = messagesWith(s => s.f === id || s.t === id);
    const byProc = {}; msgs.forEach(([s, i]) => { (byProc[s.pi] = byProc[s.pi] || []).push(i); });
    box.innerHTML = `<div class="row" style="display:flex;justify-content:space-between;align-items:center"><h2>Network function</h2><button class="btn" id="clr">✕ Close</button></div>
      <div class="dhead"><h3>${esc(N.label)} · ${esc(F.full || "")}</h3><p class="narr" style="margin:0">${esc(F.role || "")}</p></div>
      ${F.twin ? `<div class="twinnote">${esc(F.twin)}</div>` : ""}
      <div><h2 style="margin-bottom:6px">Capabilities</h2><ul class="caps">${(F.caps || []).map(c => `<li>${esc(c)}</li>`).join("")}</ul></div>
      ${F.analogy ? `<div class="analogy">Analogy: ${esc(F.analogy)}</div>` : ""}
      ${F.services ? `<div style="display:grid;gap:8px"><h2>SBI services${F.spec ? ` · ${esc(F.spec)}` : ""}</h2>${Object.entries(F.services).map(([k, ops]) => `<div class="svc"><b>${esc(k)}</b><div class="chips">${ops.map(o => { const api = APIS.find(a => a.svc === k && a.op.startsWith(o)); return `<button class="chip" ${api ? `data-api="${api.id}" title="Open in API builder"` : "disabled style='opacity:.7;cursor:default'"}>${esc(o)}${api ? " ↗" : ""}</button>`; }).join("")}</div></div>`).join("")}</div>` : ""}
      <div><h2 style="margin-bottom:6px">Interfaces</h2><div class="chips">${ifs.map(f => `<button class="chip" data-if="${f}">${f}</button>`).join("")}</div></div>
      <div><h2 style="margin-bottom:6px">Appears in (${msgs.length} messages)</h2><div class="chips">${Object.entries(byProc).map(([pi, arr]) => `<button class="chip" data-go="${arr[0]}">${esc(PROCS[pi].short)} · ${arr.length}</button>`).join("")}</div></div>`;
  } else if (sel.iface) {
    const F = IFACES[sel.iface];
    const msgs = messagesWith(s => s.i === sel.iface || (sel.iface === "SBI" && s.p === "SBI" && s.i === "SBI"));
    box.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center"><h2>Interface</h2><button class="btn" id="clr">✕ Close</button></div>
      <div class="dhead"><h3>${esc(F.name)}</h3><div class="route">${esc(F.between)} · ${esc(F.plane)}</div></div>
      <p class="narr" style="margin:0">${esc(F.about)}</p>
      ${F.stacks.map(st => `<div class="stack"><h2 style="margin-bottom:2px">${esc(st.title)}</h2>${st.layers.map(l => `<div>${esc(l)}</div>`).join("")}</div>`).join("")}
      <div><h2 style="margin-bottom:6px">3GPP specifications</h2><ul class="caps">${F.specs.map(s => `<li>${esc(s)}</li>`).join("")}</ul></div>
      <div><h2 style="margin-bottom:6px">Messages on this interface (${msgs.length})</h2><div class="chips">${msgs.slice(0, 40).map(([s, i]) => `<button class="chip" data-go="${i}" title="${esc(PROCS[s.pi].title)}">${esc(s.m.length > 34 ? s.m.slice(0, 32) + "…" : s.m)}</button>`).join("")}</div></div>`;
  }
  const c = $("#clr"); if (c) c.onclick = () => { P.sel = null; renderInfo(); renderMap(false); };
  $$("[data-if]", box).forEach(b => b.onclick = () => select({ iface: b.dataset.if }));
  $$("[data-go]", box).forEach(b => b.onclick = () => { P.sel = null; jumpTo(+b.dataset.go); });
  $$("[data-api]", box).forEach(b => b.onclick = () => { setApi(b.dataset.api); setTab("api"); });
}
function renderState() {
  const i = P.idx, st = stateAt(i), prev = i < 0 ? st : BEFORE[i];
  $("#state").innerHTML = STATE_LABELS.map(([k, l]) => `<dt>${l}</dt><dd class="${st[k] !== prev[k] ? "chg" : ""}">${esc(st[k])}</dd>`).join("");
}

/* ================================================================ sequence chart */
const ROW = 34, BAND = 36, LEFT = 46;
let rowY = {};
function renderChart() {
  if (P.tab !== "flow") return;
  const [a, b] = range();
  const steps = FLAT.slice(a, b + 1);
  const lanes = LANE_ORDER.filter(n => steps.some(s => s.f === n || s.t === n));
  const wrap = $("#chartscroll"), W = Math.max(wrap.clientWidth - 4, LEFT + 60 + lanes.length * 78);
  const lx = {}; lanes.forEach((n, k) => lx[n] = LEFT + 50 + k * (W - LEFT - 100) / Math.max(1, lanes.length - 1));
  // header
  $("#lanehead").innerHTML = lanes.map(n => `<span style="left:${lx[n]}px;border-color:${KIND[NODES[n].kind][1]}66">${esc(NODES[n].label)}</span>`).join("");
  wrap.onscroll = () => $("#lanehead").scrollLeft = wrap.scrollLeft;
  $("#lanehead").style.width = "100%";
  // rows
  rowY = {}; let y = 12; const rows = [];
  steps.forEach((s, k) => {
    const gi = a + k;
    if (P.scope === "all" && (k === 0 || steps[k - 1].pi !== s.pi)) { rows.push({ band: PROCS[s.pi], y }); y += BAND; }
    rows.push({ s, gi, y }); rowY[gi] = y; y += ROW;
  });
  const H = y + 16;
  const c = $("#chart"); c.setAttribute("width", W); c.setAttribute("height", H); c.innerHTML = "";
  // inner header spacer so lanehead matches scroll width
  $("#lanehead").innerHTML = `<div style="position:relative;width:${W}px;height:40px">${$("#lanehead").innerHTML}</div>`;
  const dfs = el("defs", {}, c);
  Object.entries(PROTO).forEach(([k, p]) => {
    const m = el("marker", { id: "ah-" + k, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, dfs);
    el("path", { d: "M0,0 L10,5 L0,10 z", fill: p.color }, m);
  });
  lanes.forEach(n => el("line", { x1: lx[n], y1: 0, x2: lx[n], y2: H, stroke: "#243140", "stroke-width": 1.5, "stroke-dasharray": "3 4" }, c));
  rows.forEach(r => {
    if (r.band) {
      el("rect", { x: 0, y: r.y + 4, width: W, height: BAND - 8, fill: "#111922" }, c);
      const t = el("text", { x: 12, y: r.y + 23, fill: "#e7edf2", "font-size": 13, "font-weight": 700, "font-family": "Archivo, sans-serif" }, c); t.textContent = r.band.title;
      return;
    }
    const s = r.s, col = PROTO[s.p].color, g = el("g", { class: "row" + (r.gi === P.idx ? " cur" : ""), "data-i": r.gi }, c);
    el("rect", { class: "rbg", x: 0, y: r.y, width: W, height: ROW, fill: "transparent" }, g);
    const n = el("text", { x: 10, y: r.y + 21, fill: "#64768a", "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, g); n.textContent = r.gi + 1;
    const x1 = lx[s.f], x2 = lx[s.t], yy = r.y + 24;
    el("line", { x1, y1: yy, x2: x2 + (x2 > x1 ? -2 : 2), y2: yy, stroke: col, "stroke-width": 2, "marker-end": `url(#ah-${s.p})`, "stroke-dasharray": s.p === "UP" ? "6 4" : "" }, g);
    const mid = (x1 + x2) / 2, span = Math.abs(x2 - x1);
    let label = s.m; const maxc = Math.max(14, Math.floor((Math.max(span, 220)) / 6.6));
    if (label.length > maxc) label = label.slice(0, maxc - 1) + "…";
    const tx = el("text", { x: span < 220 ? Math.min(x1, x2) + 4 : mid, y: yy - 6, "text-anchor": span < 220 ? "start" : "middle", fill: col, "font-size": 11.5 }, g); tx.textContent = label;
    const tt = el("title", {}, g); tt.textContent = `${s.m}  (${PROTO[s.p].label} over ${s.i})`;
    g.addEventListener("click", () => jumpTo(r.gi));
  });
  scrollChart(true);
}
function scrollChart(instant) {
  if (P.tab !== "flow") return;
  $$("#chart .row").forEach(g => g.classList.toggle("cur", +g.dataset.i === P.idx));
  const y = rowY[P.idx]; if (y == null) return;
  const w = $("#chartscroll"), far = Math.abs(y - w.scrollTop) > 1200;
  if (y < w.scrollTop + 20 || y > w.scrollTop + w.clientHeight - 80) w.scrollTo({ top: y - w.clientHeight / 3, behavior: instant || far || reduceMotion ? "auto" : "smooth" });
}
$("#protolegend").innerHTML = Object.values(PROTO).map(p => `<span><i style="background:${p.color}"></i>${esc(p.label)}</span>`).join("");

/* ---------- decode panel */
let decodeFilter = "";
function treeHTML(nodes, q) {
  const hl = s => { s = esc(s); if (!q) return s; const re = new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"); return s.replace(re, "<mark>$1</mark>"); };
  const match = n => q && ((n.n + " " + (n.v || "") + " " + (n.d || "")).toLowerCase().includes(q.toLowerCase()) || (n.c || []).some(match));
  return nodes.map(n => {
    const head = `<span class="k">${hl(n.n)}</span>${n.v ? `: <span class="v">${hl(n.v)}</span>` : ""}${n.d ? `<span class="d">${hl(n.d)}</span>` : ""}`;
    if (n.c && n.c.length) return `<details ${!q || match(n) ? "open" : ""}><summary>${head}</summary>${treeHTML(n.c, q)}</details>`;
    return `<div class="leaf">${head}</div>`;
  }).join("");
}
function renderDecode() {
  if (P.tab !== "flow") return;
  const box = $("#decode"), s = FLAT[P.idx];
  if (!s) {
    const p = P.scope === "all" ? null : PROCS.find(x => x.id === P.scope);
    box.innerHTML = `<h2>Message decode</h2><p class="narr">${p ? esc(p.intro) : "Click any arrow in the sequence chart, or press ▶, to decode a message field by field. The colours show protocols; the dashed lines are user data."}</p>`;
    return;
  }
  box.innerHTML = `<h2>Message ${P.idx + 1} · ${esc(PROCS[s.pi].short)}</h2>
    <div class="dhead"><h3>${esc(s.m)}</h3>
      <div class="route">${esc(NODES[s.f].label)} → ${esc(NODES[s.t].label)} <span class="pill" style="color:${PROTO[s.p].color}">${esc(PROTO[s.p].label)}</span> <button class="chip" id="dIf">${esc(s.i)} ↗</button></div></div>
    ${s.c ? `<div class="carry">carried in: ${esc(s.c)}</div>` : ""}
    <p class="narr" style="margin:0">${esc(s.n)}</p>
    <div class="dtools"><input id="dq" type="search" placeholder="Find IE…" value="${esc(decodeFilter)}" aria-label="Find information element"><button class="btn" id="dOpen">Expand all</button><button class="btn" id="dClose">Collapse</button></div>
    <div class="tree" id="tree">${treeHTML(s.d || [], decodeFilter)}</div>`;
  $("#dIf").onclick = () => select({ iface: s.i });
  $("#dq").oninput = e => { decodeFilter = e.target.value; $("#tree").innerHTML = treeHTML(s.d || [], decodeFilter); };
  $("#dOpen").onclick = () => $$("#tree details").forEach(d => d.open = true);
  $("#dClose").onclick = () => $$("#tree details").forEach(d => d.open = false);
}

/* ================================================================ player */
const scopeSel = $("#scope");
scopeSel.add(new Option("Full end-to-end journey", "all"));
PROCS.forEach(p => scopeSel.add(new Option(p.title, p.id)));
scopeSel.onchange = () => { stop(); P.scope = scopeSel.value; P.idx = -1; refresh(false); if (P.tab === "flow") renderChart(); };
$("#chapters").innerHTML = PROCS.map(p => `<button class="chip" data-ch="${p.id}">${esc(p.short)}</button>`).join("");
$$("#chapters .chip").forEach(b => b.onclick = () => {
  stop();
  if (P.scope !== "all") { P.scope = b.dataset.ch; scopeSel.value = P.scope; P.idx = -1; refresh(false); if (P.tab === "flow") renderChart(); return; }
  jumpTo(PROC_RANGE[b.dataset.ch][0]);
});
$("#speed").onchange = e => P.speed = +e.target.value;
const synth = window.speechSynthesis;
if (!synth) { $("#speak").disabled = true; $("#speak").parentElement.title = "Speech is not supported in this browser"; }
$("#speak").onchange = e => { P.speak = e.target.checked; if (!P.speak && synth) synth.cancel(); };

function speak(text) {
  if (!P.speak || !synth) return Promise.resolve();
  synth.cancel();
  return new Promise(res => {
    const u = new SpeechSynthesisUtterance(text.replace(/→/g, " to ").replace(/·/g, ","));
    u.rate = Math.min(1.6, 0.95 * P.speed); u.lang = "en-GB";
    let done = false; const fin = () => { if (!done) { done = true; res(); } };
    u.onend = fin; u.onerror = fin; setTimeout(fin, 4000 + text.length * 90 / P.speed);
    synth.speak(u);
  });
}

function refresh(animate) {
  const [a, b] = range();
  $("#prog").textContent = P.idx < a ? `Ready · ${b - a + 1} messages` : `Message ${P.idx - a + 1} / ${b - a + 1}`;
  const cur = FLAT[P.idx];
  $$("#chapters .chip").forEach(c => c.setAttribute("aria-current", cur ? c.dataset.ch === cur.proc : c.dataset.ch === P.scope));
  renderState(); if (!P.sel) renderInfo();
  scrollChart(); renderDecode();
  return renderMap(animate);
}
function jumpTo(i, fromPlay) {
  if (!fromPlay) stop();
  const [a, b] = range();
  if (i !== -1 && (i < a || i > b)) { P.scope = "all"; scopeSel.value = "all"; if (P.tab === "flow") { P.idx = i; renderChart(); } }
  P.idx = i; P.token++;
  const anim = refresh(true);
  const s = FLAT[i];
  return Promise.all([anim, fromPlay && s ? speak(`${s.m}. ${s.n}`) : (P.speak && s ? speak(`${s.m}. ${s.n}`) : Promise.resolve())]);
}
async function play() {
  if (P.playing) return;
  P.playing = true; setPlayIcon();
  const [a, b] = range(); if (P.idx >= b || P.idx < a - 1) P.idx = a - 1;
  while (P.playing) {
    const [, end] = range(), next = P.idx + 1;
    if (next > end) break;
    await jumpTo(next, true);
    if (!P.playing) break;
    const s = FLAT[next];
    const dwell = P.speak ? 350 : Math.max(1800, Math.min(9000, s.n.length * 38)) / P.speed;
    const t0 = performance.now();
    while (P.playing && performance.now() - t0 < dwell) await sleep(100);
  }
  P.playing = false; setPlayIcon();
}
function stop() { P.playing = false; setPlayIcon(); if (synth) synth.cancel(); }
function setPlayIcon() {
  $("#playIcon").innerHTML = P.playing ? '<path d="M3 2h4v12H3zM9 2h4v12H9z"/>' : '<path d="M4 2l10 6-10 6z"/>';
  $("#bPlay").setAttribute("aria-label", P.playing ? "Pause" : "Play");
}
$("#bPlay").onclick = () => P.playing ? stop() : play();
$("#bNext").onclick = () => { const [, b] = range(); if (P.idx < b) jumpTo(P.idx + 1); };
$("#bPrev").onclick = () => { const [a] = range(); if (P.idx >= a) jumpTo(P.idx - 1 < a ? -1 : P.idx - 1); };
document.addEventListener("keydown", e => {
  if (e.target.matches("input, select, textarea") || !(P.tab === "map" || P.tab === "flow")) return;
  if (e.key === "ArrowRight") { e.preventDefault(); $("#bNext").click(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); $("#bPrev").click(); }
  else if (e.key === " " && !e.target.closest("button, [role=button]")) { e.preventDefault(); $("#bPlay").click(); }
});

/* ================================================================ API builder */
const AV = { supi: ID.supi, suci: ID.suci, mcc: "001", mnc: "01", dnn: "internet", sst: "1", fiveqi: "9", ip: ID.ip, nftype: "SMF", nfid: "8d1f2a90-5c1e-4b7e-9a63-2f4c1d0e7b11" };
const FIELDS = [["supi", "SUPI"], ["suci", "SUCI"], ["mcc", "MCC"], ["mnc", "MNC"], ["dnn", "DNN"], ["sst", "SST (1 eMBB · 2 URLLC · 3 MIoT)"], ["fiveqi", "Default 5QI"], ["ip", "UE IPv4"], ["nftype", "NF type (register)"], ["nfid", "NF instance ID"]];
let apiCur = APIS[0].id;
{
  const groups = {}; APIS.forEach(a => (groups[a.nf] = groups[a.nf] || []).push(a));
  $("#apilist").innerHTML = Object.entries(groups).map(([nf, arr]) => `<h2>${esc(nf)}</h2>` + arr.map(a => `<button data-a="${a.id}"><b>${esc(a.svc)}</b><small>${esc(a.op)} · ${a.method}</small></button>`).join("")).join("");
  $$("#apilist button").forEach(b => b.onclick = () => setApi(b.dataset.a));
  $("#apifields").innerHTML = FIELDS.map(([k, l]) => k === "sst" ? `<label>${l}<select data-f="sst"><option>1</option><option>2</option><option>3</option><option>4</option></select></label>`
    : k === "nftype" ? `<label>${l}<select data-f="nftype"><option>SMF</option><option>AMF</option></select></label>` : `<label>${l}<input data-f="${k}" value="${esc(AV[k])}"></label>`).join("");
  $$("#apifields [data-f]").forEach(i => { i.value = AV[i.dataset.f]; i.oninput = i.onchange = () => { AV[i.dataset.f] = i.value.trim(); renderApi(); }; });
}
function setApi(id) { apiCur = id; renderApi(); }
const HOST = { NRF: "nrf.5gc", AUSF: "ausf.5gc", UDM: "udm.5gc", SMF: "smf1.5gc", PCF: "pcf.5gc", AMF: "amf1.5gc", NSSF: "nssf.5gc" };
function fillPath(p) {
  return p.replace("{nfInstanceId}", AV.nfid).replace("{supiOrSuci}", AV.suci).replace("{ueId}", AV.supi).replace("{supi}", AV.supi).replace("{ueContextId}", AV.supi)
    .replace("{authCtxId}", "a1b2c3").replace("{dnn}", AV.dnn).replace(/\{sst\}/g, AV.sst).replace("{mcc}", AV.mcc).replace("{mnc}", AV.mnc);
}
function jsonHL(o) {
  return esc(JSON.stringify(o, null, 2))
    .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="key">$1</span>$2')
    .replace(/:\s(&quot;.*?&quot;)/g, ': <span class="s">$1</span>')
    .replace(/:\s(-?\d+\.?\d*|true|false|null)/g, ': <span class="n">$1</span>');
}
function renderApi() {
  $$("#apilist button").forEach(b => b.setAttribute("aria-current", b.dataset.a === apiCur));
  const a = APIS.find(x => x.id === apiCur), path = fillPath(a.path), req = a.req(AV), res = a.res(AV);
  const url = `https://${HOST[a.nf]}${path}`;
  const reqText = `<span class="m">${a.method}</span> ${esc(path)} HTTP/2\n<span class="c">:authority: ${HOST[a.nf]}\n:scheme: https\nauthorization: Bearer &lt;OAuth2 token from Nnrf_AccessToken&gt;${req ? "\ncontent-type: application/json" : ""}\naccept: application/json</span>${req ? "\n\n" + jsonHL(req) : ""}`;
  const resText = `<span class="m">HTTP/2 ${esc(res.status)}</span>${res.headers ? "\n<span class=\"c\">" + Object.entries(res.headers).map(([k, v]) => `${esc(k.toLowerCase())}: ${esc(v)}`).join("\n") + "</span>" : ""}\n<span class="c">content-type: application/json</span>\n\n${jsonHL(res.body)}`;
  const curl = `curl --http2 -X ${a.method} '${url}' \\\n  -H 'Authorization: Bearer $TOKEN' -H 'Accept: application/json'${req ? ` \\\n  -H 'Content-Type: application/json' \\\n  -d '${JSON.stringify(req)}'` : ""}`;
  $("#apiout").innerHTML = `<div style="display:grid;gap:4px"><h2>${esc(a.svc)}_${esc(a.op)}</h2><div class="dhead"><h3>${esc(a.nf)} · ${esc(a.op)}</h3></div><p class="note" style="margin:0">${esc(a.note)} <span class="mono">(${esc(a.spec)})</span></p></div>
    <div><div class="codehead"><h2>Request</h2><button class="btn" id="cpCurl">Copy as curl</button></div><pre class="code">${reqText}</pre></div>
    <div><h2 style="margin-bottom:6px">Response</h2><pre class="code">${resText}</pre></div>
    <p class="note">The flow these calls belong to is in <button class="chip" id="apiFlow">Call flow ↗</button>. Real 5G cores such as open-source free5GC or Open5GS expose these same endpoints.</p>`;
  $("#cpCurl").onclick = e => { (navigator.clipboard ? navigator.clipboard.writeText(curl) : Promise.reject()).then(() => e.target.textContent = "Copied ✓", () => e.target.textContent = "Copy failed"); setTimeout(() => e.target.textContent = "Copy as curl", 1600); };
  $("#apiFlow").onclick = () => {
    const key = a.svc + "_" + a.op.split(" ")[0];
    let i = FLAT.findIndex(s => s.m.includes(key)); if (i < 0) i = FLAT.findIndex(s => s.m.includes(a.svc));
    setTab("flow"); if (i >= 0) jumpTo(i);
  };
}

/* ================================================================ air interface */
const CQI = [[2, 78, .1523], [2, 193, .3770], [2, 449, .8770], [4, 378, 1.4766], [4, 490, 1.9141], [4, 616, 2.4063], [6, 466, 2.7305], [6, 567, 3.3223], [6, 666, 3.9023], [6, 772, 4.5234], [6, 873, 5.1152], [8, 711, 5.5547], [8, 797, 6.2266], [8, 885, 6.9141], [8, 948, 7.4063]];
const GAP = 3.0, OH = 0.14, BLER = 0.1;
const CQI_THR = CQI.map(c => 10 * Math.log10(Math.pow(2, c[2]) - 1) + GAP);
const MODN = { 2: "QPSK", 4: "16QAM", 6: "64QAM", 8: "256QAM" };
const PRB_TABLE = {   // TS 38.101-1 Table 5.3.2-1 (FR1) and 38.101-2 Table 5.3.2-1 (FR2, 120 kHz)
  15: { 5: 25, 10: 52, 15: 79, 20: 106, 25: 133, 30: 160, 40: 216, 50: 270 },
  30: { 5: 11, 10: 24, 15: 38, 20: 51, 25: 65, 30: 78, 40: 106, 50: 133, 60: 162, 70: 189, 80: 217, 90: 245, 100: 273 },
  60: { 10: 11, 15: 18, 20: 24, 25: 31, 30: 38, 40: 51, 50: 65, 60: 79, 70: 93, 80: 107, 90: 121, 100: 135 },
  120: { 50: 32, 100: 66, 200: 132, 400: 264 },
};
const aScs = $("#aScs"), aBw = $("#aBw");
[15, 30, 60, 120].forEach(s => aScs.add(new Option(`${s} kHz · μ = ${Math.log2(s / 15)} · slot ${1 / (s / 15)} ms${s === 120 ? " (FR2)" : ""}`, s)));
aScs.value = PRB_TABLE[twin.scs] ? twin.scs : 30;
function fillBw() {
  const t = PRB_TABLE[+aScs.value], keep = +aBw.value || twin.bw; aBw.innerHTML = "";
  Object.keys(t).forEach(bw => aBw.add(new Option(`${bw} MHz · ${t[bw]} PRB`, bw)));
  aBw.value = t[keep] ? keep : Object.keys(t).slice(-1)[0];
}
fillBw();
aScs.onchange = () => { fillBw(); drawAir(); };
["aSinr", "aLay", "aUsr"].forEach(id => $("#" + id).oninput = drawAir); aBw.onchange = drawAir;
$("#cqitable").innerHTML = `<thead><tr><th>CQI</th><th>Modulation</th><th>Code rate ×1024</th><th>bit / RE</th><th>Min SINR (dB)</th></tr></thead><tbody>` +
  CQI.map((c, k) => `<tr data-k="${k}"><td>${k + 1}</td><td>${MODN[c[0]]}</td><td>${c[1]}</td><td>${c[2].toFixed(4)}</td><td>${CQI_THR[k].toFixed(1)}</td></tr>`).join("") + "</tbody>";
$("#cqibar").innerHTML = CQI.map((c, k) => `<div title="CQI ${k + 1}: ${MODN[c[0]]}, ≥ ${CQI_THR[k].toFixed(1)} dB">${k + 1}</div>`).join("");

function drawAir() {
  if (P.tab !== "air") return;
  const sinr = +$("#aSinr").value, scs = +aScs.value, mu = Math.log2(scs / 15), bw = +aBw.value, prb = PRB_TABLE[scs][bw];
  const lay = +$("#aLay").value, usr = +$("#aUsr").value;
  $("#oSinr").textContent = sinr.toFixed(1) + " dB"; $("#oLay").textContent = lay; $("#oUsr").textContent = usr;
  let cqi = 0; CQI_THR.forEach((t, k) => { if (sinr >= t) cqi = k + 1; });
  const c = cqi ? CQI[cqi - 1] : null, eff = c ? c[2] : 0;
  const slotsPerS = 1000 * Math.pow(2, mu);
  const cell = lay * prb * 12 * 14 * slotsPerS * eff * (1 - OH) * (1 - BLER) / 1e6;
  const ue = cell / usr;
  const shannon = Math.log2(1 + Math.pow(10, (sinr - GAP) / 10));
  $("#airbig").innerHTML = [
    [cqi ? cqi : "out", "CQI " + (cqi ? "" : "· below CQI 1 → outage")],
    [c ? MODN[c[0]] : "—", c ? `code rate ${c[1]}/1024` : "no transmission"],
    [eff.toFixed(2), "bit per resource element"],
    [ue >= 100 ? ue.toFixed(0) : ue.toFixed(1), `Mbps per user (${usr} sharing)`],
    [cell >= 100 ? cell.toFixed(0) : cell.toFixed(1), "Mbps cell throughput"],
    [prb, `PRBs · ${(prb * 12 * scs / 1000).toFixed(1)} MHz occupied`],
  ].map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join("");
  $$("#cqibar div").forEach((d, k) => { d.className = k + 1 === cqi ? "on" : k + 1 < cqi ? "le" : ""; });
  $$("#cqitable tbody tr").forEach((r, k) => r.className = k + 1 === cqi ? "on" : "");
  // frame structure
  const slots = Math.pow(2, mu);
  $("#frame").innerHTML = `<h2>Frame structure (μ = ${mu})</h2>
    <span>1 radio frame = 10 ms = 10 subframes</span><div class="bar">${Array.from({ length: 10 }, (_, k) => `<div class="${k === 0 ? "h" : ""}">${k}</div>`).join("")}</div>
    <span>1 subframe = 1 ms = ${slots} slot${slots > 1 ? "s" : ""} of ${(1 / slots).toFixed(3).replace(/0+$/, "").replace(/\.$/, "")} ms</span><div class="bar">${Array.from({ length: slots }, (_, k) => `<div class="${k === 0 ? "h" : ""}">slot ${k}</div>`).join("")}</div>
    <span>1 slot = 14 OFDM symbols (normal CP) · symbol ≈ ${(1e6 / (14 * slotsPerS)).toFixed(1)} µs incl. CP</span>
    <div class="bar">${Array.from({ length: 14 }, (_, k) => `<div class="${k < 2 ? "ctl" : k === 2 ? "dm" : "h"}">${k}</div>`).join("")}</div>
    <span style="display:flex;gap:12px;flex-wrap:wrap"><span><i style="display:inline-block;width:10px;height:10px;background:#f5c64a55"></i> PDCCH (DCI)</span><span><i style="display:inline-block;width:10px;height:10px;background:#e888b355"></i> DMRS</span><span><i style="display:inline-block;width:10px;height:10px;background:#6fb1ff55"></i> PDSCH data</span></span>
    <span>Scheduler decisions per second: <b style="color:var(--ink)">${slotsPerS.toLocaleString()}</b> · one PRB = 12 × ${scs} kHz = ${(12 * scs / 1000).toFixed(2)} MHz</span>
    <span>Shannon bound at this SINR (with ${GAP} dB gap): ${shannon.toFixed(2)} bit/RE. CQI ${cqi || "–"} gives ${eff.toFixed(2)}.</span>`;
  drawConst(c ? c[0] : 2, sinr);
}
function drawConst(bits, sinr) {
  const cv = $("#const"), g = cv.getContext("2d"), W = cv.width, H = cv.height;
  g.fillStyle = "#080d12"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#243140"; g.lineWidth = 1; g.beginPath(); g.moveTo(W / 2, 8); g.lineTo(W / 2, H - 8); g.moveTo(8, H / 2); g.lineTo(W - 8, H / 2); g.stroke();
  const m = Math.pow(2, bits / 2), lv = []; for (let k = 0; k < m; k++) lv.push(2 * k - m + 1);
  const norm = Math.sqrt(2 * (m * m - 1) / 3), sc = (W / 2 - 22) / ((m - 1) / norm || 1);
  const sigma = Math.sqrt(Math.pow(10, -sinr / 10) / 2);
  const gauss = () => { let u = 0, v = 0; while (!u) u = Math.random(); v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const n = Math.min(4000, 60 * m * m);
  g.fillStyle = "#6fb1ff55";
  for (let k = 0; k < n; k++) {
    const i = lv[(Math.random() * m) | 0] / norm + sigma * gauss(), q = lv[(Math.random() * m) | 0] / norm + sigma * gauss();
    g.fillRect(W / 2 + i * sc - 1, H / 2 - q * sc - 1, 2, 2);
  }
  g.fillStyle = "#f5c64a";
  lv.forEach(a => lv.forEach(b => { g.beginPath(); g.arc(W / 2 + a / norm * sc, H / 2 - b / norm * sc, m > 8 ? 1.6 : 3, 0, 7); g.fill(); }));
  $("#constnote").textContent = `${MODN[bits]} (${bits} bits/symbol) at ${sinr} dB SINR. Yellow dots are ideal points and blue dots are received symbols. When the clouds overlap, the link adaptation drops to a lower CQI.`;
}

/* ================================================================ glossary */
function renderGloss(q) {
  q = (q || "").toLowerCase();
  $("#glist").innerHTML = GLOSSARY.filter(([t, d]) => !q || (t + " " + d).toLowerCase().includes(q)).map(([t, d]) => `<div><b>${esc(t)}</b><p>${esc(d)}</p></div>`).join("") || `<p class="note">No term matches.</p>`;
}
$("#gq").oninput = e => renderGloss(e.target.value); renderGloss("");

/* ================================================================ global search */
const INDEX = [];
Object.entries(NODES).forEach(([id, N]) => { if (id !== "gNB2") INDEX.push({ type: "NF", t: N.label + " · " + ((NF_INFO[id] || {}).full || ""), sub: (NF_INFO[id] || {}).role || "", go: () => select({ node: id }) }); });
Object.entries(IFACES).forEach(([k, F]) => INDEX.push({ type: "Interface", t: F.name, sub: F.between, go: () => select({ iface: k }) }));
FLAT.forEach((s, i) => {
  INDEX.push({ type: "Message", t: s.m, sub: `${PROCS[s.pi].short} · ${NODES[s.f].label} → ${NODES[s.t].label}`, go: () => { decodeFilter = ""; setTab("flow"); jumpTo(i); } });
  const walk = (ns, path) => (ns || []).forEach(n => { INDEX.push({ type: "IE", t: n.n + (n.v ? ": " + n.v : ""), sub: `${s.m} (#${i + 1})`, ie: n.n, go: () => { decodeFilter = n.n; setTab("flow"); jumpTo(i); } }); walk(n.c); });
  walk(s.d);
});
Object.values(NF_INFO).forEach(F => F.services && Object.entries(F.services).forEach(([svc, ops]) => ops.forEach(o => {
  const api = APIS.find(a => a.svc === svc && a.op.startsWith(o));
  INDEX.push({ type: "Service", t: `${svc}_${o}`, sub: api ? "open in API builder" : "SBI operation", go: () => { if (api) { setApi(api.id); setTab("api"); } else { const nf = Object.keys(NF_INFO).find(k => NF_INFO[k].services && NF_INFO[k].services[svc]); select({ node: nf }); } } });
})));
GLOSSARY.forEach(([t, d]) => INDEX.push({ type: "Term", t, sub: d, go: () => { setTab("gloss"); $("#gq").value = t; renderGloss(t); } }));
const qIn = $("#q"), resBox = $("#results"); let hits = [], hiIdx = 0;
qIn.oninput = () => {
  const q = qIn.value.trim().toLowerCase();
  if (q.length < 2) { resBox.hidden = true; return; }
  const words = q.split(/\s+/);
  const rank = { NF: 0, Interface: 1, Term: 2, Message: 3, Service: 4, IE: 5 };
  hits = INDEX.filter(x => words.every(w => (x.t + " " + x.sub).toLowerCase().includes(w)))
    .sort((a, b) => (a.t.toLowerCase().startsWith(q) ? 0 : 1) - (b.t.toLowerCase().startsWith(q) ? 0 : 1) || rank[a.type] - rank[b.type]).slice(0, 14);
  hiIdx = 0; drawHits();
};
function drawHits() {
  resBox.hidden = false;
  resBox.innerHTML = hits.length ? hits.map((h, k) => `<button data-k="${k}" class="${k === hiIdx ? "on" : ""}"><span class="tag">${h.type}</span><span>${esc(h.t)}</span><small>${esc(h.sub)}</small></button>`).join("") : `<p class="note" style="padding:8px 12px;margin:0">No matches</p>`;
  $$("button", resBox).forEach(b => b.onclick = () => choose(+b.dataset.k));
}
function choose(k) { const h = hits[k]; if (!h) return; resBox.hidden = true; qIn.blur(); h.go(); }
qIn.onkeydown = e => {
  if (resBox.hidden) return;
  if (e.key === "ArrowDown") { hiIdx = Math.min(hits.length - 1, hiIdx + 1); drawHits(); e.preventDefault(); }
  else if (e.key === "ArrowUp") { hiIdx = Math.max(0, hiIdx - 1); drawHits(); e.preventDefault(); }
  else if (e.key === "Enter") { choose(hiIdx); e.preventDefault(); }
  else if (e.key === "Escape") resBox.hidden = true;
};
document.addEventListener("click", e => { if (!e.target.closest(".search")) resBox.hidden = true; });

/* ================================================================ boot */
addEventListener("resize", () => { if (P.tab === "flow") renderChart(); });
renderApi();
const startTab = params.get("tab");
const startStep = +params.get("step");                 // deep link: ?step=25&tab=flow
if (startStep > 0 && startStep <= FLAT.length) P.idx = startStep - 1;
refresh(false);
if (startTab && $("#v-" + startTab)) setTab(startTab);
})();
