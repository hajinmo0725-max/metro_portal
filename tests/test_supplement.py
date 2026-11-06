"""3차 A6: 표준데이터 미수록 개통 노선 보충 (GTX-A)."""
import json

import pytest

from metro_portal import ROOT

PROC = ROOT / "data" / "processed" / "kr"
pytestmark = pytest.mark.skipif(not (PROC / "lines.json").exists(), reason="processed data missing")


def load(n):
    return json.loads((PROC / n).read_text(encoding="utf-8"))


def test_gtx_a_only_confirmed_sections():
    S = {s["id"]: s for s in load("stations.json")["stations"]}
    gtx = [s for s in S.values() if s["line_no"] == "XGTXA"]
    assert sorted(s["code"] for s in gtx) == ["X101", "X102", "X103", "X105", "X106", "X108", "X109", "X110", "X111"]
    assert all(s["source"] == "kric_metro_supplement" and s["opened"] for s in gtx)
    for s in gtx:  # 다국어 파일의 위·경도 열 뒤바뀜이 바로잡혔는지
        assert 37.0 < s["lat"] < 38.0 and 126.5 < s["lon"] < 127.5
    ln = next(x for x in load("lines.json")["lines"] if x["id"] == "gtx-a")
    seqs = {q["id"]: [S[i]["name_ko"] for i in q["station_ids"]] for q in ln["sequences"]}
    assert seqs == {"north": ["운정중앙", "킨텍스", "대곡", "연신내", "서울역"], "south": ["수서역", "성남역", "구성역", "동탄역"]}
    edges = {frozenset((S[e["a"]]["name_ko"], S[e["b"]]["name_ko"])) for e in load("ride_edges.json")["edges"] if e["line"] == "gtx-a"}
    assert len(edges) == 7
    assert frozenset(("서울역", "수서역")) not in edges   # 개통 미확인 구간은 넣지 않는다


@pytest.mark.skipif(not (PROC / "strict" / "clusters.json").exists(), reason="clusters missing")
def test_gtx_a_joins_existing_transfer_stations():
    C = load("strict/clusters.json")["clusters"]
    of = {sid: c for c in C for sid in c["station_ids"]}
    for code, n_min in (("X103", 4), ("X105", 3), ("X106", 5), ("X108", 3), ("X109", 2), ("X110", 2)):
        assert len(of[f"kr:XGTXA:{code}"]["station_ids"]) >= n_min, code
    for code in ("X101", "X102", "X111"):  # 운정중앙·킨텍스·동탄은 단독역
        assert len(of[f"kr:XGTXA:{code}"]["station_ids"]) == 1
