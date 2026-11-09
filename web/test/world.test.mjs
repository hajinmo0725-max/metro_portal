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
  assert.deepEqual(worlds.map((r) => r.key), ["tw_t1", "tw_t12", "tw_t123", "tw_t12_official", "tw_t123b", "ktj_t1", "ktj_t12", "ktj_t123"]);
  assert.equal(RULESETS[0].key, "strict");   // 4차 Q6-5: 길찾기 기본은 한국 T1
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

test("공식명만 번들(tw_t12_official)과 T1만 번들은 국가 간 포탈이 없고 판교 → 타이베이 板橋가 연결되지 않는다", () => {
  for (const key of ["tw_t1", "tw_t12_official"]) {
    const data = load(`world_${key}.json`);
    assert.equal(data.portals.filter((p) => p.x).length, 0, key);
    const labels = buildLabels(data);
    const a = resolveQuery(data, labels, "판교"), b = resolveQuery(data, labels, "타이베이 板橋");
    assert.ok(!a.error && !b.error, key);
    assert.equal(routeClusters(data, buildAdj(data, { warp: true }), a.index, b.index), null);
  }
});

test("기본 번들(현지어 라벨 포함): 판교 → 타이베이 板橋 = 국가 간 T2 워프 1회 (비용 2), 신뢰도 medium", () => {
  for (const key of ["tw_t12", "tw_t123"]) {
    const data = load(`world_${key}.json`);
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
    assert.ok(cross.every((p) => p.tier === "T2" && p.conf === "medium"));
  }
});

test("국가 표기와 국가 간 워프 스타일", () => {
  const data = load("world_tw_t12.json");
  const ctry = new Set(data.clusters.map(clusterCountry));
  assert.deepEqual([...ctry].sort(), ["KR", "TW"]);
  const x = data.portals.find((p) => p.x), same = data.portals.find((p) => !p.x);
  assert.notEqual(warpStyle(x, "#8b3dff").color, warpStyle(same, "#8b3dff").color);
  assert.equal(clusterCountry({}), "KR");
});

// 5차 T3: 한국+타이베이+도쿄 번들
test("ktj_t12: 板橋는 세 나라 공통 T2 포탈 (도쿄 板橋 · 서울 판교 · 타이베이 板橋), 판교 → 도쿄권 板橋 = 워프 한 번(2)", () => {
  const data = load("world_ktj_t12.json");
  const ban = data.portals.find((p) => p.texts.includes("板橋") && p.tier === "T2");
  assert.ok(ban && ban.x);
  assert.deepEqual([...new Set(ban.c.map((c) => clusterCountry(data.clusters[c])))].sort(), ["JP", "KR", "TW"]);
  const labels = buildLabels(data);
  const a = resolveQuery(data, labels, "판교"), b = resolveQuery(data, labels, "도쿄권 板橋");
  assert.ok(!a.error && !b.error);
  const r = routeClusters(data, buildAdj(data, { warp: true }), a.index, b.index);
  assert.equal(r.cost, 2);
  // 한국–일본(三田=삼전, 田浦=전포), 대만–일본(中山, 府中)
  const pairs = data.portals.filter((p) => p.x).map((p) => [p.texts[0], [...new Set(p.c.map((c) => clusterCountry(data.clusters[c])))].sort().join("-")]);
  for (const [t, cc] of [["三田", "JP-KR"], ["田浦", "JP-KR"], ["中山", "JP-TW"], ["府中", "JP-TW"]]) {
    assert.ok(pairs.some(([x, y]) => x.startsWith(t) && y === cc), `${t} ${cc}`);
  }
});

test("ktj_t1: T1은 언어마다 따로 — 국가 간 포탈 0, 도쿄 내부 동명이역(入谷·小川町·霞ケ関·早稲田)만", () => {
  const data = load("world_ktj_t1.json");
  assert.equal(data.portals.filter((p) => p.x).length, 0);
  const jp = data.portals.filter((p) => p.c.every((c) => clusterCountry(data.clusters[c]) === "JP")).map((p) => p.n).sort();
  assert.deepEqual(jp, ["入谷", "小川町", "早稲田", "霞ケ関"]);
  assert.ok(data.meta.attribution.includes("도쿄권"));
});
