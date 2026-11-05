import { buildAdj, buildLabels, resolveQuery, routeClusters } from "./route.js";

const RULESET = "strict";
const $ = (id) => document.getElementById(id);
const WARP_COLOR = getComputedStyle(document.documentElement).getPropertyValue("--warp").trim() || "#8b3dff";

const res = await fetch(`data/kr_${RULESET}.json`);
const data = await res.json();
const labels = buildLabels(data);
const adj = { true: buildAdj(data, { warp: true }), false: buildAdj(data, { warp: false }) };
const lineColor = (i) => data.lines[i]?.color || "#888";
const nodeLL = (n) => [data.nodes[n].la, data.nodes[n].lo];
const clusterLL = (c) => [data.clusters[c].la, data.clusters[c].lo];

$("ruleset").textContent = `${data.meta.ruleset} (T1, 환승 ${data.meta.costs.transfer} · 승차 ${data.meta.costs.ride} · 워프 ${data.portals[0]?.cost ?? "-"})`;
$("attribution").textContent = data.meta.attribution;
$("stats").textContent = `역 ${data.clusters.length} · 노선 ${data.lines.length} · 포탈 ${data.portals.length}`;
$("station-list").innerHTML = labels.map((l) => `<option value="${l}"></option>`).join("");

// ---------- 지도 ----------
const map = L.map("map", { preferCanvas: true, zoomControl: true }).setView([36.4, 127.8], 7);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const linesLayer = L.layerGroup().addTo(map);
for (const [i, ln] of data.lines.entries()) {
  for (const sq of ln.seqs) {
    const pts = sq.nodes.map(nodeLL);
    if (sq.circular && pts.length > 2) pts.push(pts[0]);
    // 단방향 시퀀스(응암순환)는 점선 + 툴팁에 방향 표시. 길찾기·퍼즐 이동도 그 방향으로만 된다
    const tip = sq.directed ? `${ln.name} (단방향: ${sq.nodes.map((n) => data.nodes[n].n).join("→")}→${data.nodes[sq.nodes[0]].n})` : ln.name;
    L.polyline(pts, { color: ln.color, weight: 3, opacity: 0.85, dashArray: sq.directed ? "8 5" : null })
      .bindTooltip(tip, { sticky: true }).addTo(linesLayer);
  }
}

// 워프 아크: 두 클러스터 사이 2차 베지어 곡선
function arc(a, b, bend = 0.25, n = 40) {
  const [la1, lo1] = a, [la2, lo2] = b;
  const mx = (la1 + la2) / 2, my = (lo1 + lo2) / 2;
  const dx = la2 - la1, dy = lo2 - lo1;
  const cx = mx - dy * bend, cy = my + dx * bend;
  const pts = [];
  for (let k = 0; k <= n; k++) {
    const t = k / n, u = 1 - t;
    pts.push([u * u * la1 + 2 * u * t * cx + t * t * la2, u * u * lo1 + 2 * u * t * cy + t * t * lo2]);
  }
  return pts;
}
const warpLayer = L.layerGroup().addTo(map);
for (const p of data.portals) {
  for (let i = 0; i < p.c.length; i++) for (let j = i + 1; j < p.c.length; j++) {
    L.polyline(arc(clusterLL(p.c[i]), clusterLL(p.c[j])), { color: WARP_COLOR, weight: 1.6, opacity: 0.55, dashArray: "4 6" })
      .bindTooltip(`워프 ${p.tier} [${p.n}] · ${p.c.length}개 역`, { sticky: true }).addTo(warpLayer);
  }
}

const stationLayer = L.layerGroup().addTo(map);
const portalClusters = new Set(data.portals.flatMap((p) => p.c));
for (const [ci, c] of data.clusters.entries()) {
  const m = L.circleMarker([c.la, c.lo], {
    radius: portalClusters.has(ci) ? 5 : 3, weight: portalClusters.has(ci) ? 2 : 1,
    color: portalClusters.has(ci) ? WARP_COLOR : "#4a5560", fillColor: "#fff", fillOpacity: 1,
  }).addTo(stationLayer);
  m.bindTooltip(c.n, { direction: "top" });
  m.on("click", () => {
    const el = document.createElement("div");
    el.innerHTML = `<div class="popup-name">${c.n}</div><div class="popup-lines">${c.city} · ${c.lines.join(", ")}</div>
      <div class="popup-btns"><button data-k="from">출발</button><button data-k="to">도착</button></div>`;
    el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      $(b.dataset.k).value = labels[ci];
      map.closePopup();
      if ($("from").value && $("to").value) run();
    }));
    L.popup().setLatLng([c.la, c.lo]).setContent(el).openOn(map);
  });
}

// ---------- 길찾기 ----------
const routeLayer = L.layerGroup().addTo(map);

function esc(s) { return String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch])); }

function render(r, warp) {
  routeLayer.clearLayers();
  const box = $("result");
  if (r.error) { box.innerHTML = `<p class="error">${esc(r.error)}</p>`; return; }
  if (!r.route) {
    box.innerHTML = `<p class="error">연결 안 됨.</p><p class="hint">${warp ? "이 ruleset으로는 두 역이 이어지지 않는다." : "워프 없이는 다른 도시로 못 간다. 워프 허용을 켜 봐."}</p>`;
    return;
  }
  const { route } = r;
  const items = [];
  const bounds = [];
  for (const s of route.segments) {
    if (s.type === "ride") {
      const ln = data.lines[s.line];
      const a = data.nodes[s.nodes[0]], b = data.nodes[s.nodes[s.nodes.length - 1]];
      items.push(`<li><span class="bar" style="background:${ln.color}"></span><div><b>${esc(ln.name)}</b> ${esc(a.n)} → ${esc(b.n)}<div class="meta">${s.nodes.length - 1}역 · ${s.nodes.slice(1, -1).map((n) => esc(data.nodes[n].n)).join(" · ") || "직행"}</div></div></li>`);
      const pts = s.nodes.map(nodeLL);
      bounds.push(...pts);
      L.polyline(pts, { color: "#fff", weight: 10, opacity: 0.9 }).addTo(routeLayer);
      L.polyline(pts, { color: ln.color, weight: 6, opacity: 1 }).addTo(routeLayer);
    } else if (s.type === "transfer") {
      const a = data.nodes[s.from], b = data.nodes[s.to];
      items.push(`<li class="transfer"><span></span><div>환승 · ${esc(a.g)} → ${esc(b.g)}</div></li>`);
    } else if (s.type === "warp") {
      const a = data.nodes[s.from], b = data.nodes[s.to], p = data.nodes[s.portal];
      items.push(`<li class="warp"><span class="bar"></span><div>⇢ 워프 [${esc(p.n)}] ${esc(a.ct)} ${esc(a.n)} ⇢ ${esc(b.ct)} ${esc(b.n)}</div></li>`);
      const pts = arc(nodeLL(s.from), nodeLL(s.to));
      bounds.push(...pts);
      L.polyline(pts, { color: WARP_COLOR, weight: 4, opacity: 0.95, dashArray: "8 8" }).addTo(routeLayer);
    }
  }
  const first = route.path[0].node, last = route.path[route.path.length - 1].node;
  for (const [n, color] of [[first, "#12a150"], [last, "#e5484d"]]) {
    L.circleMarker(nodeLL(n), { radius: 8, color: "#fff", weight: 3, fillColor: color, fillOpacity: 1 }).addTo(routeLayer);
    bounds.push(nodeLL(n));
  }
  box.innerHTML = `<div class="summary"><span class="chip">총비용 <b>${route.cost}</b></span><span class="chip">승차 <b>${route.rides}</b>역</span><span class="chip warp">워프 <b>${route.warps}</b>회</span></div><ol class="steps">${items.join("")}</ol>`;
  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
}

function run() {
  const warp = $("allow-warp").checked;
  const a = resolveQuery(data, labels, $("from").value), b = resolveQuery(data, labels, $("to").value);
  if (a.error || b.error) return render({ error: a.error || b.error }, warp);
  const route = routeClusters(data, adj[warp], a.index, b.index);
  render({ route }, warp);
  const params = new URLSearchParams({ from: $("from").value, to: $("to").value, warp: warp ? "1" : "0" });
  history.replaceState(null, "", `#${params}`);
}

$("route-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
$("allow-warp").addEventListener("change", () => { if ($("from").value && $("to").value) run(); });
$("swap").addEventListener("click", () => { [$("from").value, $("to").value] = [$("to").value, $("from").value]; if ($("from").value && $("to").value) run(); });
document.querySelectorAll(".examples button").forEach((b) => b.addEventListener("click", () => { $("from").value = b.dataset.from; $("to").value = b.dataset.to; run(); }));
$("show-warps").addEventListener("change", (e) => (e.target.checked ? warpLayer.addTo(map) : warpLayer.remove()));
$("show-stations").addEventListener("change", (e) => (e.target.checked ? stationLayer.addTo(map) : stationLayer.remove()));

// URL 해시로 상태 복원 (#from=강남&to=부산 동래)
const h = new URLSearchParams(location.hash.slice(1));
if (h.get("from") && h.get("to")) {
  $("from").value = h.get("from");
  $("to").value = h.get("to");
  $("allow-warp").checked = h.get("warp") !== "0";
  run();
}
