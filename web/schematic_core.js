// 4차 S4: 도식 노선도 화면의 순수 로직 (브라우저·node 공용 ES 모듈). 화면 코드는 schematic.js.
// 데이터: data/schematic.json (pipeline/20_build_schematic.py, 권역별 도식 좌표 s·지리 투영 좌표 g·엣지 e)
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

// 4차 S4 보강: 라벨 충돌 회피 (탐욕). stations = [{p:[x,y], dir:[ux,uy], text, size, big}] → [{x, y, rot, anchor}]
// 후보: 선 방향에 수직 양쪽, 가로선이면 45° 회전 위·아래. 이미 놓은 라벨·역 원과 겹치는 넓이가 가장 작은 후보를 고른다.
// 큰 역(환승·종점)을 먼저 놓는다. 격자 해시로 근처 상자만 비교한다.
export function placeLabels(stations, { cell = 40, k = 1 } = {}) {
  // k: 화면 확대 배율의 역수. 라벨 간격·역 원 크기를 k배로 (확대해도 화면에서 같은 크기)
  cell *= k;
  const grid = new Map();
  const key = (i, j) => `${i},${j}`;
  const boxesNear = (b) => {
    const out = [];
    for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++)
      for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) for (const x of grid.get(key(i, j)) || []) out.push(x);
    return out;
  };
  const add = (b) => {
    for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++)
      for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) {
        const k = key(i, j);
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(b);
      }
  };
  const overlap = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  for (const s of stations) { const r = (s.big ? 6 : 4) * k; add([s.p[0] - r, s.p[1] - r, s.p[0] + r, s.p[1] + r]); }
  const order = stations.map((s, i) => i).sort((a, b) => (stations[b].big - stations[a].big) || a - b);
  const out = new Array(stations.length);
  for (const i of order) {
    const s = stations[i];
    const w = s.text.length * s.size * 0.95, h = s.size * 1.2;
    const [ux, uy] = s.dir;
    let nx = -uy, ny = ux;
    if (nx < 0) { nx = -nx; ny = -ny; }
    const horiz = Math.abs(uy) < 0.38;
    const c = [];
    const d45 = w * Math.SQRT1_2;
    if (horiz) {
      c.push({ x: s.p[0] + 3 * k, y: s.p[1] - 7 * k, rot: -45, anchor: "start", box: [s.p[0] + 2 * k, s.p[1] - 7 * k - d45 - h * 0.5, s.p[0] + 4 * k + d45, s.p[1] - 5 * k] });
      c.push({ x: s.p[0] - 3 * k, y: s.p[1] + 12 * k, rot: -45, anchor: "end", box: [s.p[0] - 4 * k - d45, s.p[1] + 8 * k, s.p[0] - 2 * k, s.p[1] + 12 * k + d45 + h * 0.5] });
    }
    for (const sg of [1, -1]) {
      const x = s.p[0] + sg * nx * 8 * k, y = s.p[1] + sg * ny * 8 * k + 3 * k;
      const anchor = sg * nx >= 0 ? "start" : "end";
      const x0 = anchor === "start" ? x : x - w;
      c.push({ x, y, rot: 0, anchor, box: [x0, y - h * 0.85, x0 + w, y + h * 0.15] });
    }
    if (!horiz) {
      c.push({ x: s.p[0] - w / 2, y: s.p[1] - 9 * k, rot: 0, anchor: "start", box: [s.p[0] - w / 2, s.p[1] - 9 * k - h * 0.85, s.p[0] + w / 2, s.p[1] - 9 * k + h * 0.15] });
    }
    let best = null;
    for (const [k, cand] of c.entries()) {
      const o = boxesNear(cand.box).reduce((acc, b) => acc + overlap(cand.box, b), 0) + k * 0.01;
      if (!best || o < best.o) best = { ...cand, o };
      if (o < 0.02 * (k + 1)) break;
    }
    add(best.box);
    out[i] = best;
  }
  return out;
}
