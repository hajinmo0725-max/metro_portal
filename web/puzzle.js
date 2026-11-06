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

// 날짜 → 퍼즐. daily_order(4차: 제약 기반 순환 일정)를 날짜 차이로 순환한다. number = 1번부터 세는 회차
// 4차 Q1: 출시일(daily_epoch) 이전 날짜는 #0·#-2499 같은 회차를 만들지 않고 1회차로 맞춘다 (beforeEpoch = true)
export function dailyPick(pz, dateStr) {
  let d = daysBetween(pz.daily_epoch, dateStr);
  const beforeEpoch = !(d >= 0);
  if (beforeEpoch) d = 0;
  const n = pz.daily_order.length;
  const id = pz.daily_order[d % n];
  return { number: d + 1, puzzle: pz.puzzles.find((p) => p.id === id), beforeEpoch,
           date: beforeEpoch ? pz.daily_epoch : dateStr };
}

// 날짜 문자열 검사: YYYY-MM-DD 형식이고 실제 있는 날짜인가 (2026-02-30 거부)
export function validDateString(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s || "")) return false;
  const t = Date.parse(`${s}T00:00:00Z`);
  return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === s;
}

// 4차 Q3: 승차 이동의 진행 방향 (○○ 방면). 노선 시퀀스에서 a → b로 갈 때 그 방향 종점 클러스터.
// 순환 시퀀스(2호선 등)는 종점이 없어서 진행 방향으로 3역 앞 클러스터를 방면으로 쓴다. 단방향 시퀀스는 정방향만
export function rideDirections(data) {
  const dirs = new Map();   // "a>b" -> [{line, term}]
  const add = (a, b, line, term) => {
    const k = `${a}>${b}`;
    if (!dirs.has(k)) dirs.set(k, []);
    if (!dirs.get(k).some((x) => x.line === line && x.term === term)) dirs.get(k).push({ line, term });
  };
  for (const [li, ln] of data.lines.entries()) {
    for (const sq of ln.seqs) {
      const cs = [];
      for (const n of sq.nodes) { const c = data.nodes[n].c; if (cs[cs.length - 1] !== c) cs.push(c); }
      const m = cs.length;
      for (let k = 0; k + 1 < m || (sq.circular && k < m); k++) {
        const a = cs[k], b = cs[(k + 1) % m];
        if (a === b) continue;
        if (sq.circular) {
          add(a, b, li, cs[(k + 3) % m]);
          if (!sq.directed) add(b, a, li, cs[((k - 2) % m + m) % m]);
        } else {
          add(a, b, li, cs[m - 1]);
          if (!sq.directed) add(b, a, li, cs[0]);
        }
      }
    }
  }
  for (const v of dirs.values()) v.sort((x, y) => x.line - y.line || x.term - y.term);
  return dirs;
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
  // 4차 Q3: 이동 후보 고정 정렬 = 승차 먼저 (노선 번호 → 방면 이름), 워프는 포탈 이름 → 도착 역. 가나다순이 아니라 매 수 같은 기준
  const dirs = rideDirections(data);
  const portalAt = new Map();
  for (const p of data.portals) for (const c of p.c) { if (!portalAt.has(c)) portalAt.set(c, []); portalAt.get(c).push(p.n); }
  const name = (c) => data.clusters[c].n;
  return seen.map((m, from) => [...m.values()]
    .map((x) => {
      const lines = [...x.lines].sort((u, v) => u - v);
      const d = x.type === "ride" ? (dirs.get(`${from}>${x.to}`) || []).filter((y) => lines.includes(y.line)) : [];
      return { ...x, lines, dir: d.length ? d[0].term : null, dirLine: d.length ? d[0].line : null,
               toPortal: (portalAt.get(x.to) || []).slice().sort() };
    })
    .sort((x, y) => {
      if (x.type !== y.type) return x.type === "ride" ? -1 : 1;
      if (x.type === "ride") {
        const lx = x.dirLine ?? x.lines[0], ly = y.dirLine ?? y.lines[0];
        if (lx !== ly) return lx - ly;
        const dx = x.dir === null ? "" : name(x.dir), dy = y.dir === null ? "" : name(y.dir);
        return dx < dy ? -1 : dx > dy ? 1 : x.to - y.to;
      }
      return x.portal < y.portal ? -1 : x.portal > y.portal ? 1 : x.to - y.to;
    }));
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
  return { puzzle, from, to, path: [from], steps: [], cost: 0, done: false, gaveUp: false, undos: 0,
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
  game.undos += 1;   // 4차 Q3: 되돌리기 횟수 (점수에는 영향 없고 공유 문구에만)
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
  lines.push(`↶ 되돌리기 ${game.undos || 0}회`);
  return lines.join("\n");
}
