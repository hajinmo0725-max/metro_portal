import copy

import pytest

from helpers import (DAEJEON_CITYHALL, GYODAE_2, GYODAE_3, GYODAE_BUSAN, INCHEON_CITYHALL, ISU_4, ISU_7,
                     SEOUL_CITYHALL_1, SEOUL_CITYHALL_2, YANGPYEONG_5, YANGPYEONG_GJ)
from metro_portal.graph import build_clusters, build_graph, build_portals
from metro_portal.ruleset import load_ruleset


@pytest.fixture
def rs():
    return copy.deepcopy(load_ruleset("strict"))


def run(stations, rs):
    cl = build_clusters(stations, rs)
    portals, capped = build_portals(stations, cl, rs)
    cof = {sid: c["id"] for c in cl for sid in c["station_ids"]}
    return cl, portals, capped, cof


def test_same_name_transfer_station_is_one_cluster(rs):
    # 같은 이름의 환승역 (같은 물리적 역): 1호선 시청 + 2호선 시청
    cl, portals, _, cof = run([SEOUL_CITYHALL_1, SEOUL_CITYHALL_2], rs)
    assert cof[SEOUL_CITYHALL_1["id"]] == cof[SEOUL_CITYHALL_2["id"]]
    assert len(cl) == 1
    assert portals == []  # 같은 역끼리는 포탈이 아니라 환승


def test_parenthetical_subname_transfer(rs):
    # 부역명 괄호가 붙은 역명: 2·3호선 교대(법원·검찰청)은 한 클러스터, 부산 교대와는 포탈
    cl, portals, _, cof = run([GYODAE_2, GYODAE_3, GYODAE_BUSAN], rs)
    assert cof[GYODAE_2["id"]] == cof[GYODAE_3["id"]] != cof[GYODAE_BUSAN["id"]]
    assert [p["name"] for p in portals] == ["교대"]
    assert portals[0]["degree"] == 2
    assert portals[0]["tier"] == "T1" and portals[0]["cost"] == rs["portals"]["T1"]["cost"]


def test_same_region_homonym_is_portal_not_transfer(rs):
    # 같은 권역 안의 동명이역: 5호선 양평(서울 영등포) vs 경의중앙선 양평역(경기 양평)
    cl, portals, _, cof = run([YANGPYEONG_5, YANGPYEONG_GJ], rs)
    assert cof[YANGPYEONG_5["id"]] != cof[YANGPYEONG_GJ["id"]]
    assert len(portals) == 1 and portals[0]["name"] == "양평"
    assert set(portals[0]["station_ids"]) == {YANGPYEONG_5["id"], YANGPYEONG_GJ["id"]}


def test_no_partial_match(rs):
    # 부분 일치 금지: 시청 vs 인천시청
    cl, portals, _, cof = run([SEOUL_CITYHALL_1, INCHEON_CITYHALL], rs)
    assert portals == []
    assert cof[SEOUL_CITYHALL_1["id"]] != cof[INCHEON_CITYHALL["id"]]


def test_city_hall_portal_excludes_incheon(rs):
    _, portals, _, _ = run([SEOUL_CITYHALL_1, SEOUL_CITYHALL_2, INCHEON_CITYHALL, DAEJEON_CITYHALL], rs)
    assert len(portals) == 1
    p = portals[0]
    assert p["name"] == "시청" and p["degree"] == 2
    assert INCHEON_CITYHALL["id"] not in p["station_ids"]


def test_alias_clusters_but_never_portals(rs):
    # 4호선 총신대입구(이수) ↔ 7호선 이수: 별칭으로 환승 클러스터
    far_isu = dict(ISU_7, id="far:1", lat=35.0, lon=129.0)
    cl, portals, _, cof = run([ISU_4, ISU_7, far_isu], rs)
    assert cof[ISU_4["id"]] == cof[ISU_7["id"]]
    # 먼 '이수'와는 7호선 '이수'의 정식명으로만 포탈. 부역명 '이수'로 4호선 레코드가 포탈에 붙지 않는다
    assert len(portals) == 1
    assert ISU_4["id"] not in portals[0]["station_ids"]
    rs["cluster"]["use_parenthetical_alias"] = False
    _, _, _, cof2 = run([ISU_4, ISU_7], rs)
    assert cof2[ISU_4["id"]] != cof2[ISU_7["id"]]


def test_distance_threshold_from_ruleset(rs):
    # 시청 1·2호선은 약 250m. D를 100m로 줄이면 환승이 아니라 포탈이 된다
    rs["cluster"]["transfer_distance_m"] = 100
    cl, portals, _, cof = run([SEOUL_CITYHALL_1, SEOUL_CITYHALL_2], rs)
    assert cof[SEOUL_CITYHALL_1["id"]] != cof[SEOUL_CITYHALL_2["id"]]
    assert len(portals) == 1


def test_tier_disabled(rs):
    rs["portals"]["T1"]["enabled"] = False
    _, portals, _, _ = run([YANGPYEONG_5, YANGPYEONG_GJ], rs)
    assert portals == []


def test_hub_cap(rs):
    rs["portals"]["hub_degree_cap"] = 2
    stations = [SEOUL_CITYHALL_1, DAEJEON_CITYHALL, dict(DAEJEON_CITYHALL, id="x:1", lat=35.0, lon=129.0)]
    _, portals, capped, _ = run(stations, rs)
    assert portals == [] and len(capped) == 1 and capped[0]["degree"] == 3


def test_subname_and_romanization_not_used_for_t1(rs):
    a = dict(YANGPYEONG_5, names=YANGPYEONG_5["names"] + [
        {"text": "교대", "lang": "ko", "script": "Hang", "source": "t", "official": True, "kind": "subname"},
        {"text": "Gyodae", "lang": "ko", "script": "Latn", "source": "t", "official": True, "kind": "romanization"}])
    _, portals, _, _ = run([a, GYODAE_BUSAN], rs)
    assert portals == []


def test_deterministic(rs):
    stations = [GYODAE_BUSAN, GYODAE_3, YANGPYEONG_GJ, GYODAE_2, YANGPYEONG_5, SEOUL_CITYHALL_2, SEOUL_CITYHALL_1]
    a = run(stations, rs)
    b = run(list(reversed(stations)), rs)
    assert [c["id"] for c in a[0]] == [c["id"] for c in b[0]]
    assert a[1] == b[1]


def test_warp_graph_edges(rs):
    stations = [YANGPYEONG_5, YANGPYEONG_GJ]
    cl, portals, _, _ = run(stations, rs)
    adj = build_graph(stations, [], cl, portals, rs)
    pid = portals[0]["id"]
    assert (pid, rs["portals"]["T1"]["cost"], "warp_in", "T1") in adj[YANGPYEONG_5["id"]]
    assert (YANGPYEONG_GJ["id"], 0, "warp_out", "T1") in adj[pid]
