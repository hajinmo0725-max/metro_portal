"""N1: ruleset 상속(extends)·환승 비용 1 ruleset·스코프 제외·환승 비용 반영 지표."""
import json
from pathlib import Path

import pytest
import yaml

from helpers import st
from metro_portal.graph import build_clusters, build_graph, build_portals
from metro_portal.metrics import cluster_graph, components, diameter, diameter_station_level
from metro_portal.ruleset import RulesetError, deep_merge, load_ruleset

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed" / "kr"


def test_extends_inherits_and_overrides():
    base = load_ruleset("strict")
    t1 = load_ruleset("strict_transfer1")
    assert t1["name"] == "strict_transfer1"
    assert t1["costs"] == {"ride": 1, "transfer": 1}
    # 나머지는 부모 그대로
    for sec in ("normalize", "cluster", "portals", "metrics"):
        assert t1[sec] == base[sec], sec
    assert base["costs"]["transfer"] == 0  # 부모는 오염되지 않는다


def test_overrides_and_rename():
    rs = load_ruleset("strict", overrides={"cluster": {"transfer_distance_m": 300}}, name="strict_d300")
    assert rs["name"] == "strict_d300"
    assert rs["cluster"]["transfer_distance_m"] == 300
    assert rs["cluster"]["use_parenthetical_alias"] is True


def test_deep_merge_replaces_lists():
    assert deep_merge({"a": [1, 2], "b": {"x": 1, "y": 2}}, {"a": [3], "b": {"y": 5}}) == {"a": [3], "b": {"x": 1, "y": 5}}


def test_extends_cycle(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text(f"extends: {b}\nname: a\n", encoding="utf-8")
    b.write_text(f"extends: {a}\nname: b\n", encoding="utf-8")
    with pytest.raises(RulesetError):
        load_ruleset(str(a))


def _toy(transfer_cost):
    # A1-A2 (노선 L1), B1-B2 (노선 L2), A2와 B1은 같은 이름·같은 위치 → 환승 클러스터
    stations = [
        st("L1:1", "가", 37.0, 127.000, line="L1"),
        st("L1:2", "나", 37.0, 127.010, line="L1"),
        st("L2:1", "나", 37.0, 127.0101, line="L2"),
        st("L2:2", "다", 37.0, 127.020, line="L2"),
    ]
    rides = [{"line": "L1", "a": "L1:1", "b": "L1:2"}, {"line": "L2", "a": "L2:1", "b": "L2:2"}]
    rs = load_ruleset("strict", overrides={"costs": {"transfer": transfer_cost}})
    cl = build_clusters(stations, rs)
    portals, _ = build_portals(stations, cl, rs)
    adj = build_graph(stations, rides, cl, portals, rs)
    return stations, rides, cl, portals, adj, rs


@pytest.mark.parametrize("t", [0, 1, 2])
def test_station_level_diameter_counts_transfer(t):
    stations, rides, cl, portals, adj, rs = _toy(t)
    assert len(cl) == 3
    d = diameter_station_level(adj, cl, [c["id"] for c in cl])
    assert d["value"] == 2 + t  # 가→나(1) 환승(t) 나→다(1)
    if t == 0:  # 환승 0이면 클러스터 접힘 그래프와 같은 값
        g = cluster_graph(cl, rides, portals, rs, True)
        comp = components(g, set(g))[0]
        assert diameter(g, [c for c in comp if not c.startswith("P:")], 4000, 42)["value"] == d["value"]


def test_scope_excludes_maglev_config():
    scope = yaml.safe_load(open(ROOT / "config" / "kr_scope.yaml", encoding="utf-8"))
    groups = [e["line_group"] for e in scope["exclude_line_groups"]]
    assert "S28M1:자기부상철도" in groups


@pytest.mark.skipif(not (PROC / "stations.json").exists(), reason="processed data missing")
def test_scope_excludes_maglev_data():
    doc = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))
    assert not [s for s in doc["stations"] if s["line_group"] == "S28M1:자기부상철도"]
    assert doc["meta"]["counts"]["excluded_by_scope"] == len(doc["meta"]["excluded_by_scope"]["stations"]) > 0
    lines = json.loads((PROC / "lines.json").read_text(encoding="utf-8"))["lines"]
    assert "incheon-maglev" not in {ln["id"] for ln in lines}


@pytest.mark.skipif(not (PROC / "strict" / "metrics.json").exists(), reason="processed data missing")
def test_real_station_level_diameter_matches_cluster_level_when_transfer_0():
    rs = load_ruleset("strict")
    stations = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]
    rides = json.loads((PROC / "ride_edges.json").read_text(encoding="utf-8"))["edges"]
    cl = build_clusters(stations, rs)
    portals, _ = build_portals(stations, cl, rs)
    adj = build_graph(stations, rides, cl, portals, rs)
    m = json.loads((PROC / "strict" / "metrics.json").read_text(encoding="utf-8"))
    d = diameter_station_level(adj, cl, [c["id"] for c in cl])
    assert d["value"] == m["with_warp"]["diameter"]["value"]
    assert d["mean_cost"] == m["with_warp"]["diameter"]["mean_cost"]


@pytest.mark.skipif(not (PROC / "stations.json").exists(), reason="processed data missing")
@pytest.mark.parametrize("D,expect", [(300, {"노원": 2, "잠실": 2, "신촌": 2}), (500, {"노원": 1, "잠실": 1, "신촌": 2}),
                                      (1000, {"노원": 1, "잠실": 1, "신촌": 1})])
def test_D_boundary_cases(D, expect):
    """N4: D에 따라 환승 ↔ 포탈 경계가 바뀌는 실제 사례 (노원 4·7호선 306m, 잠실 2·8호선 394m, 신촌 2호선·경의중앙 701m).
    2차 거리 규칙(transfer_rule: distance) 전용. 3차 기본(official_first)은 아래 테스트."""
    from metro_portal.world import build_world, load_base
    rs = load_ruleset("strict", overrides={"cluster": {"transfer_distance_m": D, "transfer_rule": "distance"}})
    w = build_world(*load_base(), rs)
    cnt = {}
    for c in w["clusters"]:
        cnt[c["name"]] = cnt.get(c["name"], 0) + 1
    for name, n in expect.items():
        assert cnt[name] == n, (D, name)
    names = {p["name"] for p in w["portals"]}
    assert ("신촌" in names) == (D < 701)


@pytest.mark.skipif(not (PROC / "stations.json").exists(), reason="processed data missing")
@pytest.mark.parametrize("D", [300, 500, 1000])
def test_official_first_ignores_D_for_official_pairs(D):
    """3차 A3: 공식 환승 정보가 있는 쌍은 D와 무관. 노원·잠실은 공식 yes라 항상 환승, 신촌·부전은 공식 no라 항상 분리."""
    from metro_portal.world import build_world, load_base
    rs = load_ruleset("strict", overrides={"cluster": {"transfer_distance_m": D}})
    assert rs["cluster"]["transfer_rule"] == "official_first"
    w = build_world(*load_base(), rs)
    cnt = {}
    for c in w["clusters"]:
        cnt[c["name"]] = cnt.get(c["name"], 0) + 1
    assert (cnt["노원"], cnt["잠실"], cnt["신촌"], cnt["부전"]) == (1, 1, 2, 2)
    names = {p["name"] for p in w["portals"]}
    assert {"신촌", "부전"} <= names and not ({"노원", "잠실"} & names)


@pytest.mark.skipif(not (PROC / "ruleset_compare.json").exists(), reason="ruleset_compare.json missing")
def test_ruleset_compare_reference_matches_strict_metrics():
    """N4: 비교표의 기준 조합(환승 0, D=500)은 strict 빌드 지표와 같아야 한다. 환승 비용은 포탈 목록을 바꾸지 않는다."""
    cmp_ = json.loads((PROC / "ruleset_compare.json").read_text(encoding="utf-8"))
    m = json.loads((PROC / "strict" / "metrics.json").read_text(encoding="utf-8"))
    ref = next(r for r in cmp_["rows"] if r["transfer"] == 0 and r["D"] == 500)
    assert ref["counts"] == m["counts"]
    assert ref["with_warp"]["diameter"] == m["with_warp"]["diameter"]
    assert len(cmp_["rows"]) == 6
    by = {(r["transfer"], r["D"]): r for r in cmp_["rows"]}
    for d in (300, 500, 1000):
        assert by[(0, d)]["counts"]["portals_total"] == by[(1, d)]["counts"]["portals_total"]
        assert by[(1, d)]["with_warp"]["diameter"]["value"] >= by[(0, d)]["with_warp"]["diameter"]["value"]
    t1 = json.loads((PROC / "strict_transfer1" / "metrics.json").read_text(encoding="utf-8"))
    assert by[(1, 500)]["with_warp"]["diameter"]["value"] == t1["with_warp"]["diameter"]["value"]
