"""3차 B1: 인접 그래프 → 노선 시퀀스 (타이베이 Wikidata P197)."""
import json

import pytest

from metro_portal import ROOT
from metro_portal.lineseq import break_cycles, code_consecutive, decompose, parse_code


def test_code_parsing_and_consecutive():
    assert parse_code("BL12") == ("BL", 12, "")
    assert parse_code("R22A") == ("R", 22, "a")
    assert code_consecutive("R22", "R22A") and code_consecutive("A13", "A14a") and code_consecutive("A14a", "A15")
    # 같은 노선에 R22가 있으면 R22A는 지선 역이라 R23과 이어지지 않는다. A14가 없으면 A14a는 본선 역
    assert not code_consecutive("R22A", "R23", {"R21", "R22", "R22A", "R23"})
    assert code_consecutive("A14a", "A15", {"A13", "A14a", "A15"})
    assert not code_consecutive("G01", "G03") and not code_consecutive("O12", "O50") and not code_consecutive("BL12", "R11")


def test_branch_line_decomposition():
    # 중화신루선 축소판: O10-O11-O12-O13-O14 본선, O12-O50-O51 지선 (루저우)
    code = {n: n for n in ["O10", "O11", "O12", "O13", "O14", "O50", "O51"]}
    edges = [("O10", "O11"), ("O11", "O12"), ("O12", "O13"), ("O13", "O14"), ("O12", "O50"), ("O50", "O51")]
    seqs = decompose(list(code), edges, code)
    assert seqs[0] == ["O10", "O11", "O12", "O13", "O14"]
    assert seqs[1] == ["O12", "O50", "O51"]


def test_cycle_breaking_prefers_consecutive_codes():
    # 七張(G03)–新店(G01) 옛 철도선 진술이 G01-G02-G03 삼각형을 만든 실제 사례
    code = {n: n for n in ["G01", "G02", "G03", "G04", "G03A"]}
    edges = [("G01", "G02"), ("G02", "G03"), ("G03", "G04"), ("G03", "G03A"), ("G01", "G03")]
    kept, dropped = break_cycles(list(code), edges, code)
    assert dropped == [("G01", "G03")]
    seqs = decompose(list(code), kept, code)
    assert seqs[0] == ["G01", "G02", "G03", "G04"] and seqs[1] == ["G03", "G03A"]


def test_direction_follows_codes_and_isolated_nodes():
    code = {"x": "K03", "y": "K02", "z": "K01", "w": "K09"}
    seqs = decompose(list(code), [("x", "y"), ("y", "z")], code)
    assert seqs == [["z", "y", "x"], ["w"]]


TW = ROOT / "data" / "processed" / "tw"


@pytest.mark.skipif(not (TW / "lines.json").exists(), reason="tw data missing")
def test_real_taipei_lines():
    S = {s["id"]: s for s in json.loads((TW / "stations.json").read_text(encoding="utf-8"))["stations"]}
    L = {ln["id"]: ln for ln in json.loads((TW / "lines.json").read_text(encoding="utf-8"))["lines"]}
    assert set(L) == {"tp-br", "tp-r", "tp-g", "tp-o", "tp-bl", "tp-y", "ty-a", "nt-v", "nt-k", "nt-lb"}
    seq = lambda lid, sid="main": [S[x]["code"] for x in next(q for q in L[lid]["sequences"] if q["id"] == sid)["station_ids"]]  # noqa: E731
    assert seq("tp-bl")[0] == "BL01" and seq("tp-bl")[-1] == "BL23"
    assert seq("tp-r", "branch-R22A") == ["R22", "R22A"] and seq("tp-g", "branch-G03A") == ["G03", "G03A"]
    assert seq("tp-o", "branch-O54")[:2] == ["O12", "O50"]
    assert seq("ty-a")[0] == "A1"
    # 순서의 두 번째 근거: 좌표 기하가 전부 최적 순서와 같다
    val = json.loads((TW / "lines_validation.json").read_text(encoding="utf-8"))
    for v in val["lines"]:
        for g in v["geometry"]:
            assert g["ratio"] is None or (g["ratio"] < 1.0001 and g["same_order"]), (v["line"], g)
    # 공식명은 없다 (Wikidata P1448 0건) → 이름은 전부 official=False
    assert not any(n["official"] for s in S.values() for n in s["names"])
    assert all(s["country"] == "TW" for s in S.values())
