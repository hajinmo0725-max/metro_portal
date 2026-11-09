// node --test web/test — 데일리 퍼즐 로직
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildMoves, clusterDistances, dailyPick, daysBetween, giveUp, kstDateString, legalMoves, medal, newGame,
  optimalPath, play, rideDirections, score, shareText, undo, validDateString } from "../puzzle.js";
import { buildAdj, routeClusters } from "../route.js";

const root = new URL("../", import.meta.url);
const data = JSON.parse(readFileSync(new URL("data/kr_strict.json", root), "utf8"));
const pz = JSON.parse(readFileSync(new URL("data/puzzles.json", root), "utf8"));
const moves = buildMoves(data);
const labels = data.clusters.map((c) => `${c.city} ${c.n}`);
const cix = new Map(data.clusters.map((c, i) => [c.id, i]));

test("서울 시간 날짜: UTC 15시 이후는 다음 날", () => {
  assert.equal(kstDateString(new Date("2026-11-05T14:59:00Z")), "2026-11-05");
  assert.equal(kstDateString(new Date("2026-11-05T15:00:00Z")), "2026-11-06");
  assert.equal(daysBetween("2026-11-05", "2026-11-05"), 0);
  assert.equal(daysBetween("2026-11-05", "2027-11-05"), 365);
  assert.equal(daysBetween("2026-11-05", "2026-11-04"), -1);
});

test("데일리 선택: 날짜가 같으면 같은 퍼즐, 한 주기 동안 중복 없음, 회차 번호", () => {
  const a = dailyPick(pz, "2026-11-05"), b = dailyPick(pz, "2026-11-05");
  assert.equal(a.puzzle.id, b.puzzle.id);
  assert.equal(a.number, 1);
  assert.equal(a.puzzle.id, pz.daily_order[0]);
  const n = pz.daily_order.length;
  const ids = new Set();
  for (let d = 0; d < n; d++) {
    const date = new Date(Date.parse("2026-11-05T00:00:00Z") + d * 86400000).toISOString().slice(0, 10);
    ids.add(dailyPick(pz, date).puzzle.id);
  }
  assert.equal(ids.size, n);
  // 주기 이후 반복, epoch 이전 날짜도 동작
  const later = new Date(Date.parse("2026-11-05T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);
  assert.equal(dailyPick(pz, later).puzzle.id, a.puzzle.id);
  assert.ok(dailyPick(pz, "2026-01-01").puzzle);
});

test("4차 Q1: 출시일 이전 날짜는 #0·음수 회차 대신 1회차 (beforeEpoch), 잘못된 날짜 문자열 거부", () => {
  for (const d of ["2026-11-04", "2020-01-01"]) {
    const r = dailyPick(pz, d);
    assert.equal(r.number, 1, d);
    assert.equal(r.beforeEpoch, true);
    assert.equal(r.puzzle.id, pz.daily_order[0]);
    assert.equal(r.date, pz.daily_epoch);
  }
  assert.equal(dailyPick(pz, "2026-11-06").beforeEpoch, false);
  assert.ok(validDateString("2026-11-05") && !validDateString("abc") && !validDateString("2026-02-30") && !validDateString(""));
});

test("4차 Q3: 이동 후보는 노선·방면 기준 고정 정렬, 방면 표시, 포탈역 표시", () => {
  const sindorim = data.clusters.findIndex((c) => c.n === "신도림");
  const ms = moves[sindorim];
  const rides = ms.filter((m) => m.type === "ride");
  assert.ok(rides.length >= 4 && rides.every((m) => m.dir !== null), "신도림 승차 후보에 방면이 다 있다");
  for (let i = 1; i < rides.length; i++) assert.ok((rides[i - 1].dirLine ?? rides[i - 1].lines[0]) <= (rides[i].dirLine ?? rides[i].lines[0]));
  assert.ok(ms.findIndex((m) => m.type === "warp") === -1 || ms.findIndex((m) => m.type === "warp") >= rides.length);
  // 같은 노선의 두 방향은 서로 다른 방면 (종점)
  const l2 = rides.filter((m) => data.lines[m.dirLine].name.startsWith("2호선") && !data.lines[m.dirLine].name.includes("지선"));
  assert.ok(l2.length >= 2 && new Set(l2.map((m) => m.dir)).size === l2.length);
  // 정렬은 매 수 같다: 같은 역이면 같은 순서
  assert.deepEqual(buildMoves(data)[sindorim].map((m) => m.to), ms.map((m) => m.to));
  // 포탈역 표시: 강남 → 교대(수도권)는 포탈 '교대'가 있는 역
  const gangnam = data.clusters.findIndex((c) => c.n === "강남");
  const toGyodae = moves[gangnam].find((m) => data.clusters[m.to].n === "교대");
  assert.deepEqual(toGyodae.toPortal, ["교대"]);
  // 단방향 순환(응암)은 정방향 방면만
  const dirs = rideDirections(data);
  assert.ok(dirs.size > 1000);
});

test("4차 Q3: 공유 문구에 되돌리기 횟수", () => {
  const { puzzle, number } = dailyPick(pz, "2026-11-05");
  const g = newGame(data, moves, puzzle);
  const first = legalMoves(g)[0];
  play(g, first.to); undo(g); play(g, first.to); undo(g);
  assert.equal(g.undos, 2);
  const opt = optimalPath(moves, g.from, g.to);
  for (const c of opt.path.slice(1)) play(g, c);
  assert.ok(shareText(g, number, labels).includes("↶ 되돌리기 2회"));
  assert.equal(score(g), 100);   // 되돌리기는 점수에 영향 없음
});

test("이동 그래프: 승차는 인접역, 워프는 같은 포탈, 환승은 수가 아님", () => {
  const gangnam = data.clusters.findIndex((c) => c.n === "강남");
  const gyodae = data.clusters.findIndex((c) => c.n === "교대" && c.city === "수도권");
  // 5차 R2: 부산 교대는 동해선 레코드가 '교대역'이고 서울 교대와 이름이 겹쳐서 화면에 '역'을 유지한다
  const gyodaeBusan = data.clusters.findIndex((c) => c.n === "교대역" && c.city === "부산");
  assert.ok(moves[gangnam].some((m) => m.to === gyodae && m.type === "ride" && m.cost === 1));
  const w = moves[gyodae].find((m) => m.to === gyodaeBusan);
  assert.equal(w.type, "warp");
  assert.equal(w.portal, "교대");
  for (const [i, ms] of moves.entries()) for (const m of ms) assert.notEqual(m.to, i);
});

test("클러스터 단위 최단 비용 = 역 수준 길찾기(route.js) 비용 = 퍼즐 cost_warp", () => {
  const adjW = buildAdj(data, { warp: true }), adjN = buildAdj(data, { warp: false });
  for (const p of pz.puzzles) {
    const s = cix.get(p.from), t = cix.get(p.to);
    const { dist } = clusterDistances(moves, s);
    assert.equal(dist[t], p.cost_warp, p.id);
    assert.equal(routeClusters(data, adjW, s, t).cost, p.cost_warp, p.id);
    const rn = routeClusters(data, adjN, s, t);
    assert.equal(rn ? rn.cost : null, p.cost_no_warp, p.id);
  }
});

test("최적 경로를 따라가면 100점, 이모지 결과", () => {
  const { puzzle, number } = dailyPick(pz, "2026-11-05");
  const g = newGame(data, moves, puzzle);
  const opt = optimalPath(moves, g.from, g.to);
  for (const c of opt.path.slice(1)) play(g, c);
  assert.ok(g.done && !g.gaveUp);
  assert.equal(g.cost, puzzle.cost_warp);
  assert.equal(score(g), 100);
  const txt = shareText(g, number, labels);
  assert.match(txt, /^지하철 워프 데일리 #1 /);
  assert.ok(txt.includes("💯 100점"));
  assert.equal([...txt.split("\n")[2].matchAll(/🌀/gu)].length, puzzle.warps);
});

test("돌아가면 점수가 깎이고, 되돌리기·포기 동작", () => {
  const p = pz.puzzles.find((x) => x.kind === "shortcut");
  const g = newGame(data, moves, p);
  // 일부러 한 번 왕복한 뒤 최적 경로
  const first = legalMoves(g).find((m) => m.type === "ride");
  play(g, first.to); play(g, g.from);
  assert.equal(g.cost, 2);
  play(g, first.to); undo(g);
  assert.equal(g.cost, 2);
  const opt = optimalPath(moves, g.from, g.to);
  for (const c of opt.path.slice(1)) play(g, c);
  assert.equal(g.cost, p.cost_warp + 2);
  assert.equal(score(g), Math.round((100 * p.cost_warp) / (p.cost_warp + 2)));
  assert.ok(score(g) < 100 && medal(score(g)) !== "💯");
  assert.throws(() => play(g, g.from));
  const g2 = newGame(data, moves, p);
  giveUp(g2);
  assert.equal(score(g2), 0);
  assert.ok(shareText(g2, 3, labels).includes("포기"));
});

test("수 제한: 최적의 3배+10 비용을 넘기면 자동 종료", () => {
  const p = pz.puzzles[0];
  const g = newGame(data, moves, p);
  const a = g.from, b = legalMoves(g).find((m) => m.type === "ride" && m.to !== g.to).to;
  let i = 0;
  while (!g.done && i++ < 500) play(g, g.path[g.path.length - 1] === a ? b : a);
  assert.ok(g.done && g.gaveUp && g.cost >= g.maxCost);
});

test("3차 A2: 응암순환 단방향 — 퍼즐 이동·길찾기 모두 역방향 승차 불가", () => {
  const loopSeq = data.lines.flatMap((l) => l.seqs).find((s) => s.id === "eungam-loop");
  assert.ok(loopSeq && loopSeq.directed && loopSeq.circular);
  const cl = (name) => data.clusters.findIndex((c) => c.n === name && c.city === "수도권");
  const eungam = cl("응암"), yeokchon = cl("역촌"), gusan = cl("구산");
  const rideTo = (from) => moves[from].filter((m) => m.type === "ride").map((m) => m.to);
  assert.ok(rideTo(eungam).includes(yeokchon));
  assert.ok(!rideTo(yeokchon).includes(eungam));
  assert.ok(rideTo(gusan).includes(eungam));
  assert.ok(!rideTo(eungam).includes(gusan));
  // 역촌 → 응암: 워프 없이 4수 (역촌→불광, 3호선 불광→연신내, 연신내→구산→응암), 반대는 1수
  const adjNo = buildAdj(data, { warp: false });
  assert.equal(routeClusters(data, adjNo, eungam, yeokchon).cost, 1);
  assert.equal(routeClusters(data, adjNo, yeokchon, eungam).cost, 4);
  assert.equal(clusterDistances(moves, yeokchon).dist[eungam], 4);
});
