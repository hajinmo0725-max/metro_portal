// 데일리 퍼즐 로직 (브라우저·node 공용 ES 모듈). 화면 코드는 daily.js.
// 규칙: 클러스터(물리적 역) 단위로 한 수씩 이동한다. 승차 = 인접역 1개(비용 ride), 워프 = 같은 이름 포탈로(비용 = 포탈 비용).
// 환승은 같은 클러스터 안이라 수가 아니다. 점수 = 최적 비용 / 내 비용 × 100.
// 퍼즐 목록·데일리 순서는 pipeline/10_build_game_data.py가 만든 data/puzzles.json.

import { KIND } from "./route.js";

const DAY_MS = 86400000;

// 서울 시간 기준 날짜 문자열 (YYYY-MM-DD). 모두가 같은 날 같은 퍼즐을 보게 한다
export function kstDateString(date = new Date()) {
  const kst = new Date(date.getTime() + 9 * 3600000);
  return kst.toISOString().slice(0, 10);
}

export function daysBetween(epoch, dateStr) {
  return Math.round((Date.parse(`${dateStr}T00:00:00Z`) - Date.parse(`${epoch}T00:00:00Z`)) / DAY_MS);
}

// 날짜 → 퍼즐. daily_order(시드 고정 셔플)를 날짜 차이로 순환한다. number = 1번부터 세는 회차
export function dailyPick(pz, dateStr) {
  const d = daysBetween(pz.daily_epoch, dateStr);
  const n = pz.daily_order.length;
  const id = pz.daily_order[((d % n) + n) % n];
  return { number: d + 1, puzzle: pz.puzzles.find((p) => p.id === id) };
}

// 클러스터 단위 이동 그래프: moves[c] = [{to, cost, type:'ride'|'warp', label}]
export function buildMoves(data) {
  const C = data.clusters.length;
  const ride = data.meta.costs.ride;
  const seen = Array.from({ length: C }, () => new Map());
  for (const [a, b, , k, m] of data.edges) {
    if (k !== KIND.RIDE) continue;
    const ca = data.nodes[a].c, cb = data.nodes[b].c;
    if (ca === cb) continue;
    const mv = seen[ca].get(cb) || { to: cb, cost: ride, type: "ride", lines: new Set() };
    mv.lines.add(m);
    seen[ca].set(cb, mv);
  }
  for (const p of data.portals) {
    for (const a of p.c) for (const b of p.c) {
      if (a === b || seen[a].has(b)) continue;
      seen[a].set(b, { to: b, cost: p.cost, type: "warp", portal: p.n, lines: new Set() });
    }
  }
  return seen.map((m) => [...m.values()]
    .map((x) => ({ ...x, lines: [...x.lines].sort((u, v) => u - v) }))
    .sort((x, y) => (x.type === y.type ? x.to - y.to : x.type === "ride" ? -1 : 1)));
}

// 클러스터 단위 최단 비용 (0-1 BFS가 아니라 비용이 작은 정수라 Dijkstra). 반환: {dist, prev}
export function clusterDistances(moves, src) {
  const dist = new Array(moves.length).fill(Infinity), prev = new Array(moves.length).fill(-1);
  dist[src] = 0;
  const pq = [[0, src]];
  while (pq.length) {
    let bi = 0;
    for (let i = 1; i < pq.length; i++) if (pq[i][0] < pq[bi][0] || (pq[i][0] === pq[bi][0] && pq[i][1] < pq[bi][1])) bi = i;
    const [d, u] = pq.splice(bi, 1)[0];
    if (d > dist[u]) continue;
    for (const mv of moves[u]) {
      const nd = d + mv.cost;
      if (nd < dist[mv.to]) { dist[mv.to] = nd; prev[mv.to] = u; pq.push([nd, mv.to]); }
    }
  }
  return { dist, prev };
}

export function optimalPath(moves, src, dst) {
  const { dist, prev } = clusterDistances(moves, src);
  if (dist[dst] === Infinity) return null;
  const path = [dst];
  while (path[path.length - 1] !== src) path.push(prev[path[path.length - 1]]);
  return { cost: dist[dst], path: path.reverse() };
}

// 게임 상태
export function newGame(data, moves, puzzle) {
  const idx = new Map(data.clusters.map((c, i) => [c.id, i]));
  const from = idx.get(puzzle.from), to = idx.get(puzzle.to);
  if (from === undefined || to === undefined) throw new Error(`퍼즐 역을 데이터에서 못 찾음: ${puzzle.id}`);
  return { puzzle, from, to, path: [from], steps: [], cost: 0, done: false, gaveUp: false,
           maxCost: puzzle.cost_warp * 3 + 10, moves };
}

export function legalMoves(game) {
  if (game.done) return [];
  const here = game.path[game.path.length - 1];
  return game.moves[here];
}

export function play(game, toCluster) {
  const mv = legalMoves(game).find((m) => m.to === toCluster);
  if (!mv) throw new Error("갈 수 없는 역");
  game.path.push(toCluster);
  game.steps.push(mv);
  game.cost += mv.cost;
  if (toCluster === game.to) game.done = true;
  else if (game.cost >= game.maxCost) { game.done = true; game.gaveUp = true; }
  return game;
}

export function undo(game) {
  if (game.done || !game.steps.length) return game;
  const mv = game.steps.pop();
  game.path.pop();
  game.cost -= mv.cost;
  return game;
}

export function giveUp(game) { game.done = true; game.gaveUp = true; return game; }

export function score(game) {
  if (!game.done || game.gaveUp || game.path[game.path.length - 1] !== game.to) return 0;
  return Math.round((100 * game.puzzle.cost_warp) / game.cost);
}

export function medal(s) {
  if (s >= 100) return "💯";
  if (s >= 80) return "🥇";
  if (s >= 60) return "🥈";
  if (s > 0) return "🥉";
  return "🏳️";
}

const DIFF_KO = { easy: "쉬움", normal: "보통", hard: "어려움" };

// 공유 텍스트: 역 이름 대신 수 종류만 이모지로 (🚇 승차, 🌀 워프). 출발·도착 이름은 모두에게 같은 문제라 노출해도 된다
export function shareText(game, number, labels) {
  const s = score(game);
  const em = game.steps.map((m) => (m.type === "warp" ? "🌀" : "🚇")).join("") || "🏳️";
  const p = game.puzzle;
  const lines = [
    `지하철 워프 데일리 #${number} (${DIFF_KO[p.difficulty] || p.difficulty})`,
    `${labels[game.from]} → ${labels[game.to]}`,
    game.gaveUp ? `${em} 포기 (최적 ${p.cost_warp}수)` : `${em} ${game.cost}수 / 최적 ${p.cost_warp}수 ${medal(s)} ${s}점`,
  ];
  if (p.cost_no_warp !== null && p.cost_no_warp !== undefined) lines.push(`워프 없으면 ${p.cost_no_warp}수`);
  return lines.join("\n");
}
