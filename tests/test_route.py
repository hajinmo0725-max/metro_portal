import random
from pathlib import Path

import pytest

from metro_portal.route import is_01, shortest_path, without_warps


def random_graph(n, m, seed, weights=(0, 1)):
    rnd = random.Random(seed)
    adj = {f"n{i}": [] for i in range(n)}
    for _ in range(m):
        a, b = rnd.randrange(n), rnd.randrange(n)
        if a != b:
            adj[f"n{a}"].append((f"n{b}", rnd.choice(weights), "ride", "L"))
    for k in adj:
        adj[k].sort()
    return adj


def path_cost(adj, path):
    total = 0
    for (a, _, _), (b, kind, meta) in zip(path, path[1:]):
        total += min(c for (y, c, k, mm) in adj[a] if y == b and k == kind and mm == meta)
    return total


@pytest.mark.parametrize("seed", range(20))
def test_01bfs_matches_dijkstra(seed):
    adj = random_graph(60, 180, seed)
    assert is_01(adj)
    for t in ["n5", "n17", "n42"]:
        a = shortest_path(adj, ["n0"], [t], "01bfs")
        b = shortest_path(adj, ["n0"], [t], "dijkstra")
        assert (a is None) == (b is None)
        if a:
            assert a[0] == b[0]
            assert path_cost(adj, a[1]) == a[0]
            assert a[1][0][0] == "n0" and a[1][-1][0] == t


def test_dijkstra_with_weights():
    adj = random_graph(40, 150, 7, weights=(0, 1, 2, 3))
    assert not is_01(adj)
    r = shortest_path(adj, ["n0"], ["n9"])
    if r:
        assert path_cost(adj, r[1]) == r[0]


def test_multi_source_target():
    adj = {"a": [("c", 1, "ride", "L")], "b": [("c", 0, "transfer", "x")], "c": [("d", 1, "ride", "L")], "d": []}
    cost, path = shortest_path(adj, ["a", "b"], ["d", "c"])
    assert cost == 0 and path[0][0] == "b" and path[-1][0] == "c"


def test_unreachable():
    adj = {"a": [], "b": []}
    assert shortest_path(adj, ["a"], ["b"]) is None


def test_warp_cost_once():
    adj = {"x": [("P:T1:n", 1, "warp_in", "T1")], "P:T1:n": [("y", 0, "warp_out", "T1")], "y": []}
    cost, path = shortest_path(adj, ["x"], ["y"])
    assert cost == 1 and [p[1] for p in path] == ["start", "warp_in", "warp_out"]
    assert shortest_path(without_warps(adj), ["x"], ["y"]) is None


PROC = Path(__file__).resolve().parent.parent / "data" / "processed" / "kr"
real = pytest.mark.skipif(not (PROC / "stations.json").exists(), reason="processed data missing")


@pytest.fixture(scope="module")
def world():
    import importlib.util
    spec = importlib.util.spec_from_file_location("route_cli", Path(__file__).resolve().parent.parent / "pipeline" / "05_route.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, mod.load_world("strict")


@real
def test_gangnam_to_busan_dongnae_via_gyodae(world):
    mod, w = world
    r = mod.route(w, "강남", "부산 동래")
    assert r["reachable"] and r["cost"] == 3 and r["warps"] == 1
    assert any("[교대]" in s for s in r["steps"])


@real
def test_examples_reachable_only_with_warp(world):
    mod, w = world
    for s, d in [("목동", "부산 동래"), ("강남", "부산 동래"), ("개화", "광주 녹동")]:
        assert mod.route(w, s, d)["reachable"]
        assert not mod.route(w, s, d, warp=False)["reachable"]


@real
def test_route_matches_dijkstra(world):
    mod, w = world
    rs, idx, adj, *_ = w
    for s, d in [("목동", "부산 동래"), ("개화", "광주 녹동"), ("신창", "연천")]:
        a, b = idx.resolve(s)[0], idx.resolve(d)[0]
        x = shortest_path(adj, a["station_ids"], b["station_ids"], "01bfs")
        y = shortest_path(adj, a["station_ids"], b["station_ids"], "dijkstra")
        assert x[0] == y[0]


@real
def test_same_city_route_no_warp_needed(world):
    mod, w = world
    a, b = mod.route(w, "강남", "잠실"), mod.route(w, "강남", "잠실", warp=False)
    assert a["cost"] == b["cost"] == 6 and a["warps"] == 0


@real
def test_ambiguous_and_city_prefix(world):
    mod, w = world
    assert "여러 역" in mod.route(w, "양평", "강남")["error"]
    r = mod.route(w, "서울 양평", "경기 양평")
    assert r["reachable"] and r["cost"] == 1 and r["warps"] == 1


@real
def test_deterministic(world):
    mod, w = world
    assert mod.route(w, "목동", "부산 동래")["path"] == mod.route(w, "목동", "부산 동래")["path"]
