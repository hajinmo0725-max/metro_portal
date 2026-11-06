// node --test web/test — 4차 S4 도식 노선도 로직
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildAdj, buildLabels, resolveQuery, routeClusters } from "../route.js";
import { panelSequence, portalLinks, regionIndex, routeSteps, warpTargets } from "../schematic_core.js";

const root = new URL("../", import.meta.url);
const load = (f) => JSON.parse(readFileSync(new URL(`data/${f}`, root), "utf8"));
const sch = load("schematic.json");
const kr = load("kr_strict.json");
const tw = load("world_tw_t12.json");

test("도식 권역: 수도권·부산·대구·대전·광주·타이베이, 모든 역이 번들 클러스터에 있다", () => {
  assert.deepEqual(sch.regions.map((r) => r.id), ["seoul", "busan", "daegu", "daejeon", "gwangju", "taipei"]);
  for (const r of sch.regions) {
    const ids = new Set((r.country === "TW" ? tw : kr).clusters.map((c) => c.id));
    for (const k of Object.keys(r.s)) assert.ok(ids.has(k), `${r.id} ${k}`);
    assert.deepEqual(Object.keys(r.s).sort(), Object.keys(r.g).sort());
  }
});

test("한국 클러스터는 전부 정확히 한 권역에 속한다", () => {
  const { reg } = regionIndex(sch, kr);
  assert.ok(reg.every((x) => x !== null));
  const seen = new Map();
  for (const r of sch.regions) for (const k of Object.keys(r.s)) {
    assert.ok(!seen.has(k), `${k}: ${seen.get(k)} / ${r.id}`);
    seen.set(k, r.id);
  }
});

test("MIP로 푼 권역의 도식 엣지는 전부 8방향(가로·세로·45°)", () => {
  for (const r of sch.regions) {
    if (r.engine !== "mip") continue;
    for (const [a, b] of r.e) {
      const dx = r.s[b][0] - r.s[a][0], dy = r.s[b][1] - r.s[a][1];
      const ok = Math.abs(dx) < 1e-2 || Math.abs(dy) < 1e-2 || Math.abs(Math.abs(dx) - Math.abs(dy)) < 1e-2;
      assert.ok(ok, `${r.id} ${a}-${b} (${dx.toFixed(2)}, ${dy.toFixed(2)})`);
    }
  }
});

test("같은 권역 포탈은 점선 쌍으로, 다른 권역은 목적지로", () => {
  const { reg } = regionIndex(sch, kr);
  const links = portalLinks(kr, reg);
  const same = new Map(links.filter((l) => l.same.length).map((l) => [l.name, l.same.map(([a, b]) => reg[a])]));
  assert.ok(same.get("양평").every((x) => x === "seoul"));
  assert.ok(same.get("동래").every((x) => x === "busan"));
  assert.ok(same.get("신촌").every((x) => x === "seoul"));
  const gyodae = kr.clusters.findIndex((c) => c.n === "교대" && c.city === "수도권");
  const t = warpTargets(links, gyodae);
  assert.deepEqual([...new Set(t.map((x) => x.region))].sort(), ["busan", "daegu"]);
});

test("길찾기 경로 → 패널 단계: 목동 → 부산 동래 = 수도권 → 대전 → 부산, 권역이 바뀌는 워프만 패널 이동", () => {
  const { reg } = regionIndex(sch, kr);
  const labels = buildLabels(kr);
  const a = resolveQuery(kr, labels, "목동"), b = resolveQuery(kr, labels, "부산 동래");
  const r = routeClusters(kr, buildAdj(kr, { warp: true }), a.index, b.index);
  const steps = routeSteps(kr, r, reg);
  assert.deepEqual(panelSequence(steps), ["seoul", "daejeon", "busan"]);
  const warps = steps.filter((s) => s.type === "warp");
  assert.deepEqual(warps.map((w) => w.panelChange), [false, true, true]);   // 양평(같은 수도권) → 용문(대전) → 시청(부산)
});

test("국가 간 번들: 판교 → 타이베이 板橋는 타이베이 패널로 넘어간다", () => {
  const { reg } = regionIndex(sch, tw);
  const labels = buildLabels(tw);
  const a = resolveQuery(tw, labels, "판교"), b = resolveQuery(tw, labels, "타이베이 板橋");
  const r = routeClusters(tw, buildAdj(tw, { warp: true }), a.index, b.index);
  assert.deepEqual(panelSequence(routeSteps(tw, r, reg)), ["seoul", "taipei"]);
});

test("라벨 충돌 회피: 가까운 두 역 라벨이 겹치지 않게 다른 쪽에 놓는다", async () => {
  const { placeLabels } = await import("../schematic_core.js");
  const st = [
    { p: [100, 100], dir: [0, 1], text: "가나다라", size: 10, big: false },
    { p: [100, 104], dir: [0, 1], text: "마바사아", size: 10, big: false },
  ];
  const out = placeLabels(st);
  const ov = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  assert.equal(ov(out[0].box, out[1].box), 0);
});
