// 데일리 퍼즐 화면. 로직은 puzzle.js (node 테스트 대상), 여기는 지도·DOM만.
import { buildMoves, dailyPick, giveUp, kstDateString, legalMoves, medal, newGame, optimalPath, play, score, shareText,
  undo, validDateString } from "./puzzle.js";

const RULESET = "strict";
const $ = (id) => document.getElementById(id);
const WARP_COLOR = getComputedStyle(document.documentElement).getPropertyValue("--warp").trim() || "#8b3dff";
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

const [data, pz] = await Promise.all([
  fetch(`data/kr_${RULESET}.json`).then((r) => r.json()),
  fetch("data/puzzles.json").then((r) => r.json()),
]);
const moves = buildMoves(data);
const labels = data.clusters.map((c) => `${c.city} ${c.n}`);
const cLL = (c) => [data.clusters[c].la, data.clusters[c].lo];

// 날짜: #d=YYYY-MM-DD 로 다른 날 퍼즐도 풀 수 있다.
// 4차 Q1: 같은 탭에서 해시만 바꿔도 반영되게 hashchange에서 다시 읽는다 (상태가 날짜별이라 새로 고침이 가장 단순하고 안전)
window.addEventListener("hashchange", () => location.reload());
const hashDate = new URLSearchParams(location.hash.slice(1)).get("d");
const picked = dailyPick(pz, validDateString(hashDate) ? hashDate : kstDateString());
const { number, puzzle, beforeEpoch } = picked;
const dateStr = picked.date;   // 출시일 이전 날짜는 1회차 날짜로 맞춘다 (#0·음수 회차 방지)
const game = newGame(data, moves, puzzle);
const DIFF_KO = { easy: "쉬움", normal: "보통", hard: "어려움" };
const portalOf = new Map();
for (const p of data.portals) for (const c of p.c) portalOf.set(c, [...(portalOf.get(c) || []), p.n]);

$("pz-no").textContent = `#${number}`;
$("pz-from").textContent = labels[game.from];
$("pz-to").textContent = labels[game.to];
$("pz-chips").innerHTML = [
  `<span class="chip">${esc(dateStr)}</span>`,
  beforeEpoch ? `<span class="chip warn">출시일(${esc(pz.daily_epoch)}) 이전 날짜라 1회차를 보여 줌</span>` : "",
  `<span class="chip">난이도 <b>${DIFF_KO[puzzle.difficulty] || puzzle.difficulty}</b></span>`,
  puzzle.cost_no_warp !== null ? `<span class="chip">워프 없으면 <b>${puzzle.cost_no_warp}</b>수</span>` : `<span class="chip warp">워프 필수</span>`,
  `<span class="chip">최적은 비밀</span>`,
].join("");
$("attribution").textContent = data.meta.attribution;

// ---------- 지도 ----------
const map = L.map("map", { preferCanvas: true }).setView([36.4, 127.8], 7);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);
for (const ln of data.lines) for (const sq of ln.seqs) {
  const pts = sq.nodes.map((n) => [data.nodes[n].la, data.nodes[n].lo]);
  if (sq.circular && pts.length > 2) pts.push(pts[0]);
  L.polyline(pts, { color: ln.color, weight: 3, opacity: 0.55 }).addTo(map);
}
function arc(a, b, bend = 0.25, n = 40) {
  const [la1, lo1] = a, [la2, lo2] = b, mx = (la1 + la2) / 2, my = (lo1 + lo2) / 2, dx = la2 - la1, dy = lo2 - lo1;
  const cx = mx - dy * bend, cy = my + dx * bend, pts = [];
  for (let k = 0; k <= n; k++) { const t = k / n, u = 1 - t; pts.push([u * u * la1 + 2 * u * t * cx + t * t * la2, u * u * lo1 + 2 * u * t * cy + t * t * lo2]); }
  return pts;
}
for (const p of data.portals) for (let i = 0; i < p.c.length; i++) for (let j = i + 1; j < p.c.length; j++) {
  L.polyline(arc(cLL(p.c[i]), cLL(p.c[j])), { color: WARP_COLOR, weight: 1.2, opacity: 0.35, dashArray: "4 6" }).addTo(map);
}
// 4차 Q3: 포탈 역 강조 (보라 테두리). 이름에 마우스를 올리거나 누르면 어디로 워프되는지 보인다
for (const [c, names] of portalOf) {
  const dest = data.portals.filter((p) => p.c.includes(c)).flatMap((p) => p.c.filter((x) => x !== c)).map((x) => labels[x]);
  L.circleMarker(cLL(c), { radius: 5, color: WARP_COLOR, weight: 2.5, fillColor: "#fff", fillOpacity: 0.9 })
    .bindTooltip(`🌀 ${esc(labels[c])} · 워프 [${esc(names.join(", "))}] → ${esc(dest.join(", "))}`, { direction: "top" }).addTo(map);
}
const playLayer = L.layerGroup().addTo(map);

// ---------- 화면 갱신 ----------
function lineName(i) { return data.lines[i]?.name || ""; }

// 4차 Q1·Q3: 역 이름은 한 줄(줄바꿈 금지), 방면·노선은 옆에 줄여서. 도착역이 포탈 역이면 🌀 표시
function moveLabel(m) {
  if (m.type === "warp") return `<span class="nm">🌀 워프 [${esc(m.portal)}] → ${esc(labels[m.to])}</span>`;
  const dir = m.dir !== null && m.dir !== undefined ? `<span class="dir">${esc(data.clusters[m.dir].n)} 방면</span>` : "";
  const pt = m.toPortal && m.toPortal.length ? `<span class="pt" title="포탈 역: ${esc(m.toPortal.join(", "))}">🌀</span>` : "";
  return `<span class="nm">🚇 ${esc(data.clusters[m.to].n)}</span>${pt}${dir}`;
}

function draw() {
  playLayer.clearLayers();
  const here = game.path[game.path.length - 1];
  // 내 경로
  for (let i = 1; i < game.path.length; i++) {
    const a = cLL(game.path[i - 1]), b = cLL(game.path[i]), st = game.steps[i - 1];
    if (st.type === "warp") L.polyline(arc(a, b), { color: WARP_COLOR, weight: 4, dashArray: "8 8" }).addTo(playLayer);
    else L.polyline([a, b], { color: data.lines[st.lines[0]]?.color || "#333", weight: 7, opacity: 0.95 }).addTo(playLayer);
  }
  // 갈 수 있는 역 (지도에서 눌러도 이동)
  for (const m of legalMoves(game)) {
    L.circleMarker(cLL(m.to), { radius: 7, color: m.type === "warp" ? WARP_COLOR : "#2f6fed", weight: 3, fillColor: "#fff", fillOpacity: 1 })
      .bindTooltip(data.clusters[m.to].n, { direction: "top" }).on("click", () => step(m.to)).addTo(playLayer);
  }
  for (const [c, color] of [[game.to, "#e5484d"], [game.from, "#12a150"], [here, "#1b1f24"]]) {
    L.circleMarker(cLL(c), { radius: c === here ? 9 : 8, color: "#fff", weight: 3, fillColor: color, fillOpacity: 1 })
      .bindTooltip(labels[c], { permanent: c === game.to || c === here, direction: "auto" }).addTo(playLayer);
  }
  // 패널
  $("pz-here").textContent = labels[here];
  $("pz-cost").textContent = `${game.cost}수 사용`;
  $("pz-moves").innerHTML = legalMoves(game).map((m) => {
    const sw = m.type === "ride" ? `<span class="sw" style="background:${data.lines[m.lines[0]]?.color || "#888"}"></span>` : "";
    const tag = m.type === "ride" ? esc(m.lines.map(lineName).join(" · ")) : `${m.cost}수`;
    // 노선명이 길면 태그만 말줄임 (역 이름 칸이 좁아져 한 글자씩 세로로 줄바꿈되던 버그, QA 5장)
    return `<li><button type="button" class="${m.type}" data-to="${m.to}">${sw}${moveLabel(m)}<span class="tag" title="${tag}">${tag}</span></button></li>`;
  }).join("");
  $("pz-moves").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => step(Number(b.dataset.to))));
  $("pz-undo").disabled = game.done || !game.steps.length;
  $("pz-giveup").disabled = game.done;
  $("pz-trail").innerHTML = game.steps.map((s, i) => {
    const from = labels[game.path[i]], to = labels[game.path[i + 1]];
    return s.type === "warp"
      ? `<li class="warp"><span class="bar"></span><div>⇢ 워프 [${esc(s.portal)}] ${esc(from)} ⇢ ${esc(to)}</div></li>`
      : `<li><span class="bar" style="background:${data.lines[s.lines[0]]?.color || "#888"}"></span><div>${esc(data.clusters[game.path[i]].n)} → ${esc(data.clusters[game.path[i + 1]].n)}<div class="meta">${esc(s.lines.map(lineName).join(" · "))}</div></div></li>`;
  }).join("") || `<li class="transfer"><span></span><div>아직 출발 전</div></li>`;
  if (game.done) showResult();
  save();
}

function showResult() {
  $("pz-play").hidden = true;
  $("pz-result").hidden = false;
  $("pz-share").textContent = shareText(game, number, labels);
  $("pz-legend").hidden = false;
  const opt = optimalPath(moves, game.from, game.to);
  const optSteps = [];
  for (let i = 1; i < opt.path.length; i++) {
    const a = opt.path[i - 1], b = opt.path[i], m = moves[a].find((x) => x.to === b);
    optSteps.push(m.type === "warp" ? `⇢[${esc(m.portal)}]⇢ ${esc(labels[b])}` : esc(data.clusters[b].n));
  }
  const s = score(game);
  $("pz-optimal").innerHTML = `<p class="${s === 100 ? "pz-done" : ""}">${s === 100 ? "최적해 찾음! " : ""}${medal(s)} ${s}점</p>
    <p class="field-label" style="margin:8px 0 2px">최적 경로 (${opt.cost}수, 유일해)</p>
    <p style="margin:0;font-size:13px">${esc(labels[game.from])} → ${optSteps.join(" → ")}</p>`;
  // 최적 경로를 지도에 얇게 겹쳐 그림
  for (let i = 1; i < opt.path.length; i++) {
    const a = cLL(opt.path[i - 1]), b = cLL(opt.path[i]);
    const m = moves[opt.path[i - 1]].find((x) => x.to === opt.path[i]);
    L.polyline(m.type === "warp" ? arc(a, b) : [a, b], { color: "#12a150", weight: 3, dashArray: "2 6" }).addTo(playLayer);
  }
}

// 4차 Q4: 완료 상태에서 전체 경로(내 경로 + 최적 경로, 다른 도시 포함)가 다 보이게. 모바일은 레이아웃이 잡힌 뒤 지도 크기를
// 다시 재고 맞춘다 (초기 크기로 맞추면 수도권만 보이던 문제)
function fitAll() {
  const opt = optimalPath(moves, game.from, game.to);
  const pts = [...game.path, ...opt.path].map(cLL);
  const go = () => { map.invalidateSize(); map.fitBounds(L.latLngBounds(pts).pad(0.12), { maxZoom: 12, padding: [24, 24] }); };
  go();
  requestAnimationFrame(go);
  setTimeout(go, 300);
}

function step(to) {
  if (game.done) return;
  play(game, to);
  draw();
  if (game.done) fitAll();
  else map.panTo(cLL(to), { animate: true });
}

$("pz-undo").addEventListener("click", () => { undo(game); draw(); });
$("pz-giveup").addEventListener("click", () => { giveUp(game); draw(); fitAll(); });
$("pz-copy").addEventListener("click", async () => {
  const text = $("pz-share").textContent + `\n${location.origin}${location.pathname}`;
  try { await navigator.clipboard.writeText(text); $("pz-copied").textContent = "복사됨"; } catch {
    const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); $("pz-copied").textContent = "복사됨"; } catch { $("pz-copied").textContent = "복사 실패: 위 글을 직접 복사해"; }
    ta.remove();
  }
});

// 진행 상황 저장 (브라우저 저장소가 막혀 있으면 조용히 건너뛴다)
const KEY = `metro_portal.daily.${dateStr}`;
function save() {
  try { localStorage.setItem(KEY, JSON.stringify({ path: game.path, gaveUp: game.gaveUp })); } catch { /* 저장소 없음 */ }
}
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || "null");
  if (saved && saved.path?.[0] === game.from) {
    for (const c of saved.path.slice(1)) { if (!game.done) play(game, c); }
    if (saved.gaveUp && !game.done) giveUp(game);
  }
} catch { /* 무시 */ }

map.invalidateSize();
map.fitBounds(L.latLngBounds([cLL(game.from), cLL(game.to)]).pad(0.3), { maxZoom: 12, padding: [30, 30] });
draw();
if (game.done) fitAll();
// 테스트·디버그용 (e2e 스크립트가 읽는다)
window.__daily = { game, number, dateStr, beforeEpoch, map, labels, data };
