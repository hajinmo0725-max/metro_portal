// 4차 S4: 도식 노선도 화면 (권역 패널, 포탈 아이콘·목적지, 같은 권역 포탈 점선, 길찾기 경로 하이라이트, 지리 ↔ 도식 전환)
import { buildAdj, buildLabels, resolveQuery, routeClusters } from "./route.js";
import { fitTransform, labelStats, lerpPoint, offsetSegment, panelSequence, placeLabels, portalLinks, regionIndex, routeSteps, warpTargets } from "./schematic_core.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
const WARP = getComputedStyle(document.documentElement).getPropertyValue("--warp").trim() || "#8b3dff";
const BUNDLES = { strict: "kr_strict.json", tw_t12: "world_tw_t12.json" };
const W = 1000;
// 권역별 기본 확대 (수도권은 655역이라 처음부터 확대해서 도심을 보여 준다)
const DEFAULT_ZOOM = { seoul: 3 };

const sch = await (await fetch("data/schematic.json")).json();
let data, labels, adj, reg, links, rsKey;
const state = { region: sch.regions[0].id, view: "schematic", zoom: 1, steps: null, focus: null };
let els = null;          // 현재 패널의 SVG 요소와 좌표 (전환 애니메이션용)

function el(name, attrs = {}, parent = null) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

async function loadBundle(key) {
  rsKey = BUNDLES[key] ? key : "strict";
  data = await (await fetch(`data/${BUNDLES[rsKey]}`)).json();
  labels = buildLabels(data);
  adj = buildAdj(data, { warp: true });
  ({ reg } = regionIndex(sch, data));
  links = portalLinks(data, reg);
  $("sch-list").innerHTML = labels.map((l) => `<option value="${esc(l)}"></option>`).join("");
  $("sch-rs").value = rsKey;
}

function regionDef(id) { return sch.regions.find((r) => r.id === id); }

function drawTabs() {
  $("sch-tabs").innerHTML = sch.regions.map((r) => {
    const onRoute = state.steps && panelSequence(state.steps).includes(r.id);
    return `<button type="button" role="tab" data-r="${r.id}" aria-selected="${r.id === state.region}" class="${onRoute ? "on-route" : ""}">${esc(r.city)}</button>`;
  }).join("");
  $("sch-tabs").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => show(b.dataset.r)));
}

// 패널 좌표: 두 보기(도식 s·지리 g)를 같은 화면 상자에 각각 맞춘다
function screenCoords(r) {
  const ids = Object.keys(r.s);
  const H = Math.round(W * 0.78);
  const ts = fitTransform(ids.map((k) => r.s[k]), W, H, 56);
  const tg = fitTransform(ids.map((k) => r.g[k]), W, H, 56);
  const S = new Map(), G = new Map();
  for (const k of ids) { S.set(k, ts(r.s[k])); G.set(k, tg(r.g[k])); }
  return { H, S, G };
}

function labelPlace(p, nbrs) {
  let vx = 0, vy = 0;
  for (const q of nbrs) {
    let dx = q[0] - p[0], dy = q[1] - p[1];
    const L = Math.hypot(dx, dy) || 1;
    if (dx < -1e-6 || (Math.abs(dx) <= 1e-6 && dy < 0)) { dx = -dx; dy = -dy; }
    vx += dx / L; vy += dy / L;
  }
  const L = Math.hypot(vx, vy) || 1, ux = vx / L, uy = vy / L;
  if (Math.abs(uy) < 0.38) return { x: p[0] + 3, y: p[1] - 7, rot: -45 };
  let nx = -uy, ny = ux;
  if (nx < 0) { nx = -nx; ny = -ny; }
  return { x: p[0] + nx * 8, y: p[1] + ny * 8 + 3, rot: 0 };
}

function build() {
  const r = regionDef(state.region);
  const svg = $("sch-svg");
  svg.innerHTML = "";
  const { H, S, G } = screenCoords(r);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.style.width = `${100 * state.zoom}%`;
  // 확대 배율의 역수: 글자·원·선 굵기를 줄여 화면 크기는 그대로, 간격만 넓어지게
  const k = 1 / state.zoom;
  const idx = new Map(data.clusters.map((c, i) => [c.id, i]));
  const lineByid = new Map(data.lines.map((l, i) => [l.id, i]));
  const gEdges = el("g", { class: "sch-edges" }, svg), gSame = el("g", { class: "sch-same" }, svg);
  const gRoute = el("g", { class: "sch-route" }, svg), gSt = el("g", { class: "sch-stations" }, svg);
  const items = { edges: [], same: [], st: [], lab: [], route: [], portal: [] };
  const nbr = new Map();
  for (const [a, b, ls] of r.e) {
    if (!nbr.has(a)) nbr.set(a, []);
    if (!nbr.has(b)) nbr.set(b, []);
    nbr.get(a).push(b); nbr.get(b).push(a);
    ls.forEach((lid, k) => {
      const col = (r.lines[lid] || {}).color || data.lines[lineByid.get(lid)]?.color || "#888";
      const ln = el("line", { stroke: col, "stroke-width": 4 * Math.max(k, 0.55), "stroke-linecap": "round" }, gEdges);
      items.edges.push({ e: ln, a, b, k, n: ls.length });
    });
  }
  // 같은 권역 안 포탈은 점선으로 잇는다 (양평·동래·신촌 등)
  for (const l of links) for (const [c1, c2] of l.same) {
    const i1 = data.clusters[c1].id, i2 = data.clusters[c2].id;
    if (!S.has(i1) || !S.has(i2) || reg[c1] !== r.id) continue;
    const ln = el("line", { stroke: WARP, "stroke-width": 2.2 * k, "stroke-dasharray": `${5 * k} ${5 * k}`, opacity: 0.9 }, gSame);
    ln.appendChild(el("title")).textContent = `같은 권역 워프 [${l.name}] (비용 ${l.cost})`;
    items.same.push({ e: ln, a: i1, b: i2 });
  }
  // 역과 포탈 아이콘
  const portalAt = new Map();
  for (const l of links) for (const m of l.members) {
    if (!portalAt.has(m.c)) portalAt.set(m.c, []);
    portalAt.get(m.c).push(l);
  }
  for (const cid of Object.keys(r.s).sort()) {
    const ci = idx.get(cid);
    if (ci === undefined) continue;
    const deg = (nbr.get(cid) || []).length;
    const ps = portalAt.get(ci) || [];
    const g = el("g", { class: "sch-st" + (ps.length ? " portal" : ""), "data-c": ci }, gSt);
    const circ = el("circle", { r: (ps.length ? 6 : deg !== 2 ? 5 : 3.2) * k, fill: "#fff", stroke: ps.length ? WARP : "#222", "stroke-width": (ps.length ? 3 : deg !== 2 ? 2 : 1.2) * k, "data-big": deg !== 2 || ps.length ? 1 : 0 }, g);
    const t = el("text", { "font-size": (deg !== 2 || ps.length ? 12 : 10) * k, fill: "#222", "stroke-width": 3 * k }, g);
    t.textContent = data.clusters[ci].n;
    let icon = null;
    if (ps.length) {
      const tg = warpTargets(links, ci);
      const dest = [...new Set(tg.map((x) => regionDef(x.region)?.city || "?"))];
      icon = el("text", { "font-size": 13 * k, class: "sch-icon", "stroke-width": 3 * k }, g);
      icon.textContent = `🌀${dest.filter((d) => d !== r.city).length ? "→" + dest.filter((d) => d !== r.city).join("·") : ""}`;
      g.addEventListener("click", (ev) => { ev.stopPropagation(); openPortal(ci, ev); });
      g.appendChild(el("title")).textContent = `포탈 역 ${data.clusters[ci].n}: ` + tg.map((x) => `[${x.portal}] → ${regionDef(x.region)?.city || ""} ${data.clusters[x.c].n}`).join(", ");
    }
    items.st.push({ g, circ, t, icon, cid, ci });
  }
  // 경로 하이라이트 (이 권역의 승차 구간)
  if (state.steps) {
    for (const s of state.steps) {
      if (s.type !== "ride" || s.region !== r.id) continue;
      const cids = s.clusters.map((c) => data.clusters[c].id).filter((x) => S.has(x));
      const col = data.lines[s.line]?.color || "#333";
      for (let i = 1; i < cids.length; i++) {
        const halo = el("line", { stroke: "#ffd400", "stroke-width": 14 * Math.max(k, 0.55), "stroke-linecap": "round", opacity: 0.85 }, gRoute);
        const ln = el("line", { stroke: col, "stroke-width": 7 * Math.max(k, 0.55), "stroke-linecap": "round" }, gRoute);
        items.route.push({ e: halo, a: cids[i - 1], b: cids[i] }, { e: ln, a: cids[i - 1], b: cids[i] });
      }
    }
  }
  els = { S, G, items, nbr, H, k };
  place(state.view === "schematic" ? 1 : 0);
  if (state.focus !== null) pulse(state.focus);
}

// t = 1 도식, 0 지리. 사이 값은 전환 애니메이션
function place(t) {
  const { S, G, items, nbr, k } = els;
  const P = (k) => lerpPoint(G.get(k), S.get(k), t);
  const segs = [];   // 5차 R4: 라벨이 노선 선 위에 걸치지 않게 라벨 배치에 넘긴다
  for (const x of items.edges) {
    const [p, q] = offsetSegment(P(x.a), P(x.b), x.k, x.n, 4.5 * Math.max(k, 0.55));
    x.e.setAttribute("x1", p[0].toFixed(1)); x.e.setAttribute("y1", p[1].toFixed(1));
    x.e.setAttribute("x2", q[0].toFixed(1)); x.e.setAttribute("y2", q[1].toFixed(1));
    segs.push([p[0], p[1], q[0], q[1]]);
  }
  for (const x of [...items.same, ...items.route]) {
    const p = P(x.a), q = P(x.b);
    x.e.setAttribute("x1", p[0].toFixed(1)); x.e.setAttribute("y1", p[1].toFixed(1));
    x.e.setAttribute("x2", q[0].toFixed(1)); x.e.setAttribute("y2", q[1].toFixed(1));
  }
  // 멈춘 상태(t = 0 또는 1)에서는 라벨 충돌 회피 배치, 전환 애니메이션 중에는 단순 규칙
  const settled = t === 0 || t === 1;
  const placed = settled ? placeLabels(items.st.map((x) => {
    const p = P(x.cid), nb = (nbr.get(x.cid) || []).map(P);
    let vx = 0, vy = 0;
    for (const q of nb) {
      let dx = q[0] - p[0], dy = q[1] - p[1];
      const L = Math.hypot(dx, dy) || 1;
      if (dx < -1e-6 || (Math.abs(dx) <= 1e-6 && dy < 0)) { dx = -dx; dy = -dy; }
      vx += dx / L; vy += dy / L;
    }
    const L = Math.hypot(vx, vy) || 1;
    return { p, dir: [vx / L, vy / L], text: x.t.textContent, size: +x.t.getAttribute("font-size"), big: x.circ.getAttribute("data-big") === "1" };
  }), { k, segments: segs }) : null;
  if (placed) { els.placed = placed; els.segs = segs; }
  items.st.forEach((x, i) => {
    const p = P(x.cid);
    x.circ.setAttribute("cx", p[0].toFixed(1)); x.circ.setAttribute("cy", p[1].toFixed(1));
    const lp = placed ? placed[i] : labelPlace(p, (nbr.get(x.cid) || []).map(P));
    x.t.setAttribute("x", lp.x.toFixed(1)); x.t.setAttribute("y", lp.y.toFixed(1));
    x.t.setAttribute("text-anchor", lp.anchor || "start");
    if (lp.rot) x.t.setAttribute("transform", `rotate(${lp.rot} ${lp.x.toFixed(1)} ${lp.y.toFixed(1)})`); else x.t.removeAttribute("transform");
    if (x.icon) { x.icon.setAttribute("x", (p[0] - 8 * k).toFixed(1)); x.icon.setAttribute("y", (p[1] + 20 * k).toFixed(1)); }
  });
}

// 5차 R4: 라벨 품질 지표 (E2E 측정용, 필요할 때만 계산)
window.__schLabelStats = () => (els && els.placed ? labelStats(els.placed, els.segs) : null);

function animateTo(view) {
  if (view === state.view || !els) { state.view = view; return; }
  const from = state.view === "schematic" ? 1 : 0, to = view === "schematic" ? 1 : 0;
  state.view = view;
  const t0 = performance.now(), dur = 450;
  const tick = (now) => {
    const u = Math.min(1, (now - t0) / dur), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    place(from + (to - from) * e);
    if (u < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
  saveHash();
}

function pulse(ci) {
  const g = document.querySelector(`.sch-st[data-c="${ci}"] circle`);
  if (!g) return;
  g.classList.add("pulse");
  const cx = +g.getAttribute("cx"), cy = +g.getAttribute("cy");
  const sc = $("sch-scroll"), svg = $("sch-svg");
  const k = svg.clientWidth / W;
  sc.scrollTo({ left: cx * k - sc.clientWidth / 2, top: cy * k - sc.clientHeight / 2, behavior: "smooth" });
  setTimeout(() => g.classList.remove("pulse"), 2400);
  state.focus = null;
}

function openPortal(ci, ev) {
  const pop = $("sch-pop");
  const tg = warpTargets(links, ci);
  pop.innerHTML = `<b>🌀 ${esc(data.clusters[ci].n)}</b><ul>${tg.map((x, i) => `<li><button type="button" data-i="${i}">[${esc(x.portal)}] ${x.cross ? "국가 간 · " : ""}${esc(regionDef(x.region)?.city || "")} ${esc(data.clusters[x.c].n)} <span class="meta">${esc(x.tier)} · 비용 ${x.cost}</span></button></li>`).join("")}</ul>`;
  pop.hidden = false;
  const box = $("sch-scroll").getBoundingClientRect();
  pop.style.left = `${Math.min(ev.clientX - box.left + 8, box.width - 230)}px`;
  pop.style.top = `${ev.clientY - box.top + 8}px`;
  pop.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const x = tg[+b.dataset.i];
    pop.hidden = true;
    state.focus = x.c;
    show(x.region);
  }));
}

function show(regionId) {
  if (!regionDef(regionId)) return;
  const changed = state.region !== regionId || !els;
  state.region = regionId;
  if (changed) state.zoom = DEFAULT_ZOOM[regionId] || 1;
  const hadFocus = state.focus !== null;
  $("sch-pop").hidden = true;
  drawTabs();
  build();
  if (changed && !hadFocus) {
    const sc = $("sch-scroll");
    requestAnimationFrame(() => sc.scrollTo({ left: (sc.scrollWidth - sc.clientWidth) / 2, top: (sc.scrollHeight - sc.clientHeight) / 2 }));
  }
  const r = regionDef(regionId);
  $("sch-note").textContent = r.note || "";
  saveHash();
}

function renderRoute() {
  const box = $("sch-route");
  const a = resolveQuery(data, labels, $("sch-from").value), b = resolveQuery(data, labels, $("sch-to").value);
  if (a.error || b.error) { box.innerHTML = `<p class="error">${esc(a.error || b.error)}</p>`; state.steps = null; return; }
  const route = routeClusters(data, adj, a.index, b.index);
  if (!route) { box.innerHTML = '<p class="error">연결 안 됨.</p>'; state.steps = null; return; }
  state.steps = routeSteps(data, route, reg);
  const seq = panelSequence(state.steps);
  const li = state.steps.map((s, i) => {
    if (s.type === "ride") {
      const ln = data.lines[s.line];
      return `<li data-r="${s.region}" data-i="${i}"><span class="bar" style="background:${ln.color}"></span><div><b>${esc(ln.name)}</b> ${esc(data.clusters[s.clusters[0]].n)} → ${esc(data.clusters[s.clusters[s.clusters.length - 1]].n)}<div class="meta">${s.clusters.length - 1}역 · ${esc(regionDef(s.region)?.city || "")} 패널</div></div></li>`;
    }
    const fr = regionDef(s.fromRegion)?.city || "", to = regionDef(s.toRegion)?.city || "";
    return `<li class="warp" data-r="${s.toRegion}" data-i="${i}" data-c="${s.to}"><span class="bar"></span><div>⇢ 워프 ${esc(s.tier)} [${esc(s.portal)}] ${esc(fr)} ${esc(data.clusters[s.from].n)} ⇢ ${esc(to)} ${esc(data.clusters[s.to].n)}${s.panelChange ? ` <button type="button" class="ghost sch-go">${esc(to)} 패널로 이동 ▸</button>` : " <span class='meta'>(같은 패널)</span>"}</div></li>`;
  }).join("");
  box.innerHTML = `<div class="summary"><span class="chip">총비용 <b>${route.cost}</b></span><span class="chip">승차 <b>${route.rides}</b>역</span><span class="chip warp">워프 <b>${route.warps}</b>회</span><span class="chip">패널 <b>${seq.map((x) => esc(regionDef(x)?.city || x)).join(" → ")}</b></span></div><ol class="steps">${li}</ol>`;
  box.querySelectorAll("li[data-r]").forEach((x) => x.addEventListener("click", () => { state.focus = x.dataset.c ? +x.dataset.c : null; show(x.dataset.r); }));
  state.focus = a.index[0] ?? a.index;
  show(seq[0]);
}

function saveHash() {
  const p = new URLSearchParams({ r: state.region, v: state.view, rs: rsKey });
  if ($("sch-from").value && $("sch-to").value) { p.set("from", $("sch-from").value); p.set("to", $("sch-to").value); }
  history.replaceState(null, "", `#${p}`);
}

document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => animateTo(b.dataset.view)));
// 확대·축소: 화면 가운데를 유지하면서 다시 그린다 (글자 크기는 그대로)
function rezoom(f) {
  const sc = $("sch-scroll");
  const cx = (sc.scrollLeft + sc.clientWidth / 2) / sc.scrollWidth, cy = (sc.scrollTop + sc.clientHeight / 2) / sc.scrollHeight;
  state.zoom = Math.min(6, Math.max(1, state.zoom * f));
  build();
  sc.scrollTo({ left: cx * sc.scrollWidth - sc.clientWidth / 2, top: cy * sc.scrollHeight - sc.clientHeight / 2 });
}
$("sch-zin").addEventListener("click", () => rezoom(1.5));
$("sch-zout").addEventListener("click", () => rezoom(1 / 1.5));
$("sch-form").addEventListener("submit", (e) => { e.preventDefault(); renderRoute(); saveHash(); });
$("sch-rs").addEventListener("change", async (e) => { await loadBundle(e.target.value); if ($("sch-from").value && $("sch-to").value) renderRoute(); else show(state.region); });
$("sch-scroll").addEventListener("click", () => { $("sch-pop").hidden = true; });

const h = new URLSearchParams(location.hash.slice(1));
await loadBundle(h.get("rs") || "strict");
state.view = h.get("v") === "geo" ? "geo" : "schematic";
document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === state.view)));
if (h.get("from") && h.get("to")) { $("sch-from").value = h.get("from"); $("sch-to").value = h.get("to"); renderRoute(); } else show(h.get("r") || state.region);
// 테스트·디버그용
window.__sch = { state, get data() { return data; }, get reg() { return reg; }, sch };
