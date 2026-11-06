"""4차 Q0-5: 개통 예정 노선 (config/kr_planned.yaml) 비활성 등록과 켰을 때의 미리보기."""
import json

import pytest
import yaml

from metro_portal import ROOT
from metro_portal.planned import apply_line_defs, load_planned, station_records

PROC = ROOT / "data" / "processed" / "kr"


def test_planned_lines_disabled_by_default():
    assert load_planned() == []
    allp = load_planned(include_disabled=True)
    assert {p["id"] for p in allp} == {"yangsan", "busan-2-yangsan-ext", "donghae-bugulsan-ext"}
    assert all(p["enabled"] is False for p in allp)


def test_postponed_lines_not_registered():
    cfg = yaml.safe_load(open(ROOT / "config" / "kr_planned.yaml", encoding="utf-8"))
    ids = " ".join(p["id"] + p.get("name", "") + p.get("line_name", "") for p in cfg["lines"])
    for bad in ("위례", "동북", "신안산", "교외", "수서"):
        assert bad not in ids
    names = {s["name"] for p in cfg["lines"] for s in p["stations"]}
    assert "삼성" not in names and "창릉" not in names


def test_station_records_shape(tmp_path):
    recs = station_records(load_planned(include_disabled=True))
    ids = [r["id"] for r in recs]
    assert len(ids) == len(set(ids))
    for r in recs:
        assert 35.0 < r["lat"] < 36.0 and 128.5 < r["lon"] < 129.6
        assert "transfer_line_nos_raw" not in r  # 공식 환승 정보 없음 → 거리 D 판정
        assert r["names"][0]["grade"] == "official"
    if (PROC / "stations.json").exists():
        existing = {s["id"] for s in json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]}
        assert not (set(ids) & existing), "계획 역 id가 기존 역 id와 겹친다"


def test_disabled_lines_do_not_touch_outputs():
    if not (PROC / "stations.json").exists():
        pytest.skip("processed data missing")
    S = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))
    assert S["meta"]["counts"]["planned_enabled"] == 0
    assert not any(s.get("planned") for s in S["stations"])
    L = json.loads((PROC / "lines.json").read_text(encoding="utf-8"))["lines"]
    assert not any(ln.get("planned") or ln.get("planned_extensions") for ln in L)


def test_apply_line_defs_new_line_and_extension():
    planned = load_planned(include_disabled=True)
    defs = {("S2602", "부산 도시철도 2호선"): {"source": {"line_no": "S2602", "name": "부산 도시철도 2호선"}, "id": "busan-2"},
            ("I26K6", "동해선"): {"source": {"line_no": "I26K6", "name": "동해선"}, "id": "donghae",
                                  "sequences": [{"id": "main", "stops": ["부전역", "태화강역"]}]}}
    rows = []
    apply_line_defs(planned, defs, rows)
    assert rows and rows[0]["노선번호"] == "XYS01"
    assert defs[("XYS01", "양산도시철도")]["sequences"][0]["stops"][0] == "노포"
    assert defs[("S2602", "부산 도시철도 2호선")]["branches"] == [{"id": "yangsan-ext", "stops": ["양산", "양산중앙(종합운동장)"]}]
    assert [q["id"] for q in defs[("I26K6", "동해선")]["sequences"]] == ["main", "bugulsan-ext"]


@pytest.mark.skipif(not (PROC / "planned_preview.json").exists(), reason="preview missing")
def test_preview_new_portal_singi():
    r = json.loads((PROC / "planned_preview.json").read_text(encoding="utf-8"))["rulesets"]["strict"]
    assert [p["id"] for p in r["portals_added"]] == ["P:T1:신기"]
    merged = {m["cluster"].split("#")[0] for m in r["merged_with_existing"]}
    assert merged == {"노포", "양산중앙"}  # 양산선 노포 = 부산1호선 노포, 양산선 양산중앙 = 2호선 연장 양산중앙
    assert r["portals_changed"] == [] and r["portals_removed"] == []
