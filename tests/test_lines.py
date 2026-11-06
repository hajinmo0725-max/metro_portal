import importlib.util
import json
from pathlib import Path

import pytest

from metro_portal.kric import code_key
from metro_portal.ruleset import load_ruleset

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("lines03", ROOT / "pipeline" / "03_build_kr_lines.py")
lines03 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lines03)


def test_parse_stops_variants():
    assert lines03.parse_stops("A01-서울,A02-공덕") == [("A01", "서울"), ("A02", "공덕")]
    assert lines03.parse_stops("D04-신사+D05-논현") == [("D04", "신사"), ("D05", "논현")]
    assert lines03.parse_stops('"8001-부전역, 8002-거제해맞이역"') == [("8001", "부전역"), ("8002", "거제해맞이역")]
    # 역번호에 하이픈이 들어간 지선 표기
    assert lines03.parse_stops("211-1-용답, 211-2-신답") == [("211-1", "용답"), ("211-2", "신답")]
    assert lines03.parse_stops("역번호없음") == [("", "역번호없음")]


@pytest.mark.parametrize("a,b", [("D007", "D07"), ("0522", "522"), ("100", "0100"), ("P549", "p549"), ("211-1", "211-1")])
def test_code_key_equivalence(a, b):
    assert code_key(a) == code_key(b)


def test_code_key_distinct():
    assert code_key("211-1") != code_key("211")
    assert code_key("D7") != code_key("7")


def test_apply_patch_order():
    stops = ["a", "b", "c", "d"]
    out = lines03.apply_patch(stops, {"remove": ["c"], "insert_after": {"b": ["x", "y"]}, "prepend": ["p@G"], "append": ["z"]})
    assert out == ["p@G", "a", "b", "x", "y", "d", "z"]
    assert lines03.apply_patch(stops, {"reverse": True}) == ["d", "c", "b", "a"]


def _st(sid, name, code, group):
    return {"id": sid, "name_ko": name, "code": code, "line_group": group}


def test_resolver_prefers_code_then_name_then_code_only():
    norm = load_ruleset("strict")["normalize"]
    stations = [_st("x1", "서울역", "1001", "G1:경부선"), _st("x2", "서울역", "0133", "G1:1호선"),
                _st("x3", "디지털미디어시티역", "1266", "G2:경의중앙선")]
    r = lines03.Resolver(stations, norm)
    assert r.resolve("서울역", ["G1:경부선", "G1:1호선"], "0133")[0] == "x2"
    assert r.resolve("서울", ["G1:1호선"])[0] == "x2"
    assert r.resolve("서울역@G1:경부선", ["G1:1호선"])[0] == "x1"
    sid, how = r.resolve("디엠시역", ["G2:경의중앙선"], "1266")
    assert sid == "x3" and how == "code-only"
    assert r.resolve("없는역", ["G1:경부선"])[0] is None


VAL = ROOT / "data" / "processed" / "kr" / "lines_validation.json"


@pytest.mark.skipif(not VAL.exists(), reason="processed data missing")
def test_m2_validation_regression():
    v = json.loads(VAL.read_text(encoding="utf-8"))
    assert v["stop_failures"] == []
    assert v["unused_line_defs"] == []
    assert v["totals"]["outliers_unexplained"] == 0
    # 시퀀스에 안 들어간 역은 의도적으로 남긴 경의중앙선 광운대 레코드 하나뿐
    # 4차 Q5: 유일한 미편입 역이던 광운대역[경의중앙선] 고아 레코드를 kr_scope.yaml exclude_stations로 뺐다
    assert v["stations_not_sequenced"] == []


@pytest.mark.skipif(not VAL.exists(), reason="processed data missing")
def test_branches_are_separate_sequences():
    lines = {l["id"]: l for l in json.loads((ROOT / "data/processed/kr/lines.json").read_text(encoding="utf-8"))["lines"]}
    assert [s["id"] for s in lines["seoul-5"]["sequences"]] == ["main", "macheon"]
    assert {s["id"] for s in lines["seoul-1-gyeongbu"]["sequences"]} == {"main", "gwangmyeong", "seodongtan"}
    assert lines["seoul-2"]["sequences"][0]["circular"] is True
