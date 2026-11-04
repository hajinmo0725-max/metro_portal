"""실제 처리 산출물(data/processed/kr)에 대한 회귀 테스트. 산출물이 없으면 건너뛴다."""
import json
from pathlib import Path

import pytest

from metro_portal.graph import build_clusters, build_portals
from metro_portal.normalize import normalize_name
from metro_portal.ruleset import load_ruleset

PROC = Path(__file__).resolve().parent.parent / "data" / "processed" / "kr"
pytestmark = pytest.mark.skipif(not (PROC / "stations.json").exists(), reason="processed data missing")


@pytest.fixture(scope="module")
def built():
    rs = load_ruleset("strict")
    stations = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]
    cl = build_clusters(stations, rs)
    portals, _ = build_portals(stations, cl, rs)
    cof = {sid: c["id"] for c in cl for sid in c["station_ids"]}
    by_name = {}
    for s in stations:
        by_name.setdefault(normalize_name(s["name_ko"], rs["normalize"]), []).append(s)
    return rs, stations, cl, {p["name"]: p for p in portals}, cof, by_name


def test_station_ids_unique(built):
    _, stations, *_ = built
    assert len({s["id"] for s in stations}) == len(stations)


def test_every_station_in_one_cluster(built):
    _, stations, cl, *_ = built
    ids = [sid for c in cl for sid in c["station_ids"]]
    assert sorted(ids) == sorted(s["id"] for s in stations)


def test_seoul_gyodae_lines_2_3_same_cluster(built):
    _, _, _, portals, cof, by_name = built
    seoul = [s for s in by_name["교대"] if s["region"] == "서울특별시"]
    assert len(seoul) == 2 and len({cof[s["id"]] for s in seoul}) == 1
    assert "교대" in portals


def test_yangpyeong_two_clusters_and_portal(built):
    _, _, _, portals, cof, by_name = built
    assert len({cof[s["id"]] for s in by_name["양평"]}) == 2
    assert portals["양평"]["degree"] == 2


def test_incheon_city_hall_not_in_city_hall_portal(built):
    _, _, _, portals, _, by_name = built
    inc = {s["id"] for s in by_name["인천시청"]}
    assert inc and not (inc & set(portals["시청"]["station_ids"]))


def test_isu_alias_cluster(built):
    _, _, _, _, cof, by_name = built
    assert cof[by_name["총신대입구"][0]["id"]] == cof[by_name["이수"][0]["id"]]


def test_seoul_station_variants_cluster(built):
    # '서울'(공항철도), '서울역'(1·4호선), '서울역(경의선)' → 하나의 클러스터
    _, _, _, portals, cof, by_name = built
    assert len({cof[s["id"]] for s in by_name["서울"]}) == 1
    assert "서울" not in portals
