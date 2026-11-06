"""3차 A3·A4: 공식 환승 정보 우선 클러스터링과 좌표 복사 점검."""
import json

import pytest

from metro_portal import ROOT
from metro_portal.graph import build_clusters
from metro_portal.ruleset import load_ruleset
from metro_portal.transfer import OfficialTransfers, coord_copy_pairs

RS = load_ruleset("strict")
CODES = ROOT / "config" / "kr_transfer_codes.yaml"


def st(sid, name, lat, lon, line_no, raw="", flag=False, line_group=None):
    return {"id": sid, "name_ko": name, "lat": lat, "lon": lon, "line_no": line_no, "line_group": line_group or line_no,
            "line_name": line_no, "region": "", "transfer_flag": flag, "transfer_line_nos_raw": raw,
            "names": [{"text": name, "lang": "ko", "script": "Hang", "source": "t", "official": True, "kind": "primary"}]}


def clusters_by_name(stations, rs=RS):
    cl = build_clusters(stations, rs)
    return {tuple(sorted(c["station_ids"])) for c in cl}


def test_relation_kinds():
    a = st("a", "시청", 37.5652, 126.9772, "I4101", "S1102", True)       # 1호선, 2호선 환승 표기
    b = st("b", "시청", 37.5635, 126.9753, "S1102", "I4101", True)
    c = st("c", "부전", 35.1630, 129.0590, "I26K6")                        # 일반역
    d = st("d", "부전", 35.1600, 129.0600, "S2601")                        # 일반역
    e = st("e", "지축", 37.6480, 126.9140, "I1103")
    f = st("f", "지축", 37.6480, 126.9140, "I4106")                        # 3호선 패밀리 (직결 경계)
    g = st("g", "논현", 37.5110, 127.0214, "I11D1", "I11D1", True)        # 환승역인데 자기 노선만 → 불완전
    h = st("h", "논현", 37.5110, 127.0214, "S1107")
    o = OfficialTransfers([a, b, c, d, e, f, g, h], CODES)
    assert o.relation(a, b) == "yes"
    assert o.relation(c, d) == "no"
    assert o.relation(e, f) == "same_line"
    assert o.relation(g, h) == "unknown"
    assert o.info["g"]["reason"] == "환승역인데 노선 목록 없음"


def test_family_expansion_and_alias_literal():
    sinseol_1 = st("a", "신설동", 37.5760, 127.0250, "I4101", "S1102", True)   # 2호선을 본선 코드로 적음
    sinseol_2 = st("b", "신설동", 37.5745, 127.0255, "S1121")                  # 우리 레코드는 성수지선
    oksu = st("c", "옥수", 37.5406, 127.0186, "I1103", "I41K4", True)         # I41K4 = 경의중앙 (별칭)
    o = OfficialTransfers([sinseol_1, sinseol_2, oksu], CODES)
    assert o.relation(sinseol_1, sinseol_2) == "yes"
    assert {"I4108", "I4102"} <= o.info["c"]["lines"]
    assert "I41K2" not in o.info["c"]["lines"]   # 별칭 결과를 다시 패밀리로 넓혀 경춘선까지 번지면 안 된다
    assert o.info["c"]["unknown_codes"] == []


def test_unknown_code_marks_incomplete():
    x = st("x", "가", 37.0, 127.0, "I4101", "ZZZ9", True)
    o = OfficialTransfers([x], CODES)
    assert o.info["x"]["status"] == "unknown" and o.info["x"]["unknown_codes"] == ["ZZZ9"]


def test_official_no_splits_within_D_and_yes_merges_beyond_D():
    # 공식 no: 342m (D=500 이내)라도 분리 → 같은 이름 다른 클러스터 (포탈 후보)
    c = st("c", "부전", 35.1630, 129.0590, "I26K6")
    d = st("d", "부전", 35.1600, 129.0600, "S2601")
    assert clusters_by_name([c, d]) == {("c",), ("d",)}
    # 공식 yes: 700m (D 밖)라도 상한 1500m 안이면 묶음
    a = st("a", "가양", 37.5600, 126.8540, "S1109", "S1105", True)
    b = st("b", "가양", 37.5660, 126.8560, "S1105", "", False)
    assert clusters_by_name([a, b]) == {("a", "b")}
    # 공식 yes라도 상한을 넘으면 안 묶음 (좌표·코드 오류 방어)
    far = st("f", "가양", 37.6000, 126.8540, "S1105")
    assert ("a", "f") not in {tuple(sorted(x)) for x in clusters_by_name([a, far])}
    # distance 규칙(2차)이면 부전은 묶인다
    rs_d = load_ruleset("strict", overrides={"cluster": {"transfer_rule": "distance"}})
    assert clusters_by_name([c, d], rs_d) == {("c", "d")}


def test_unknown_and_same_line_fall_back_to_distance():
    e = st("e", "지축", 37.6480, 126.9140, "I1103")
    f = st("f", "지축", 37.64803, 126.91402, "I4106")
    assert clusters_by_name([e, f]) == {("e", "f")}
    # 정보 없는 같은 이름 같은 권역 동명이역 (양평, 53km) → 거리로 분리
    y1 = st("y1", "양평", 37.525614, 126.886177, "S1105")
    y2 = st("y2", "양평역", 37.492674, 127.491858, "I4108", "", True)   # 환승역 표기만, 목록 없음 → unknown
    assert clusters_by_name([y1, y2]) == {("y1",), ("y2",)}


def test_partial_name_never_matches_under_official_rule():
    a = st("a", "시청", 37.5652, 126.9772, "I4101", "S2801", True)     # 인천1호선을 환승노선으로 적어도
    b = st("b", "인천시청", 37.4570, 126.7020, "S2801", "I4101", True)  # 이름이 다르면 묶지 않는다 (부분 일치 금지)
    assert clusters_by_name([a, b]) == {("a",), ("b",)}


def test_coord_copy_pairs():
    x = st("x", "동래", 35.2058, 129.0786, "L2604", "S2601", True)
    y = st("y", "동래", 35.20586, 129.07866, "I26K6")   # 약 8m, 공식 no → 의심
    z = st("z", "동래", 35.2058, 129.0786, "S2601", "L2604", True)   # 공식 yes → 제외
    o = OfficialTransfers([x, y, z], CODES)
    res = coord_copy_pairs([x, y, z], o, RS["normalize"], 20)
    assert {(r["a"], r["b"], r["relation"]) for r in res} == {("x", "y", "no"), ("y", "z", "no")}


AUDIT = ROOT / "data" / "processed" / "kr" / "transfer_audit.json"


@pytest.mark.skipif(not AUDIT.exists(), reason="transfer_audit.json missing")
def test_real_audit_results():
    a = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert a["names_cluster_count_changed"] == {"부전": [1, 2]}
    assert a["portals_added"] == ["부전 [부산:동해선 ↔ 부산:부산 도시철도 1호선]"] and a["portals_removed"] == []
    # 좌표 복사 의심(공식 no, 20m 미만)은 현재 0건이고, 2차에서 고친 동해선 동래를 되돌리면 잡힌다
    assert not [p for p in a["coord_copy"]["pairs"] if p["relation"] == "no"]
    reg = {r["id"]: r["detected"] for r in a["coord_copy"]["regression"]}
    assert reg["kr:I26K6:8005"] is True
