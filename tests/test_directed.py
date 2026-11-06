"""3차 A2: 유향 승차 엣지 (6호선 응암순환 단방향). 거리 대칭을 가정하던 곳이 전부 방향을 지키는지 고정한다."""
import json

import pytest

from metro_portal import ROOT
from metro_portal.game import INF, ClusterGraph, n_stops
from metro_portal.graph import build_graph
from metro_portal.metrics import cluster_graph, diameter, strong_components
from metro_portal.route import shortest_path
from metro_portal.ruleset import load_ruleset

from helpers import st

RS = load_ruleset("strict")


def loop_world():
    """A(분기역) - B 본선 무향, A→C→D→A 단방향 순환. 응암순환 축소판."""
    S = [st("A", "가", 37.60, 126.90), st("B", "나", 37.59, 126.91), st("C", "다", 37.61, 126.91), st("D", "라", 37.62, 126.90)]
    E = [{"line": "L", "a": "A", "b": "B", "distance_m": 1000.0},
         {"line": "L", "a": "A", "b": "C", "distance_m": 1000.0, "directed": True},
         {"line": "L", "a": "C", "b": "D", "distance_m": 1000.0, "directed": True},
         {"line": "L", "a": "D", "b": "A", "distance_m": 1000.0, "directed": True}]
    clusters = [{"id": f"{s['name_ko']}#1", "name": s["name_ko"], "names": [s["name_ko"]], "station_ids": [s["id"]],
                 "lat": s["lat"], "lon": s["lon"], "regions": [""], "lines": ["L"], "cities": ["X"]} for s in S]
    return S, E, clusters


def test_station_graph_respects_direction():
    S, E, cl = loop_world()
    adj = build_graph(S, E, cl, [], RS)
    assert [x[0] for x in adj["A"] if x[2] == "ride"] == ["B", "C"]
    assert [x[0] for x in adj["C"] if x[2] == "ride"] == ["D"]       # C → A 불가
    assert shortest_path(adj, ["A"], ["C"])[0] == 1
    assert shortest_path(adj, ["C"], ["A"])[0] == 2                  # C → D → A
    assert shortest_path(adj, ["C"], ["B"])[0] == 3


def test_cluster_graph_and_diameter_use_ordered_pairs():
    S, E, cl = loop_world()
    g = cluster_graph(cl, E, [], RS, with_warp=False)
    d = diameter(g, [c["id"] for c in cl], 4000, 42)
    # 최장 순서쌍 비용 3: C → B(C→D→A→B), B → D(B→A→C→D). 동률이면 (출발, 도착) 사전순 → 나 → 라
    # 역방향은 각각 2라서 대칭 가정이면 지름을 2로 잘못 낸다
    assert d["value"] == 3 and (d["from"], d["to"]) == ("나#1", "라#1")
    assert len(strong_components(g, set(g))) == 1


def test_strong_components_detects_one_way_dead_end():
    adj = {"a": [("b", 1)], "b": [("c", 1)], "c": [("b", 1)]}
    comps = strong_components(adj, set(adj))
    assert comps == [["b", "c"], ["a"]]


def test_game_cluster_graph_direction_and_nstops():
    S, E, cl = loop_world()
    g = ClusterGraph({"rs": RS, "clusters": cl, "portals": [], "edges": E})
    a, c = g.ix["가#1"], g.ix["다#1"]
    assert g.sssp_count(a)[0][c] == 1
    assert g.sssp_count(c)[0][a] == 2
    assert g.bfs_ride(c)[a] == 2
    # 2턴 경로: C에서 시작하면 C→D→A만 가능 (C→A→B 불가)
    res = n_stops(g, 2, 10, allow_warp=False)
    starts = {(r["start"], r["end"]) for r in res["track"]}
    assert ("다#1", "나#1") not in starts
    for r in res["track"]:
        for x, y in zip(r["path"], r["path"][1:]):
            assert any(v == g.ix[y["cluster"]] for v, _ in g.ride_adj[g.ix[x["cluster"]]])


PROC = ROOT / "data" / "processed" / "kr"


@pytest.mark.skipif(not (PROC / "ride_edges.json").exists(), reason="processed data missing")
def test_real_eungam_loop_is_one_way():
    stn = {s["id"]: s["name_ko"] for s in json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]}
    E = json.loads((PROC / "ride_edges.json").read_text(encoding="utf-8"))["edges"]
    loop = [(stn[e["a"]], stn[e["b"]]) for e in E if e.get("directed")]
    assert sorted(loop) == sorted([("응암", "역촌"), ("역촌", "불광"), ("불광", "독바위"), ("독바위", "연신내"),
                                   ("연신내", "구산"), ("구산", "응암")])
    # 무향 엣지에는 같은 쌍이 없어야 한다 (역방향 이동이 새면 안 됨)
    und = {frozenset((stn[e["a"]], stn[e["b"]])) for e in E if not e.get("directed") and e["line"] == "seoul-6"}
    assert not any(frozenset(p) in und for p in loop)


@pytest.mark.skipif(not (PROC / "strict" / "graph.json").exists(), reason="graph missing")
def test_real_route_eungam_direction():
    """실데이터: 응암 → 역촌 1역. 역촌 → 응암은 역방향 승차가 안 돼서 4수
    (역촌→불광, 3호선 불광→연신내, 6호선 연신내→구산→응암). 순환만 타면 5역."""
    from metro_portal.route import without_warps
    from metro_portal.world import build_world, load_base
    w = build_world(*load_base(), RS)
    adj = without_warps(w["adj"])
    ids = lambda n: [s["id"] for s in w["stations"] if s["name_ko"] == n and s["line_group"].startswith("S1106")]  # noqa: E731
    assert shortest_path(adj, ids("응암"), ids("역촌"))[0] == 1
    assert shortest_path(adj, ids("역촌"), ids("응암"))[0] == 4
