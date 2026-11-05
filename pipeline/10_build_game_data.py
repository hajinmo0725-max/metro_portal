#!/usr/bin/env python3
"""N5. 게임 데이터 사전 계산.

(a) 최단 루트 퍼즐 후보: 모든 출발·도착 클러스터 쌍에 대해 워프 포함/제외 최단 비용과 워프 포함 최적 경로 개수를
    계산하고, 최적해가 유일하면서 워프 단축 폭이 큰 쌍(같은 권역) + 워프 없이는 못 가는 도시 횡단 쌍을 난이도별로 고른다.
(b) N정류장 최대 거리: 정확히 N턴(승차 1역 = 1턴, 워프 1회 = 1턴, 환승은 턴 아님) 동안 같은 물리적 역을 두 번 밟지 않는
    경로 중 (1) 시작-끝 대권거리 최대, (2) 탑승 구간 거리 합 최대를 각각 상위 K개 (출발·도착 쌍 중복 없이).

경로 단위는 클러스터(물리적 역) 수준이다. 환승은 클러스터 안에서 비용 0으로 접히므로 '최적 경로 개수'는
물리적 역 순서(+워프)가 다른 경로의 개수다. 같은 두 역 사이를 다른 노선으로 가는 것은 같은 경로로 센다.
환승 비용이 0이 아닌 ruleset이면 이 단계는 거부한다 (클러스터 접힘이 성립하지 않음).

입력: data/processed/kr/{stations,ride_edges,lines}.json, config/game.yaml, ruleset
출력: data/processed/puzzles.json, data/processed/n_stops_max.json, web/data/puzzles.json(웹용 축약본),
      docs/reports/n5_game_data.md
"""
from __future__ import annotations

import argparse
import heapq
import json
import random
import sys
from collections import Counter, deque
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base  # noqa: E402

INF = float("inf")


class ClusterGraph:
    """클러스터 + 포탈 노드. 인덱스 0..C-1 = 클러스터, C.. = 포탈."""

    def __init__(self, w):
        rs = w["rs"]
        self.cl = sorted(w["clusters"], key=lambda c: c["id"])
        self.C = len(self.cl)
        self.ix = {c["id"]: i for i, c in enumerate(self.cl)}
        cof = {x: c["id"] for c in self.cl for x in c["station_ids"]}
        self.portals = sorted(w["portals"], key=lambda p: p["id"])
        self.P = len(self.portals)
        n = self.C + self.P
        ride = rs["costs"]["ride"]
        self.adj = [dict() for _ in range(n)]       # v -> cost
        self.ride_len = {}                           # (a,b) -> 구간 거리(m), a<b
        self.ride_lines = {}                         # (a,b) -> 노선 id 집합
        for e in w["edges"]:
            a, b = self.ix[cof[e["a"]]], self.ix[cof[e["b"]]]
            if a == b:
                continue
            self.adj[a][b] = ride
            self.adj[b][a] = ride
            k = (min(a, b), max(a, b))
            self.ride_len[k] = max(self.ride_len.get(k, 0.0), e["distance_m"])
            self.ride_lines.setdefault(k, set()).add(e["line"])
        for j, p in enumerate(self.portals):
            pn = self.C + j
            for cid in p["cluster_ids"]:
                c = self.ix[cid]
                self.adj[c][pn] = p["cost"]
                self.adj[pn][c] = 0
        self.adj = [sorted(d.items()) for d in self.adj]
        self.ride_adj = [[(v, c) for v, c in self.adj[u] if v < self.C] for u in range(self.C)]
        self.rev = [[] for _ in range(n)]
        for u in range(n):
            for v, c in self.adj[u]:
                self.rev[v].append((u, c))
        for lst in self.rev:
            lst.sort()

    def name(self, i):
        if i < self.C:
            c = self.cl[i]
            return f"{'/'.join(c['cities'])} {c['name']}"
        return f"[{self.portals[i - self.C]['name']}]"

    def sssp_count(self, s):
        """워프 포함 최단 비용과 최적 경로 개수. 0비용 엣지는 포탈→클러스터뿐이라 (비용, 포탈 먼저) 순서면 DAG 순서가 된다."""
        n = self.C + self.P
        dist = [INF] * n
        cnt = [0] * n
        warps = [0] * n  # 최적 경로의 워프 수 (최적해가 유일한 노드에서만 의미 있음)
        dist[s], cnt[s] = 0, 1
        pq = [(0, 1, s)]
        done = [False] * n
        while pq:
            d, _, u = heapq.heappop(pq)
            if done[u]:
                continue
            done[u] = True
            for v, c in self.adj[u]:
                nd = d + c
                if nd < dist[v]:
                    dist[v], cnt[v] = nd, cnt[u]
                    warps[v] = warps[u] + (1 if u >= self.C else 0)
                    heapq.heappush(pq, (nd, 0 if v >= self.C else 1, v))
                elif nd == dist[v]:
                    cnt[v] += cnt[u]
        self.last_warps = warps
        return dist, cnt

    def bfs_ride(self, s):
        dist = [INF] * self.C
        dist[s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for v, c in self.ride_adj[u]:
                if dist[u] + c < dist[v]:
                    dist[v] = dist[u] + c
                    q.append(v)
        return dist

    def unique_path(self, s, t, dist):
        """최적해가 유일할 때 t에서 거꾸로 따라가 경로 복원 (s에서 시작한 dist 사용)."""
        path = [t]
        while path[-1] != s:
            v = path[-1]
            path.append(next(u for u, c in self.rev[v] if dist[u] + c == dist[v]))
        return path[::-1]


def describe_path(g, path):
    """클러스터·포탈 노드열 → 단계 목록 (ride는 노선 묶음, warp는 포탈)."""
    steps = []
    i = 0
    while i < len(path) - 1:
        u, v = path[i], path[i + 1]
        if v >= g.C:  # warp: u -> portal -> w
            w = path[i + 2]
            steps.append({"type": "warp", "portal": g.portals[v - g.C]["name"], "from": g.cl[u]["id"], "to": g.cl[w]["id"]})
            i += 2
        else:
            k = (min(u, v), max(u, v))
            steps.append({"type": "ride", "from": g.cl[u]["id"], "to": g.cl[v]["id"], "lines": sorted(g.ride_lines[k])})
            i += 1
    return steps


def difficulty(cfg, cost, warps):
    for level in ("easy", "normal"):
        lim = cfg["difficulty"][level]
        if warps <= lim["max_warps"] and cost <= lim["max_cost"]:
            return level
    return "hard"


def build_puzzles(g, cfg):
    C = g.C
    rows = []
    for s in range(C):
        dw, cw = g.sssp_count(s)
        wp = g.last_warps
        dn = g.bfs_ride(s)
        for t in range(s + 1, C):
            if dw[t] == INF:
                continue
            rows.append((s, t, dw[t], dn[t], cw[t], wp[t]))
    stats = {"pairs": len(rows),
             "pairs_reachable_without_warp": sum(1 for r in rows if r[3] != INF),
             "pairs_warp_shortens": sum(1 for r in rows if r[3] != INF and r[2] < r[3]),
             "pairs_cross_component": sum(1 for r in rows if r[3] == INF),
             "pairs_unique_optimum": sum(1 for r in rows if r[4] == 1),
             "optimal_count_hist": dict(sorted(Counter(min(r[4], 10) for r in rows).items())),
             }
    # 출발·도착 이름이 같으면(양평→양평) 워프 한 번이 답이라 퍼즐에서 뺀다. 최소 비용도 둔다
    ok = [r for r in rows if r[4] == 1 and cfg["min_cost"] <= r[2] <= cfg["max_cost"] and g.cl[r[0]]["name"] != g.cl[r[1]]["name"]]
    shortcut = [r for r in ok if r[3] != INF and r[2] < r[3] and r[3] - r[2] >= cfg["min_savings"]]
    cross = [r for r in ok if r[3] == INF]
    stats["candidates_shortcut"] = len(shortcut)
    stats["candidates_crosscity"] = len(cross)
    dist_cache = {}

    def path_of(s, t):
        if s not in dist_cache:
            dist_cache[s] = g.sssp_count(s)[0]
        return g.unique_path(s, t, dist_cache[s])

    out = []
    for kind, rows_k in (("shortcut", shortcut), ("crosscity", cross)):
        by_lvl = {"easy": [], "normal": [], "hard": []}
        for s, t, cw, cn, _, warps in rows_k:
            sav = (cn - cw) if cn != INF else None
            # 정렬 키: 단축 폭(같은 권역) 또는 워프 수·비용(도시 횡단)이 클수록 흥미롭다
            key = (-(sav or 0), -(sav / cn if sav else 0), s, t) if kind == "shortcut" else (-warps, -cw, s, t)
            by_lvl[difficulty(cfg, cw, warps)].append((key, s, t, cw, cn, warps))
        for lvl in ("easy", "normal", "hard"):
            stats[f"pool_{kind}_{lvl}"] = len(by_lvl[lvl])
            used_sig, used_end, picked = Counter(), Counter(), 0
            for _, s, t, cw, cn, warps in sorted(by_lvl[lvl]):
                if used_end[s] >= cfg["max_per_endpoint"] or used_end[t] >= cfg["max_per_endpoint"]:
                    continue
                steps = describe_path(g, path_of(s, t))
                sig = tuple(x["portal"] for x in steps if x["type"] == "warp")
                assert len(sig) == warps
                if used_sig[sig] >= cfg["max_per_warp_signature"]:
                    continue
                used_sig[sig] += 1
                used_end[s] += 1
                used_end[t] += 1
                out.append({"kind": kind, "difficulty": lvl, "from": g.cl[s]["id"], "to": g.cl[t]["id"],
                            "from_label": g.name(s), "to_label": g.name(t),
                            "cost_warp": cw, "cost_no_warp": None if cn == INF else cn,
                            "savings": None if cn == INF else cn - cw, "optimal_paths": 1, "warps": warps,
                            "rides": sum(1 for x in steps if x["type"] == "ride"), "warp_portals": list(sig),
                            "optimal": steps})
                picked += 1
                if picked >= cfg["per_kind_per_difficulty"][kind]:
                    break
    # 결정적 퍼즐 id와 데일리 순서
    for i, p in enumerate(out):
        p["id"] = f"P{i + 1:03d}"
    rnd = random.Random(cfg["daily_seed"])
    order = [p["id"] for p in out]
    rnd.shuffle(order)
    return out, order, stats


def n_stops(g, N, K, allow_warp=True):
    """정확히 N턴 단순 경로(클러스터 재방문 금지) 전수 탐색."""
    C = g.C
    lat = [c["lat"] for c in g.cl]
    lon = [c["lon"] for c in g.cl]
    nb = []
    for u in range(C):
        lst = [(v, g.ride_len[(min(u, v), max(u, v))], False) for v, _ in g.ride_adj[u]]
        if allow_warp:
            for pn, _ in g.adj[u]:
                if pn >= C:
                    for w, _ in g.adj[pn]:
                        if w != u:
                            lst.append((w, 0.0, True))
        # 같은 목적지가 승차·워프 둘 다면 승차 우선 (구간 거리 합에 유리)
        best = {}
        for v, d, wp in lst:
            if v not in best or (best[v][2] and not wp):
                best[v] = (v, d, wp)
        nb.append(sorted(best.values()))
    best_gc, best_tr = {}, {}
    vis = [False] * C
    path = []
    nwarps = [0]

    def dfs(u, depth, track, s):
        if depth == N:
            k = (min(s, u), max(s, u))
            gc = haversine_m(lat[s], lon[s], lat[u], lon[u])
            if k not in best_gc or gc > best_gc[k][0] + 1e-9:
                best_gc[k] = (gc, list(path), nwarps[0])
            if k not in best_tr or track > best_tr[k][0] + 1e-9:
                best_tr[k] = (track, list(path), nwarps[0])
            return
        for v, d, wp in nb[u]:
            if not vis[v]:
                vis[v] = True
                path.append((v, wp))
                nwarps[0] += wp
                dfs(v, depth + 1, track + d, s)
                nwarps[0] -= wp
                path.pop()
                vis[v] = False

    for s in range(C):
        vis[s] = True
        path.append((s, False))
        dfs(s, 0, 0.0, s)
        path.pop()
        vis[s] = False

    def top(best):
        items = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[:K]
        res = []
        for (a, b), (val, p, nw) in items:
            res.append({"value_m": round(val), "start": g.cl[p[0][0]]["id"], "end": g.cl[p[-1][0]]["id"],
                        "start_label": g.name(p[0][0]), "end_label": g.name(p[-1][0]), "warps": nw,
                        "great_circle_m": round(haversine_m(lat[p[0][0]], lon[p[0][0]], lat[p[-1][0]], lon[p[-1][0]])),
                        "track_m": round(sum(g.ride_len[(min(x[0], y[0]), max(x[0], y[0]))] for x, y in zip(p, p[1:]) if not y[1])),
                        "path": [{"cluster": g.cl[v]["id"], "label": g.name(v), "via": "warp" if wp else ("start" if i == 0 else "ride")}
                                 for i, (v, wp) in enumerate(p)]})
        return res
    return {"great_circle": top(best_gc), "track": top(best_tr), "pairs_seen": len(best_gc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruleset", default="strict")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "config" / "game.yaml", encoding="utf-8"))
    rs = load_ruleset(a.ruleset)
    if rs["costs"]["transfer"] != 0:
        raise SystemExit("[10] 환승 비용 0인 ruleset만 지원 (클러스터 접힘 전제)")
    w = build_world(*load_base(), rs)
    g = ClusterGraph(w)
    puzzles, order, stats = build_puzzles(g, cfg["puzzles"])
    pz = {"ruleset": rs["name"], "definition": {
        "unit": "클러스터(물리적 역). 환승 비용 0으로 클러스터 안에서 접힘",
        "cost": f"승차 1역 = {rs['costs']['ride']}, 워프 = 포탈 비용(T1 {rs['portals']['T1']['cost']})",
        "optimal_paths": "물리적 역 순서(+워프)가 다른 최단 경로 개수. 같은 구간의 다른 노선은 같은 경로",
        "kinds": {"shortcut": "워프 없이도 갈 수 있지만 워프로 크게 단축되는 쌍 (단축 폭 큰 순)",
                  "crosscity": "워프 없이는 못 가는 쌍 (워프 수·비용 큰 순)"},
        "difficulty": cfg["puzzles"]["difficulty"]},
        "stats": stats, "daily_order": order, "puzzles": puzzles}
    out = ROOT / "data" / "processed" / "puzzles.json"
    out.write_text(json.dumps(pz, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    web = {"ruleset": rs["name"], "daily_epoch": cfg["puzzles"]["daily_epoch"], "daily_order": order,
           "puzzles": [{k: p[k] for k in ("id", "kind", "difficulty", "from", "to", "cost_warp", "cost_no_warp", "savings", "warps")}
                       for p in puzzles]}
    (ROOT / "web" / "data" / "puzzles.json").write_text(json.dumps(web, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[10] puzzles={len(puzzles)} stats={json.dumps(stats, ensure_ascii=False)}")

    ncfg = cfg["n_stops"]
    ns = {"ruleset": rs["name"], "N": ncfg["N"], "definition": {
        "turn": "승차 1역 = 1턴, 워프 1회 = 1턴, 환승은 턴이 아님",
        "path": "정확히 N턴, 같은 물리적 역(클러스터) 재방문 금지",
        "great_circle": "시작·끝 클러스터 좌표의 대권거리",
        "track": "탑승한 인접역 구간 직선거리 합 (실제 선로 길이가 아니라 역 좌표 간 직선거리 근사). 워프 구간은 0"},
        "with_warp": n_stops(g, ncfg["N"], ncfg["top_k"], True),
        "without_warp": n_stops(g, ncfg["N"], ncfg["top_k_no_warp"], False)}
    (ROOT / "data" / "processed" / "n_stops_max.json").write_text(json.dumps(ns, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(pz, ns, g)
    print(f"[10] n_stops N={ncfg['N']}: gc top={ns['with_warp']['great_circle'][0]['value_m']}m "
          f"track top={ns['with_warp']['track'][0]['value_m']}m")
    return 0


def fmt_steps(steps):
    out = []
    for x in steps:
        if x["type"] == "ride":
            out.append(f"{x['from'].split('#')[0]}→{x['to'].split('#')[0]}")
        else:
            out.append(f"⇢[{x['portal']}]⇢")
    # 연속 승차 압축: A→B, B→C → A→B→C
    txt = []
    for s in out:
        if txt and "→" in s and "→" in txt[-1] and not txt[-1].startswith("⇢") and txt[-1].split("→")[-1] == s.split("→")[0]:
            txt[-1] = txt[-1] + "→" + s.split("→")[1]
        else:
            txt.append(s)
    return " ".join(txt)


def write_report(pz, ns, g):
    st = pz["stats"]
    L = ["# N5 게임 데이터 사전 계산", "", "생성: `python3 pipeline/10_build_game_data.py` (설정: `config/game.yaml`)", "",
         "## (a) 최단 루트 퍼즐 후보", "",
         f"- 정의: {pz['definition']['unit']}. 비용 {pz['definition']['cost']}. 최적 경로 개수 = {pz['definition']['optimal_paths']}.",
         "", "| 항목 | 값 |", "| :- | -: |"]
    L += [f"| {k} | {v} |" for k, v in st.items()]
    L += ["", "optimal_count_hist: 워프 포함 최적 경로 개수 분포 (10 = 10개 이상).", "",
          f"선정 결과: {len(pz['puzzles'])}개 → `data/processed/puzzles.json` (웹용 축약본 `web/data/puzzles.json`)", ""]
    for kind in ("shortcut", "crosscity"):
        L += [f"### {kind} — {pz['definition']['kinds'][kind]}", "",
              "| id | 난이도 | 출발 | 도착 | 워프 有 | 워프 無 | 단축 | 워프 | 최적 경로 |", "| :- | :- | :- | :- | -: | -: | -: | -: | :- |"]
        for p in pz["puzzles"]:
            if p["kind"] != kind:
                continue
            L.append(f"| {p['id']} | {p['difficulty']} | {p['from_label']} | {p['to_label']} | {p['cost_warp']} | "
                     f"{p['cost_no_warp'] if p['cost_no_warp'] is not None else '불가'} | {p['savings'] if p['savings'] is not None else '-'} | "
                     f"{p['warps']} | {fmt_steps(p['optimal'])} |")
        L.append("")
    L += [f"## (b) N정류장 최대 거리 (N={ns['N']})", "",
          f"- 턴: {ns['definition']['turn']}. 경로: {ns['definition']['path']}.",
          f"- 대권거리: {ns['definition']['great_circle']}. 구간 거리 합: {ns['definition']['track']}.", ""]
    for key, title in (("great_circle", "시작-끝 대권거리 최대"), ("track", "탑승 구간 거리 합 최대")):
        L += [f"### {title} — 워프 허용 상위 {len(ns['with_warp'][key])}", "",
              "| 순위 | 값(km) | 시작 | 끝 | 워프 | 대권(km) | 구간 합(km) | 경로 |", "| -: | -: | :- | :- | -: | -: | -: | :- |"]
        for i, r in enumerate(ns["with_warp"][key], 1):
            route = " ".join(("⇢" if x["via"] == "warp" else ("" if x["via"] == "start" else "→")) + x["label"].split(" ", 1)[1].split("#")[0]
                             for x in r["path"])
            L.append(f"| {i} | {r['value_m'] / 1000:.1f} | {r['start_label']} | {r['end_label']} | {r['warps']} | "
                     f"{r['great_circle_m'] / 1000:.1f} | {r['track_m'] / 1000:.1f} | {route} |")
        L += ["", f"워프 금지 상위 {len(ns['without_warp'][key])} (비교):", "",
              "| 순위 | 값(km) | 시작 | 끝 |", "| -: | -: | :- | :- |"]
        L += [f"| {i} | {r['value_m'] / 1000:.1f} | {r['start_label']} | {r['end_label']} |" for i, r in enumerate(ns["without_warp"][key], 1)]
        L.append("")
    (ROOT / "docs" / "reports" / "n5_game_data.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
