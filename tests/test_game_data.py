"""N5: 게임 데이터 사전 계산 — 최적 경로 개수(브루트포스 대조), N정류장 탐색, 실데이터 퍼즐 회귀."""
import importlib.util
import itertools
import json
import random
from pathlib import Path

import pytest

from helpers import st
from metro_portal.ruleset import load_ruleset

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("g10", ROOT / "pipeline" / "10_build_game_data.py")
g10 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g10)


def toy_world(n, ride_pairs, portal_groups, seed=0):
    """클러스터 n개(이름 c0..), 승차 엣지, 포탈(같은 이름 그룹). 좌표는 서로 멀리 떨어뜨려 환승으로 안 묶이게 한다."""
    rnd = random.Random(seed)
    names = [f"c{i}" for i in range(n)]
    for k, grp in enumerate(portal_groups):
        for i in grp:
            names[i] = f"p{k}"
    stations = [st(f"s{i}", names[i], 33.5 + i * 0.05, 125.0 + rnd.random() * 0.01, line=f"L{i}") for i in range(n)]
    edges = [{"line": "L", "a": f"s{a}", "b": f"s{b}", "distance_m": 1000.0 + a + b} for a, b in ride_pairs]
    rs = load_ruleset("strict")
    from metro_portal.graph import build_clusters, build_graph, build_portals
    cl = build_clusters(stations, rs)
    for c in cl:
        c["cities"] = ["X"]
    portals, _ = build_portals(stations, cl, rs)
    adj = build_graph(stations, edges, cl, portals, rs)
    return {"stations": stations, "edges": edges, "lines": [], "clusters": cl, "portals": portals, "adj": adj, "rs": rs}


def brute_counts(g, s):
    """모든 단순 경로를 열거해서 최단 비용과 개수를 센다 (작은 그래프 전용)."""
    best = {}
    n = g.C + g.P

    def dfs(u, cost, seen):
        if u < g.C:
            b = best.get(u)
            if b is None or cost < b[0]:
                best[u] = [cost, 1]
            elif cost == b[0]:
                b[1] += 1
        for v, c in g.adj[u]:
            if v not in seen:
                seen.add(v)
                dfs(v, cost + c, seen)
                seen.remove(v)
    dfs(s, 0, {s})
    del n
    return best


@pytest.mark.parametrize("seed", range(12))
def test_path_count_matches_bruteforce(seed):
    rnd = random.Random(seed)
    n = 9
    pairs = sorted({tuple(sorted(rnd.sample(range(n), 2))) for _ in range(12)})
    groups = [[0, 5], [2, 7, 8]] if seed % 2 else [[1, 6]]
    w = toy_world(n, pairs, groups, seed)
    g = g10.ClusterGraph(w)
    for s in range(g.C):
        dist, cnt = g.sssp_count(s)
        bf = brute_counts(g, s)
        for t in range(g.C):
            if t == s:
                continue
            if t in bf:
                assert dist[t] == bf[t][0] and cnt[t] == bf[t][1], (seed, s, t)
            else:
                assert dist[t] == float("inf")


def test_parallel_routes_and_unique_warp():
    # 0-1-3, 0-2-3 두 갈래(비용 2, 2개) / 4는 0과 같은 이름(포탈)이라 0→4는 워프 1회 유일
    w = toy_world(5, [(0, 1), (1, 3), (0, 2), (2, 3)], [[0, 4]])
    g = g10.ClusterGraph(w)
    i = {c["name"]: g.ix[c["id"]] for c in g.cl}
    dist, cnt = g.sssp_count(g.ix[[c["id"] for c in g.cl if c["station_ids"] == ["s0"]][0]])
    s3 = g.ix[[c["id"] for c in g.cl if c["station_ids"] == ["s3"]][0]]
    s4 = g.ix[[c["id"] for c in g.cl if c["station_ids"] == ["s4"]][0]]
    assert (dist[s3], cnt[s3]) == (2, 2)
    assert (dist[s4], cnt[s4]) == (1, 1) and g.last_warps[s4] == 1
    del i


def test_n_stops_line_exact_turns():
    # 일직선 0-1-2-3-4, 워프 없음, N=2: 끝점 쌍은 (0,2),(1,3),(2,4)
    w = toy_world(5, [(0, 1), (1, 2), (2, 3), (3, 4)], [])
    g = g10.ClusterGraph(w)
    res = g10.n_stops(g, 2, 10, allow_warp=False)
    ends = {tuple(sorted((r["start"], r["end"]))) for r in res["great_circle"]}
    ids = {c["station_ids"][0]: c["id"] for c in g.cl}
    assert ends == {tuple(sorted((ids[f"s{a}"], ids[f"s{b}"]))) for a, b in [(0, 2), (1, 3), (2, 4)]}
    assert all(len(r["path"]) == 3 for r in res["track"])


def test_n_stops_warp_counts_as_turn():
    # 0-1 승차, 1과 3이 포탈, 3-4 승차. N=3이면 0→1⇢3→4 가능 (워프 1턴)
    w = toy_world(5, [(0, 1), (3, 4)], [[1, 3]])
    g = g10.ClusterGraph(w)
    res = g10.n_stops(g, 3, 5, allow_warp=True)
    ids = {c["station_ids"][0]: c["id"] for c in g.cl}
    pairs = {tuple(sorted((r["start"], r["end"]))): r for r in res["great_circle"]}
    k = tuple(sorted((ids["s0"], ids["s4"])))
    assert k in pairs and pairs[k]["warps"] == 1
    assert pairs[k]["track_m"] == round(1001.0 + 1007.0)


PZ = ROOT / "data" / "processed" / "puzzles.json"
real = pytest.mark.skipif(not PZ.exists(), reason="puzzles.json missing")


@real
def test_puzzles_are_consistent_with_router():
    """퍼즐의 워프 有/無 비용을 05 단계 길찾기(역 수준 그래프)로 다시 계산해 대조하고, 최적 경로가 유효한지 본다."""
    from metro_portal.route import shortest_path, without_warps
    from metro_portal.world import build_world, load_base
    pz = json.loads(PZ.read_text(encoding="utf-8"))
    w = build_world(*load_base(), load_ruleset(pz["ruleset"]))
    cmap = {c["id"]: c for c in w["clusters"]}
    nowarp = without_warps(w["adj"])
    g = g10.ClusterGraph(w)
    assert len(pz["puzzles"]) >= 60 and len(set(pz["daily_order"])) == len(pz["puzzles"])
    for p in pz["puzzles"]:
        a, b = cmap[p["from"]]["station_ids"], cmap[p["to"]]["station_ids"]
        r = shortest_path(w["adj"], a, b)
        assert r[0] == p["cost_warp"], p["id"]
        rn = shortest_path(nowarp, a, b)
        assert (rn[0] if rn else None) == p["cost_no_warp"], p["id"]
        assert p["optimal_paths"] == 1 and cmap[p["from"]]["name"] != cmap[p["to"]]["name"]
        # 최적 경로: 연속, 승차는 인접, 워프는 같은 포탈, 비용 합 = cost_warp
        cur, cost = p["from"], 0
        for s in p["optimal"]:
            assert s["from"] == cur
            u, v = g.ix[s["from"]], g.ix[s["to"]]
            if s["type"] == "ride":
                assert any(x == v for x, _ in g.ride_adj[u])
                cost += 1
            else:
                portal = next(q for q in g.portals if q["name"] == s["portal"])
                assert s["from"] in portal["cluster_ids"] and s["to"] in portal["cluster_ids"]
                cost += portal["cost"]
            cur = s["to"]
        assert cur == p["to"] and cost == p["cost_warp"]
        _, cnt = g.sssp_count(g.ix[p["from"]])
        assert cnt[g.ix[p["to"]]] == 1


@real
def test_n_stops_results_valid():
    ns = json.loads((ROOT / "data" / "processed" / "n_stops_max.json").read_text(encoding="utf-8"))
    N = ns["N"]
    for key in ("great_circle", "track"):
        rows = ns["with_warp"][key]
        assert len(rows) == 20
        vals = [r["value_m"] for r in rows]
        assert vals == sorted(vals, reverse=True)
        assert len({tuple(sorted((r["start"], r["end"]))) for r in rows}) == 20
        for r in rows:
            assert len(r["path"]) == N + 1
            assert len({x["cluster"] for x in r["path"]}) == N + 1  # 재방문 없음
            assert sum(x["via"] == "warp" for x in r["path"]) == r["warps"]
    # 워프 허용 최댓값 >= 워프 금지 최댓값
    for key in ("great_circle", "track"):
        assert ns["with_warp"][key][0]["value_m"] >= ns["without_warp"][key][0]["value_m"]
