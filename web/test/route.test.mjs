// node --test web/test
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildAdj, routeClusters, shortestPath, describe, KIND } from "../route.js";

const root = new URL("../", import.meta.url);
const data = JSON.parse(readFileSync(new URL("data/kr_strict.json", root), "utf8"));
const expected = JSON.parse(readFileSync(new URL("data/expected_routes_strict.json", root), "utf8"));
const adjWarp = buildAdj(data, { warp: true });
const adjNo = buildAdj(data, { warp: false });
const clusterByName = (n, city) => {
  const all = data.clusters.map((c, i) => [c, i]).filter(([c]) => c.n === n && (!city || c.city.includes(city))).map(([, i]) => i);
  return all.length === 1 ? all[0] : all;
};

test("JS 길찾기 비용·경로가 Python 결과와 같다", () => {
  assert.ok(expected.length >= 80);
  for (const e of expected) {
    const r = routeClusters(data, e.warp ? adjWarp : adjNo, e.from, e.to);
    if (e.cost === null) { assert.equal(r, null); continue; }
    assert.equal(r.cost, e.cost);
    assert.deepEqual(r.path.map((p) => p.node), e.path);
  }
});

test("강남 → 부산 동래 = 교대 워프 1회, 비용 3", () => {
  const r = routeClusters(data, adjWarp, clusterByName("강남"), clusterByName("동래", "부산"));
  assert.equal(r.cost, 3);
  assert.equal(r.warps, 1);
  const warp = r.segments.find((s) => s.type === "warp");
  assert.equal(data.nodes[warp.portal].n, "교대");
});

test("워프 없이는 서울에서 부산에 못 간다", () => {
  assert.equal(routeClusters(data, adjNo, clusterByName("강남"), clusterByName("동래", "부산")), null);
});

test("0-1 BFS와 Dijkstra 비용 일치 (랜덤 쌍)", () => {
  let seed = 7;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  for (let i = 0; i < 30; i++) {
    const a = Math.floor(rnd() * data.clusters.length), b = Math.floor(rnd() * data.clusters.length);
    const x = shortestPath(adjWarp, data.clusters[a].s, data.clusters[b].s, "01bfs");
    const y = shortestPath(adjWarp, data.clusters[a].s, data.clusters[b].s, "dijkstra");
    assert.equal(x?.cost ?? null, y?.cost ?? null);
  }
});

test("경로 구간 묶기: 승차는 노선별로 연속, 워프는 in/out 한 쌍", () => {
  const r = routeClusters(data, adjWarp, clusterByName("목동"), clusterByName("동래", "부산"));
  const segs = describe(r.path, data);
  for (const s of segs) {
    if (s.type === "warp") assert.ok(Number.isInteger(s.to));
    if (s.type === "ride") assert.ok(s.nodes.length >= 2);
  }
  assert.equal(segs.filter((s) => s.type === "warp").length, r.warps);
  assert.ok(r.path.every((p, i) => i === 0 || Object.values(KIND).includes(p.kind)));
});

test("데이터 무결성: 엣지 인덱스·포탈 노드", () => {
  for (const [a, b] of data.edges) assert.ok(a < data.nodes.length && b < data.nodes.length);
  for (const p of data.portals) { assert.equal(data.nodes[p.node].portal, true); assert.ok(p.c.length >= 2); }
});

import { buildLabels, resolveQuery } from "../route.js";

test("입력 해석: 도시 접두어, 동명역, 라벨", () => {
  const labels = buildLabels(data);
  assert.equal(new Set(labels).size, labels.length);
  const r1 = resolveQuery(data, labels, "부산 동래");
  // 부산에는 동래가 둘(1·4호선 / 동해선): 도시 접두어가 있으면 둘 다 후보
  // 5차 R2: 동해선 동래는 화면에 '동래역' (원래 이름 동래역 + 다른 동래와 겹침). 입력 '동래'는 둘 다 찾는다
  assert.ok(r1.multi && r1.index.length === 2);
  assert.deepEqual(r1.index.map((i) => data.clusters[i].n).sort(), ["동래", "동래역"]);
  assert.ok(resolveQuery(data, labels, "동래").error.includes("여러 역"));
  const r0 = resolveQuery(data, labels, "광주 녹동");
  assert.equal(data.clusters[r0.index].n, "녹동");
  assert.ok(resolveQuery(data, labels, "양평").error.includes("여러 역"));
  const r2 = resolveQuery(data, labels, "강남역");
  assert.equal(data.clusters[r2.index].n, "강남");
  // 5차 R2: '역'을 떼면 도시 이름이 되는 역은 화면에 '서울역'. 입력은 '서울'·'서울역' 둘 다 된다
  const rs1 = resolveQuery(data, labels, "서울"), rs2 = resolveQuery(data, labels, "서울역");
  assert.equal(data.clusters[rs1.index].n, "서울역");
  assert.equal(rs1.index, rs2.index);
  const r3 = resolveQuery(data, labels, labels[10]);
  assert.equal(r3.index, 10);
  assert.ok(resolveQuery(data, labels, "없는역이름").error);
});
