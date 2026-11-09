"""5차 R2: 화면 표시 이름의 '역' 유지 규칙. 매칭용 정규화(포탈·클러스터)는 그대로다."""
import json
from pathlib import Path

import pytest

from metro_portal.names import display_names, region_names, strip_display_suffix
from metro_portal.normalize import normalize_name
from metro_portal.ruleset import load_ruleset

ROOT = Path(__file__).resolve().parent.parent
NORM = load_ruleset("strict")["normalize"]


def st(sid, name, addr="서울시 중구 세종대로 1"):
    return {"id": sid, "name_ko": name, "address": addr, "country": "KR"}


def cl(cid, name, sids):
    return {"id": cid, "name": name, "station_ids": sids, "countries": ["KR"]}


def run(clusters, stations):
    return display_names(clusters, {s["id"]: s for s in stations}, lambda n: strip_display_suffix(n, NORM))


def test_region_name_keeps_suffix_and_district_does_not():
    stations = [st("a", "서울역"), st("b", "서울"), st("c", "강남", "서울시 강남구 강남대로 1"), st("d", "수원역(분당)", "경기도 수원시 팔달구 1")]
    clusters = [cl("서울#1", "서울", ["a", "b"]), cl("강남#1", "강남", ["c"]), cl("수원#1", "수원", ["d"])]
    cd, sd, why = run(clusters, stations)
    assert cd == {"서울#1": "서울역", "강남#1": "강남", "수원#1": "수원역"}   # 구(강남구)는 지역 이름에 넣지 않는다
    assert sd["b"] == "서울역" and sd["a"] == "서울역"                        # 한 물리적 역은 한 표기
    assert sd["d"] == "수원역(분당)"                                         # 괄호 부역명 유지
    assert why == {"서울#1": "region", "수원#1": "region"}


def test_collision_keeps_suffix_only_where_raw_had_it():
    # 서울 교대(원래 이름 '교대') vs 부산 교대(동해선 원래 이름 '교대역' + 1호선 '교대') → 부산 쪽만 '교대역'
    stations = [st("s2", "교대(법원·검찰청)"), st("b1", "교대", "부산광역시 동래구 1"), st("bd", "교대역", "부산광역시 연제구 1")]
    clusters = [cl("교대#0", "교대", ["s2"]), cl("교대#1", "교대", ["b1", "bd"])]
    cd, sd, why = run(clusters, stations)
    assert cd == {"교대#0": "교대", "교대#1": "교대역"}
    assert sd["s2"] == "교대(법원·검찰청)" and sd["b1"] == "교대역"
    assert why == {"교대#1": "collision"}


def test_no_partial_match_and_matching_normalization_unchanged():
    stations = [st("x", "인천시청", "인천광역시 남동구 1"), st("y", "시청")]
    clusters = [cl("인천시청#1", "인천시청", ["x"]), cl("시청#1", "시청", ["y"])]
    cd, _, _ = run(clusters, stations)
    assert cd == {"인천시청#1": "인천시청", "시청#1": "시청"}
    # 매칭 정규화는 그대로: 서울역 → 서울, 양평역 → 양평
    assert normalize_name("서울역", NORM) == "서울" and normalize_name("양평역", NORM) == "양평"


def test_region_names_from_address_tokens():
    rs = region_names([st("a", "x", "경기도 가평군 가평읍 1"), st("b", "y", "부산광역시 해운대구 1"), st("c", "z", "춘춘시 오기")])
    assert {"경기", "가평", "부산"} <= rs and "해운대" not in rs and "춘춘" not in rs


@pytest.mark.skipif(not (ROOT / "web" / "data" / "kr_strict.json").exists(), reason="웹 번들 없음")
def test_real_bundle_display_names():
    d = json.loads((ROOT / "web" / "data" / "kr_strict.json").read_text(encoding="utf-8"))
    n = {(c["city"], c["n"]) for c in d["clusters"]}
    assert ("수도권", "서울역") in n and ("부산", "부산역") in n and ("대전", "대전역") in n
    assert ("부산", "동래") in n and ("부산", "동래역") in n          # 1·4호선 동래 / 동해선 동래역
    assert ("수도권", "강남") in n and ("수도권", "시청") in n
    # 포탈 이름(매칭 키)은 그대로 정규화 이름이다
    assert {"교대", "양평", "동래"} <= {p["n"] for p in d["portals"]}
