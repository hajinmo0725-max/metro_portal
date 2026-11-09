// 워프 포함 길찾기 (브라우저·node 공용 ES 모듈).
// 알고리즘은 metro_portal/route.py와 같다: 비용이 0/1뿐이면 0-1 BFS, 아니면 Dijkstra.
// 그래프(인접 리스트 순서 포함)는 pipeline/06_build_web_data.py가 Python 그래프를 그대로 내보낸 것이다.

export const KIND = { RIDE: 0, TRANSFER: 1, WARP_IN: 2, WARP_OUT: 3 };

export function buildAdj(data, { warp = true } = {}) {
  const adj = data.nodes.map(() => []);
  for (const [a, b, c, k, m] of data.edges) {
    if (!warp && (k === KIND.WARP_IN || k === KIND.WARP_OUT)) continue;
    adj[a].push([b, c, k, m]);
  }
  return adj;
}

function isZeroOne(adj) {
  for (const outs of adj) for (const e of outs) if (e[1] !== 0 && e[1] !== 1) return false;
  return true;
}

class Deque {
  constructor(items = []) { this.front = []; this.back = items.slice(); this.head = 0; }
  get size() { return this.front.length + this.back.length - this.head; }
  pushBack(x) { this.back.push(x); }
  pushFront(x) { this.front.push(x); }
  popFront() { return this.front.length ? this.front.pop() : this.back[this.head++]; }
}

class Heap { // (cost, counter) 사전순 최소 힙
  constructor() { this.a = []; }
  get size() { return this.a.length; }
  less(i, j) { const x = this.a[i], y = this.a[j]; return x[0] < y[0] || (x[0] === y[0] && x[1] < y[1]); }
  push(v) { const a = this.a; a.push(v); let i = a.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (!this.less(i, p)) break; [a[i], a[p]] = [a[p], a[i]]; i = p; } }
  pop() {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) { a[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < a.length && this.less(l, m)) m = l; if (r < a.length && this.less(r, m)) m = r; if (m === i) break; [a[i], a[m]] = [a[m], a[i]]; i = m; } }
    return top;
  }
}

// sources/targets: 노드 인덱스 배열. 반환: {cost, path:[{node, kind, meta}]} 또는 null
export function shortestPath(adj, sources, targets, algorithm = "auto") {
  const tset = new Set(targets);
  const src = [...sources].sort((a, b) => a - b);
  if (algorithm === "auto") algorithm = isZeroOne(adj) ? "01bfs" : "dijkstra";
  const dist = new Map(), prev = new Map(), done = new Set();
  for (const s of src) { dist.set(s, 0); prev.set(s, null); }
  const relax = (x, d, y, c, k, m, push) => {
    const nd = d + c;
    if (nd < (dist.has(y) ? dist.get(y) : Infinity)) { dist.set(y, nd); prev.set(y, [x, k, m]); push(y, nd, c); }
  };
  if (algorithm === "01bfs") {
    const dq = new Deque(src);
    while (dq.size) {
      const x = dq.popFront();
      if (done.has(x)) continue;
      done.add(x);
      if (tset.has(x)) return { cost: dist.get(x), path: unwind(prev, x) };
      const d = dist.get(x);
      for (const [y, c, k, m] of adj[x]) relax(x, d, y, c, k, m, (yy, nd, cc) => (cc === 0 ? dq.pushFront(yy) : dq.pushBack(yy)));
    }
    return null;
  }
  const pq = new Heap();
  let counter = 0;
  for (const s of src) pq.push([0, counter++, s]);
  while (pq.size) {
    const [d, , x] = pq.pop();
    if (done.has(x)) continue;
    done.add(x);
    if (tset.has(x)) return { cost: d, path: unwind(prev, x) };
    for (const [y, c, k, m] of adj[x]) relax(x, d, y, c, k, m, (yy, nd) => pq.push([nd, counter++, yy]));
  }
  return null;
}

function unwind(prev, x) {
  const out = [];
  while (prev.get(x) !== null) { const [p, k, m] = prev.get(x); out.push({ node: x, kind: k, meta: m }); x = p; }
  out.push({ node: x, kind: "start", meta: null });
  return out.reverse();
}

// 경로 → 구간 목록 (ride/transfer/warp). Python describe()와 같은 묶음 규칙
export function describe(path, data) {
  const segs = [];
  for (let i = 1; i < path.length; i++) {
    const { node, kind, meta } = path[i];
    const prevNode = path[i - 1].node;
    if (kind === KIND.RIDE) {
      const last = segs[segs.length - 1];
      if (last && last.type === "ride" && last.line === meta) last.nodes.push(node);
      else segs.push({ type: "ride", line: meta, nodes: [prevNode, node] });
    } else if (kind === KIND.TRANSFER) {
      const last = segs[segs.length - 1];
      if (last && last.type === "transfer") last.to = node; else segs.push({ type: "transfer", from: prevNode, to: node });
    } else if (kind === KIND.WARP_IN) {
      segs.push({ type: "warp", portal: node, from: prevNode, tier: meta });
    } else if (kind === KIND.WARP_OUT) {
      segs[segs.length - 1].to = node;
    }
  }
  return segs;
}

export function summarize(path) {
  let rides = 0, warps = 0;
  for (const p of path) { if (p.kind === KIND.RIDE) rides++; if (p.kind === KIND.WARP_IN) warps++; }
  return { rides, warps };
}

// 클러스터 인덱스(또는 인덱스 배열: 같은 도시 동명역 여러 개) → 경로
export function routeClusters(data, adj, fromCluster, toCluster) {
  const nodesOf = (c) => [].concat(c).flatMap((i) => data.clusters[i].s);
  const r = shortestPath(adj, nodesOf(fromCluster), nodesOf(toCluster));
  if (!r) return null;
  return { ...r, ...summarize(r.path), segments: describe(r.path, data) };
}

// 사용자 입력 → 클러스터 인덱스. Python StationIndex.resolve와 같은 규칙(앞 토큰이 도시명이면 필터)에
// 정규화는 표시용 최소 규칙(공백 정리, 끝의 '역' 제거)만 쓴다. 클러스터 이름은 이미 ruleset 정규화 결과다.
export function clusterLabel(c) {
  return `${c.n} · ${c.city}${c.lines.length ? " · " + c.lines.join("/") : ""}`;
}

export function buildLabels(data) {
  const seen = new Map();
  const labels = data.clusters.map((c) => clusterLabel(c));
  labels.forEach((l, i) => seen.set(l, (seen.get(l) || []).concat(i)));
  return labels.map((l, i) => (seen.get(l).length > 1 ? `${l} (${data.clusters[i].id})` : l));
}

const stripSuffix = (s) => (s.length > 1 && s.endsWith("역") ? s.slice(0, -1) : s);

export function resolveQuery(data, labels, text) {
  const t = (text || "").replace(/\s+/g, " ").trim();
  if (!t) return { error: "역 이름을 입력해" };
  const exact = labels.indexOf(t);
  if (exact >= 0) return { index: exact };
  const parts = t.split(" ");
  let city = null, name = t;
  if (parts.length >= 2) { city = parts[0]; name = parts.slice(1).join(" "); }
  const key = stripSuffix(name.replace(/\(.*?\)/g, "").trim());
  // 5차 R2: 표시 이름이 "서울역"처럼 '역'을 유지해도 입력 "서울"·"서울역" 둘 다 찾는다 (매칭 키 = 접미사 뗀 이름)
  let cands = data.clusters.map((c, i) => [c, i]).filter(([c]) => c.n === key || stripSuffix(c.n) === key);
  if (city) cands = cands.filter(([c, i]) => c.city.includes(city) || data.clusters[i].s.some((n) => (data.nodes[n].ct || "").includes(city)));
  if (cands.length === 1) return { index: cands[0][1] };
  if (cands.length === 0) return { error: `역을 찾지 못함: ${t}` };
  // 도시 접두어까지 줬는데 같은 도시에 같은 이름 역이 여럿이면(부산 동래) 전부를 후보로 쓴다 (Python과 같은 규칙)
  if (city && new Set(cands.map(([c]) => c.city)).size === 1) return { index: cands.map(([, i]) => i), multi: true };
  return { error: `여러 역이 일치함: ${cands.map(([, i]) => labels[i]).join(", ")}. 목록에서 골라` , options: cands.map(([, i]) => i) };
}
