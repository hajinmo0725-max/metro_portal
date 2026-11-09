// 4차 S4: 도식 노선도 화면의 순수 로직 (브라우저·node 공용 ES 모듈). 화면 코드는 schematic.js.
// 데이터: data/schematic.json (pipeline/21_build_schematic_web.py가 풀이 캐시에서 만든다, 권역별 도식 좌표 s·지리 투영 좌표 g·엣지 e)
//        + 길찾기 번들 (kr_strict.json 또는 world_<rs>.json: clusters·portals·nodes·lines)

// 클러스터 인덱스 → 권역 id. 도식 좌표가 있는 권역을 우선 쓰고, 없으면 클러스터 city로 찾는다
export function regionIndex(sch, data) {
  const byId = new Map(data.clusters.map((c, i) => [c.id, i]));
  const byCity = new Map(sch.regions.map((r) => [r.city, r.id]));
  const reg = new Array(data.clusters.length).fill(null);
  for (const r of sch.regions) {
    for (const cid of Object.keys(r.s)) {
      const i = byId.get(cid);
      if (i !== undefined && reg[i] === null) reg[i] = r.id;
    }
  }
  data.clusters.forEach((c, i) => {
    if (reg[i] !== null) return;
    for (const city of String(c.city || "").split("/")) if (byCity.has(city)) { reg[i] = byCity.get(city); break; }
  });
  return { reg, byId };
}

// 포탈별 연결: 같은 권역 안 쌍(점선으로 잇는다)과 다른 권역 목적지(아이콘 + 패널 이동)
export function portalLinks(data, reg) {
  return data.portals.map((p) => {
    const members = p.c.map((c) => ({ c, region: reg[c] }));
    const same = [];
    for (let i = 0; i < members.length; i++) for (let j = i + 1; j < members.length; j++) {
      if (members[i].region && members[i].region === members[j].region) same.push([members[i].c, members[j].c]);
    }
    return { id: p.id, name: p.n, tier: p.tier, cost: p.cost, cross: !!p.x, conf: p.conf || "high", members, same };
  });
}

// 클러스터 c에서 갈 수 있는 워프 목적지 (다른 클러스터들, 권역 포함)
export function warpTargets(links, c) {
  const out = [];
  for (const l of links) {
    if (!l.members.some((m) => m.c === c)) continue;
    for (const m of l.members) if (m.c !== c) out.push({ portal: l.name, tier: l.tier, cost: l.cost, cross: l.cross, c: m.c, region: m.region });
  }
  return out.sort((a, b) => (a.region === b.region ? a.c - b.c : String(a.region) < String(b.region) ? -1 : 1));
}

// 길찾기 결과(route.js routeClusters) → 패널 단계. ride는 클러스터열로, warp는 권역이 바뀌면 panelChange
export function routeSteps(data, route, reg) {
  const steps = [];
  for (const s of route.segments) {
    if (s.type === "ride") {
      const cs = [];
      for (const n of s.nodes) { const c = data.nodes[n].c; if (cs[cs.length - 1] !== c) cs.push(c); }
      steps.push({ type: "ride", line: s.line, clusters: cs, region: reg[cs[0]] });
    } else if (s.type === "warp") {
      const a = data.nodes[s.from].c, b = data.nodes[s.to].c;
      steps.push({ type: "warp", portal: data.nodes[s.portal].n, tier: s.tier, from: a, to: b,
                   fromRegion: reg[a], toRegion: reg[b], panelChange: reg[a] !== reg[b] });
    }
  }
  return steps;
}

// 경로가 지나는 권역 순서 (연속 중복 제거)
export function panelSequence(steps) {
  const out = [];
  for (const s of steps) {
    const rs = s.type === "ride" ? [s.region] : [s.fromRegion, s.toRegion];
    for (const r of rs) if (r && out[out.length - 1] !== r) out.push(r);
  }
  return out;
}

// 좌표 집합을 화면 상자에 맞추는 변환 (y는 북쪽이 위)
export function fitTransform(points, width, height, pad = 40) {
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
  const w = Math.max(maxx - minx, 1e-9), h = Math.max(maxy - miny, 1e-9);
  const sc = Math.min((width - 2 * pad) / w, (height - 2 * pad) / h);
  const ox = (width - w * sc) / 2, oy = (height - h * sc) / 2;
  return (p) => [ox + (p[0] - minx) * sc, oy + (maxy - p[1]) * sc];
}

// 두 좌표계 사이 보간 (지리 ↔ 도식 전환 애니메이션)
export function lerpPoint(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

// 엣지 위 노선별 평행 오프셋 (화면 좌표, 노선 n개를 gap 간격으로)
export function offsetSegment(pa, pb, k, n, gap = 4.5) {
  const dx = pb[0] - pa[0], dy = pb[1] - pa[1], L = Math.hypot(dx, dy) || 1;
  const nx = -dy / L, ny = dx / L, off = (k - (n - 1) / 2) * gap;
  return [[pa[0] + nx * off, pa[1] + ny * off], [pb[0] + nx * off, pb[1] + ny * off]];
}

// 4차 S4 보강 → 5차 R4: 라벨 충돌 회피 (탐욕). stations = [{p:[x,y], dir:[ux,uy], text, size, big}] → [{x, y, rot, anchor, box, cost}]
// 후보: 선 방향에 수직 양쪽, 가로선이면 45° 회전 위·아래 (4차) + 8방위(동·서·남·북·대각) (5차).
// 비용 = 이미 놓은 라벨·역 원과 겹치는 넓이 + segW × 라벨 안을 지나는 노선 선분 길이 (5차: 라벨이 선 위에 걸치는 문제) + 후보 순번 × 0.01.
// segments = [[x1, y1, x2, y2], ...] (화면 좌표, 평행 오프셋 포함). 큰 역(환승·종점)을 먼저 놓는다. 격자 해시로 근처만 비교한다.
export function labelGeom(c) {
  // 라벨 사각형 = 원점(ox, oy)에서 rot만큼 돌린 좌표계의 [x0, y0, x1, y1]. box는 화면 좌표 외접 사각형(격자·라벨끼리 겹침용)
  const { ox, oy, rot, r } = c;
  if (!rot) return [r[0] + ox, r[1] + oy, r[2] + ox, r[3] + oy];
  const a = (rot * Math.PI) / 180, ca = Math.cos(a), sa = Math.sin(a);
  const pts = [[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]].map(([x, y]) => [ox + x * ca - y * sa, oy + x * sa + y * ca]);
  return [Math.min(...pts.map((q) => q[0])), Math.min(...pts.map((q) => q[1])), Math.max(...pts.map((q) => q[0])), Math.max(...pts.map((q) => q[1]))];
}

// 선분이 라벨 사각형 안을 지나는 길이 (Liang–Barsky 클리핑, 회전 라벨은 라벨 좌표계로 돌려서)
export function segInLabel(c, sg) {
  let [x1, y1, x2, y2] = sg;
  x1 -= c.ox; y1 -= c.oy; x2 -= c.ox; y2 -= c.oy;
  if (c.rot) {
    const a = (-c.rot * Math.PI) / 180, ca = Math.cos(a), sa = Math.sin(a);
    [x1, y1, x2, y2] = [x1 * ca - y1 * sa, x1 * sa + y1 * ca, x2 * ca - y2 * sa, x2 * sa + y2 * ca];
  }
  const [rx0, ry0, rx1, ry1] = c.r;
  let t0 = 0, t1 = 1;
  const dx = x2 - x1, dy = y2 - y1;
  for (const [p, q] of [[-dx, x1 - rx0], [dx, rx1 - x1], [-dy, y1 - ry0], [dy, ry1 - y1]]) {
    if (Math.abs(p) < 1e-12) { if (q < 0) return 0; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return 0; if (t > t0) t0 = t; } else { if (t < t0) return 0; if (t < t1) t1 = t; }
  }
  return t1 > t0 ? (t1 - t0) * Math.hypot(dx, dy) : 0;
}

export function placeLabels(stations, { cell = 40, k = 1, segments = [], segW = null } = {}) {
  // k: 화면 확대 배율의 역수. 라벨 간격·역 원 크기를 k배로 (확대해도 화면에서 같은 크기)
  cell *= k;
  const grid = new Map(), sgrid = new Map();
  const key = (i, j) => `${i},${j}`;
  const cellsOf = (b, f) => {
    for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++)
      for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) f(key(i, j));
  };
  const near = (g, b) => { const out = new Set(); cellsOf(b, (kk) => { for (const x of g.get(kk) || []) out.add(x); }); return [...out]; };
  const put = (g, b, x) => cellsOf(b, (kk) => { if (!g.has(kk)) g.set(kk, []); g.get(kk).push(x); });
  const overlap = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  for (const s of stations) { const r = (s.big ? 6 : 4) * k; const b = [s.p[0] - r, s.p[1] - r, s.p[0] + r, s.p[1] + r]; put(grid, b, b); }
  segments.forEach((sg) => put(sgrid, [Math.min(sg[0], sg[2]), Math.min(sg[1], sg[3]), Math.max(sg[0], sg[2]), Math.max(sg[1], sg[3])], sg));
  const order = stations.map((s, i) => i).sort((a, b) => (stations[b].big - stations[a].big) || a - b);
  const out = new Array(stations.length);
  for (const i of order) {
    const s = stations[i];
    const w = s.text.length * s.size * 0.95, h = s.size * 1.2;
    const sw = segW ?? 0.45 * h;
    const [ux, uy] = s.dir;
    let nx = -uy, ny = ux;
    if (nx < 0) { nx = -nx; ny = -ny; }
    const horiz = Math.abs(uy) < 0.38;
    const [px, py] = s.p;
    const c = [];
    // 회전 후보 (가로선): 원점 = 글자 기준점, 라벨 좌표계에서 [0, -0.85h, w, 0.15h] (anchor start) / [-w, ...] (end)
    if (horiz) {
      c.push({ x: px + 3 * k, y: py - 7 * k, rot: -45, anchor: "start", ox: px + 3 * k, oy: py - 7 * k, r: [0, -h * 0.85, w, h * 0.15] });
      c.push({ x: px - 3 * k, y: py + 12 * k, rot: -45, anchor: "end", ox: px - 3 * k, oy: py + 12 * k, r: [-w, -h * 0.85, 0, h * 0.15] });
    }
    for (const sg of [1, -1]) {
      const x = px + sg * nx * 8 * k, y = py + sg * ny * 8 * k + 3 * k;
      const anchor = sg * nx >= 0 ? "start" : "end";
      c.push({ x, y, rot: 0, anchor, ox: x, oy: y, r: anchor === "start" ? [0, -h * 0.85, w, h * 0.15] : [-w, -h * 0.85, 0, h * 0.15] });
    }
    if (!horiz) c.push({ x: px - w / 2, y: py - 9 * k, rot: 0, anchor: "start", ox: px - w / 2, oy: py - 9 * k, r: [0, -h * 0.85, w, h * 0.15] });
    // 5차: 8방위 후보 (역에서 8k 떨어진 곳)
    const d = 8 * k, dd = 6 * k;
    for (const [x, y, anchor, r] of [
      [px + d, py + h * 0.35, "start", [0, -h * 0.85, w, h * 0.15]], [px - d, py + h * 0.35, "end", [-w, -h * 0.85, 0, h * 0.15]],
      [px - w / 2, py - d, "start", [0, -h * 0.85, w, h * 0.15]], [px - w / 2, py + d + h * 0.7, "start", [0, -h * 0.85, w, h * 0.15]],
      [px + dd, py - dd, "start", [0, -h * 0.85, w, h * 0.15]], [px - dd, py - dd, "end", [-w, -h * 0.85, 0, h * 0.15]],
      [px + dd, py + dd + h * 0.7, "start", [0, -h * 0.85, w, h * 0.15]], [px - dd, py + dd + h * 0.7, "end", [-w, -h * 0.85, 0, h * 0.15]],
    ]) c.push({ x, y, rot: 0, anchor, ox: x, oy: y, r });
    let best = null;
    for (const [j, cand] of c.entries()) {
      cand.box = labelGeom(cand);
      let o = near(grid, cand.box).reduce((acc, b) => acc + overlap(cand.box, b), 0);
      if (segments.length) o += sw * near(sgrid, cand.box).reduce((acc, sg) => acc + segInLabel(cand, sg), 0);
      o += j * 0.01;
      if (!best || o < best.cost) best = { ...cand, cost: o };
      if (o < 0.02 * (j + 1)) break;
    }
    put(grid, best.box, best.box);
    out[i] = best;
  }
  return out;
}

// 5차 R4: 라벨 배치 품질 지표 — 선분이 지나는 라벨 수(라벨 안 길이 > minLen), 서로 겹치는 라벨 쌍 수
export function labelStats(placed, segments, { minLen = 2 } = {}) {
  let onLine = 0, pairs = 0;
  for (const c of placed) if (segments.some((sg) => segInLabel(c, sg) > minLen)) onLine++;
  for (let i = 0; i < placed.length; i++) for (let j = i + 1; j < placed.length; j++) {
    const a = placed[i].box, b = placed[j].box;
    if (Math.min(a[2], b[2]) - Math.max(a[0], b[0]) > 0.5 && Math.min(a[3], b[3]) - Math.max(a[1], b[1]) > 0.5) pairs++;
  }
  return { labels: placed.length, on_line: onLine, overlap_pairs: pairs };
}
