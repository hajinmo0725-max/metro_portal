// node --test web/test — Phase 1 한국+타이베이 번들 (3차 B4)
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { buildAdj, buildLabels, resolveQuery, routeClusters } from "../route.js";
import { RULESETS, clusterCountry, warpStyle } from "../world.js";

const root = new URL("../", import.meta.url);
const load = (f) => JSON.parse(readFileSync(new URL(`data/${f}`, root), "utf8"));
const worlds = RULESETS.filter((r) => r.file.startsWith("world_"));

test("ruleset 목록의 번들 파일이 전부 있다", () => {
  for (const r of RULESETS) assert.ok(existsSync(new URL(`data/${r.file}`, root)), r.file);
  assert.deepEqual(worlds.map((r) => r.key), ["tw_t1", "tw_t12", "tw_t123", "tw_t12_label", "tw_t123_label"]);
});

for (const r of worlds) {
  test(`${r.key}: JS 길찾기가 Python 결과와 같다 (워프 비용 2·3 → Dijkstra)`, () => {
    const data = load(r.file);
    const exp = load(`expected_routes_world_${r.key}.json`);
    const adj = { true: buildAdj(data, { warp: true }), false: buildAdj(data, { warp: false }) };
    assert.ok(exp.length >= 90);
    for (const e of exp) {
      const res = routeClusters(data, adj[e.warp], e.from, e.to);
      if (e.cost === null) { assert.equal(res, null); continue; }
      assert.equal(res.cost, e.cost);
      assert.deepEqual(res.path.map((p) => p.node), e.path);
    }
  });
}

test("공식명만 쓰는 번들은 국가 간 포탈이 없고 판교 → 타이베이 板橋가 연결되지 않는다", () => {
  for (const key of ["tw_t1", "tw_t12", "tw_t123"]) {
    const data = load(`world_${key}.json`);
    assert.equal(data.portals.filter((p) => p.x).length, 0, key);
    const labels = buildLabels(data);
    const a = resolveQuery(data, labels, "판교"), b = resolveQuery(data, labels, "타이베이 板橋");
    assert.ok(!a.error && !b.error, key);
    assert.equal(routeClusters(data, buildAdj(data, { warp: true }), a.index, b.index), null);
  }
});

test("참고 번들: 판교 → 타이베이 板橋 = 국가 간 T2 워프 1회 (비용 2)", () => {
  const data = load("world_tw_t12_label.json");
  const labels = buildLabels(data);
  const a = resolveQuery(data, labels, "판교"), b = resolveQuery(data, labels, "타이베이 板橋");
  const r = routeClusters(data, buildAdj(data, { warp: true }), a.index, b.index);
  assert.equal(r.cost, 2);
  assert.equal(r.warps, 1);
  const w = r.segments.find((s) => s.type === "warp");
  assert.equal(w.tier, "T2");
  assert.notEqual(data.nodes[w.from].co, data.nodes[w.to].co);
  const cross = data.portals.filter((p) => p.x);
  assert.equal(cross.length, 6);
  assert.ok(cross.every((p) => p.tier === "T2"));
});

test("국가 표기와 국가 간 워프 스타일", () => {
  const data = load("world_tw_t12_label.json");
  const ctry = new Set(data.clusters.map(clusterCountry));
  assert.deepEqual([...ctry].sort(), ["KR", "TW"]);
  const x = data.portals.find((p) => p.x), same = data.portals.find((p) => !p.x);
  assert.notEqual(warpStyle(x, "#8b3dff").color, warpStyle(same, "#8b3dff").color);
  assert.equal(clusterCountry({}), "KR");
});
