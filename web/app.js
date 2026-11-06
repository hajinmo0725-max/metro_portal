import { buildAdj, buildLabels, resolveQuery, routeClusters } from "./route.js";
import { COUNTRY_KO, CROSS_COLOR, RULESETS, arcBends, clusterCountry, confidenceLabel, rulesetByKey, tierLabel, warpStyle } from "./world.js";

const $ = (id) => document.getElementById(id);
const WARP_COLOR = getComputedStyle(document.documentElement).getPropertyValue("--warp").trim() || "#8b3dff";

// 번들은 ruleset 토글로 바꿔 읽는다 (Phase 1). 처음은 URL 해시의 rs 또는 한국만
let data, labels, adj, rsKey;
const lineColor = (i) => data.lines[i]?.color || "#888";
const nodeLL = (n) => [data.nodes[n].la, data.nodes[n].lo];
const clusterLL = (c) => [data.clusters[c].la, data.clusters[c].lo];

// ---------- 지도 ----------
const map = L.map("map", { preferCanvas: true, zoomControl: true }).setView([36.4, 127.8], 7);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);
const linesLayer = L.layerGroup().addTo(map);
const warpLayer = L.layerGroup().addTo(map);
const stationLayer = L.layerGroup().addTo(map);       // 포탈 역 (항상)
const plainStationLayer = L.layerGroup();             // 일반 역: 4차 Q5 낮은 줌(< PLAIN_MIN_ZOOM)에서는 숨겨 노선을 가리지 않게
const routeLayer = L.layerGroup().addTo(map);
const PLAIN_MIN_ZOOM = 10;
// 아크는 클릭·탭 판정 여유를 크게 (터치에서 가는 선을 누르기 어렵다, QA 3장)
const arcRenderer = L.canvas({ tolerance: 8 });
function syncPlainStations() {
  const on = $("show-stations").checked && map.getZoom() >= PLAIN_MIN_ZOOM;
  if (on && !map.hasLayer(plainStationLayer)) plainStationLayer.addTo(map);
  if (!on && map.hasLayer(plainStationLayer)) plainStationLayer.remove();
}
map.on("zoomend", syncPlainStations);

function drawLines() {
  linesLayer.clearLayers();
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
// 클러스터 표시 이름: 도시 + 이름 + (노선). 같은 이름 역이 같은 도시에 여럿이면 노선으로 구분한다 (QA 4장 '수도권 양평 ⇢ 수도권 양평역')
function clusterLabel(ci) {
  const c = data.clusters[ci];
  return `${c.city} ${c.n} (${c.lines.join("·")})`;
}
function drawWarps() {
  warpLayer.clearLayers();
  // 4차 Q5: 같은 도시 쌍을 잇는 아크(서울–부산 등)는 곡률을 나눠 겹치지 않게, 짧은 도시 내부 아크(동래 1.4km)는 굵고 진하게
  const bends = arcBends(data, (ci) => clusterLL(ci), (a, b) => L.latLng(a).distanceTo(b));
  for (const p of data.portals) {
    const names = p.texts && p.texts.length ? ` · 원문 ${p.texts.join(" / ")}` : "";
    const conf = p.conf && p.conf !== "high" ? ` · ${confidenceLabel(p.conf)}` : "";
    const pop = `<div class="arc-pop"><b>${p.x ? "국가 간 " : ""}워프 [${esc(p.n)}]</b><div>${esc(tierLabel(p.tier))} · 비용 ${p.cost}${esc(conf)}</div>`
      + `<ul>${p.c.map((ci) => `<li>${esc(clusterLabel(ci))}</li>`).join("")}</ul>${p.texts && p.texts.length ? `<div>원문 ${esc(p.texts.join(" / "))}</div>` : ""}</div>`;
    for (let i = 0; i < p.c.length; i++) for (let j = i + 1; j < p.c.length; j++) {
      const b = bends.get(`${p.id}|${i}|${j}`);
      const st = { ...warpStyle(p, WARP_COLOR), ...(b.short ? { weight: 3.5, opacity: 0.95, dashArray: "3 4" } : {}), renderer: arcRenderer };
      L.polyline(arc(clusterLL(p.c[i]), clusterLL(p.c[j]), b.bend), st)
        .bindTooltip(`${p.x ? "국가 간 " : ""}워프 ${tierLabel(p.tier)} (비용 ${p.cost}) [${p.n}] · ${p.c.length}개 역${names}${conf}`, { sticky: true })
        .bindPopup(pop)   // 클릭·탭으로도 연다
        .addTo(warpLayer);
    }
  }
}

function drawStations() {
  stationLayer.clearLayers();
  plainStationLayer.clearLayers();
  const portalClusters = new Set(data.portals.flatMap((p) => p.c));
  const crossClusters = new Set(data.portals.filter((p) => p.x).flatMap((p) => p.c));
  for (const [ci, c] of data.clusters.entries()) {
    const isP = portalClusters.has(ci), isX = crossClusters.has(ci);
    const m = L.circleMarker([c.la, c.lo], {
      radius: isP ? 5 : 3, weight: isP ? 2 : 1,
      color: isX ? CROSS_COLOR : isP ? WARP_COLOR : "#4a5560", fillColor: "#fff", fillOpacity: 1,
    }).addTo(isP ? stationLayer : plainStationLayer);
    const ctry = COUNTRY_KO[clusterCountry(c)] || clusterCountry(c);
    m.bindTooltip(`${c.n} · ${ctry}`, { direction: "top" });
    m.on("click", () => {
      const el = document.createElement("div");
      el.innerHTML = `<div class="popup-name">${esc(c.n)}</div><div class="popup-lines">${esc(ctry)} · ${esc(c.city)} · ${esc(c.lines.join(", "))}</div>
        <div class="popup-btns"><button data-k="from">출발</button><button data-k="to">도착</button></div>`;
      el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        $(b.dataset.k).value = labels[ci];
        map.closePopup();
        if ($("from").value && $("to").value) run();
      }));
      L.popup().setLatLng([c.la, c.lo]).setContent(el).openOn(map);
    });
  }
}

async function load(key, { fit = false } = {}) {
  const def = rulesetByKey(key);
  const res = await fetch(`data/${def.file}`);
  data = await res.json();
  rsKey = def.key;
  labels = buildLabels(data);
  adj = { true: buildAdj(data, { warp: true }), false: buildAdj(data, { warp: false }) };
  const tiers = Object.keys(data.meta.tiers || { T1: 1 }).join("+");
  const nX = data.portals.filter((p) => p.x).length;
  $("ruleset").textContent = `${data.meta.ruleset} (${tiers}, 환승 ${data.meta.costs.transfer} · 승차 ${data.meta.costs.ride})${def.note ? " · " + def.note : ""}`;
  $("attribution").textContent = data.meta.attribution;
  const countries = [...new Set(data.clusters.map(clusterCountry))].map((c) => COUNTRY_KO[c] || c).join("·");
  $("stats").textContent = `${countries} · 역 ${data.clusters.length} · 노선 ${data.lines.length} · 포탈 ${data.portals.length}${(data.meta.countries || []).length > 1 ? ` (국가 간 ${nX})` : ""}`;
  $("station-list").innerHTML = labels.map((l) => `<option value="${esc(l)}"></option>`).join("");
  $("ruleset-select").value = rsKey;
  $("ruleset-note").textContent = def.note === "현지어 라벨 포함" || def.note === "T3b 포함"
    ? "타이베이 이름은 위키데이터 zh-Hant 라벨(현지어 라벨, 준공식)이다. 그 라벨로 맞은 국가 간 워프는 신뢰도 '보통'. 국가 간 경로는 선택 항목이고 기본은 한국만."
    : (data.meta.countries || []).length > 1 && nX === 0 ? "공식명만 쓰면 타이베이와 이어지는 포탈이 없다 (타이베이 공식명 미확보)." : "";
  drawLines();
  drawWarps();
  drawStations();
  syncPlainStations();
  routeLayer.clearLayers();
  $("result").innerHTML = '<p class="hint">지도에서 역을 눌러 출발·도착을 고르거나 위에 역 이름을 입력해.</p>';
  if (fit) map.fitBounds(data.clusters.map((c) => [c.la, c.lo]), { padding: [20, 20] });
}

// ---------- 길찾기 ----------
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
  // 4차 Q6-5: 출발 나라와 다른 나라를 지나는 구간은 '해외 경유'로 표시
  const home = data.nodes[route.path[0].node].co || "KR";
  let abroad = 0;
  for (const s of route.segments) {
    if (s.type === "ride") {
      const ln = data.lines[s.line];
      const a = data.nodes[s.nodes[0]], b = data.nodes[s.nodes[s.nodes.length - 1]];
      const out = (a.co || "KR") !== home;
      if (out) abroad += 1;
      const tag = out ? `<span class="abroad">해외 경유 · ${esc(COUNTRY_KO[a.co] || a.co)}</span>` : "";
      items.push(`<li><span class="bar" style="background:${ln.color}"></span><div><b>${esc(ln.name)}</b>${tag} ${esc(a.n)} → ${esc(b.n)}<div class="meta">${s.nodes.length - 1}역 · ${s.nodes.slice(1, -1).map((n) => esc(data.nodes[n].n)).join(" · ") || "직행"}</div></div></li>`);
      const pts = s.nodes.map(nodeLL);
      bounds.push(...pts);
      L.polyline(pts, { color: "#fff", weight: 10, opacity: 0.9 }).addTo(routeLayer);
      L.polyline(pts, { color: ln.color, weight: 6, opacity: 1 }).addTo(routeLayer);
    } else if (s.type === "transfer") {
      const a = data.nodes[s.from], b = data.nodes[s.to];
      items.push(`<li class="transfer"><span></span><div>환승 · ${esc(a.g)} → ${esc(b.g)}</div></li>`);
    } else if (s.type === "warp") {
      const a = data.nodes[s.from], b = data.nodes[s.to], p = data.nodes[s.portal];
      const cross = (a.co || "KR") !== (b.co || "KR");
      // 같은 이름 역이라 노선을 병기한다 (예: 수도권 양평 (5호선) ⇢ 수도권 양평 (경의·중앙선))
      items.push(`<li class="warp${cross ? " cross" : ""}"><span class="bar"></span><div>⇢ ${cross ? "국가 간 " : ""}워프 ${esc(s.tier)} [${esc(p.n)}] ${esc(a.ct)} ${esc(a.n)} <span class="meta">(${esc(a.g)})</span> ⇢ ${esc(b.ct)} ${esc(b.n)} <span class="meta">(${esc(b.g)})</span></div></li>`);
      const pts = arc(nodeLL(s.from), nodeLL(s.to), cross ? 0.18 : 0.25);
      bounds.push(...pts);
      L.polyline(pts, { color: cross ? CROSS_COLOR : WARP_COLOR, weight: 4, opacity: 0.95, dashArray: "8 8" }).addTo(routeLayer);
    }
  }
  const first = route.path[0].node, last = route.path[route.path.length - 1].node;
  for (const [n, color] of [[first, "#12a150"], [last, "#e5484d"]]) {
    L.circleMarker(nodeLL(n), { radius: 8, color: "#fff", weight: 3, fillColor: color, fillOpacity: 1 }).addTo(routeLayer);
    bounds.push(nodeLL(n));
  }
  box.innerHTML = `<div class="summary"><span class="chip">총비용 <b>${route.cost}</b></span><span class="chip">승차 <b>${route.rides}</b>역</span><span class="chip warp">워프 <b>${route.warps}</b>회</span>${abroad ? `<span class="chip abroad">해외 경유 구간 <b>${abroad}</b></span>` : ""}</div><ol class="steps">${items.join("")}</ol>`;
  if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
  // 4차 Q4: 모바일(지도가 위에 고정)에서는 결과로 스크롤해서 지도와 결과를 함께 보이게
  if (window.matchMedia("(max-width: 720px)").matches) box.scrollIntoView({ behavior: "smooth", block: "start" });
}

function run() {
  const warp = $("allow-warp").checked;
  const a = resolveQuery(data, labels, $("from").value), b = resolveQuery(data, labels, $("to").value);
  if (a.error || b.error) return render({ error: a.error || b.error }, warp);
  const route = routeClusters(data, adj[warp], a.index, b.index);
  render({ route }, warp);
  const params = new URLSearchParams({ from: $("from").value, to: $("to").value, warp: warp ? "1" : "0", rs: rsKey });
  history.replaceState(null, "", `#${params}`);
}

$("route-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
$("allow-warp").addEventListener("change", () => { if ($("from").value && $("to").value) run(); });
$("swap").addEventListener("click", () => { [$("from").value, $("to").value] = [$("to").value, $("from").value]; if ($("from").value && $("to").value) run(); });
document.querySelectorAll(".examples button").forEach((b) => b.addEventListener("click", () => { $("from").value = b.dataset.from; $("to").value = b.dataset.to; run(); }));
$("show-warps").addEventListener("change", (e) => (e.target.checked ? warpLayer.addTo(map) : warpLayer.remove()));
$("show-stations").addEventListener("change", (e) => { (e.target.checked ? stationLayer.addTo(map) : stationLayer.remove()); syncPlainStations(); });

$("ruleset-select").innerHTML = RULESETS.map((r) => `<option value="${r.key}">${esc(r.label)}</option>`).join("");
$("ruleset-select").addEventListener("change", async (e) => {
  const keep = [$("from").value, $("to").value];
  await load(e.target.value, { fit: (rulesetByKey(e.target.value).file.startsWith("world_")) });
  [$("from").value, $("to").value] = keep;
  if (keep[0] && keep[1]) run();
});
document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
  const v = { kr: [[36.4, 127.8], 7], tw: [[25.04, 121.52], 11] }[b.dataset.view];
  map.setView(v[0], v[1]);
}));

// URL 해시로 상태 복원 (#from=강남&to=부산 동래&rs=tw_t12)
const h = new URLSearchParams(location.hash.slice(1));
await load(h.get("rs") || "strict", { fit: false });
if (h.get("from") && h.get("to")) {
  $("from").value = h.get("from");
  $("to").value = h.get("to");
  $("allow-warp").checked = h.get("warp") !== "0";
  run();
}
// 테스트·디버그용 (e2e 스크립트가 읽는다)
window.__app = { map, get data() { return data; }, plainStationLayer, stationLayer, warpLayer };
