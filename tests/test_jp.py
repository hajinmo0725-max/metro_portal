"""5차 T1: 도쿄권 Wikidata 정제 (라벨 정리, 역번호, 순서)."""
import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("b23", ROOT / "pipeline" / "23_build_jp.py")
b23 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b23)
SCOPE = yaml.safe_load(open(ROOT / "config" / "jp_scope.yaml", encoding="utf-8"))
b23._CFG.update(prefix=re.compile(SCOPE["label_prefix_pattern"]), suffixes=tuple(SCOPE["name_suffixes"]))
JP = ROOT / "data" / "processed" / "jp"


@pytest.mark.parametrize("label,expected", [
    ("JR東日本東京駅", "東京"), ("京王電鉄 京王線新宿駅", "新宿"), ("東京メトロ南北線市ケ谷駅", "市ケ谷"),
    ("東急電鉄・東京メトロ・都営地下鉄目黒駅", "目黒"), ("相鉄海老名駅", "海老名"), ("都営練馬駅", "練馬"),
    # 공식 역명에 붙은 운영사 약칭은 남긴다
    ("京急蒲田駅", "京急蒲田"), ("京成高砂駅", "京成高砂"), ("小田急相模原駅", "小田急相模原"), ("東武練馬駅", "東武練馬"),
    # 동음이의 괄호, 한 글자 역, 노면전차 정류장
    ("府中駅 (東京都)", "府中"), ("柏駅", "柏"), ("荒川車庫前停留場", "荒川車庫前"),
])
def test_strip_label(label, expected):
    assert b23.strip_label(label) == expected


def test_norm_code_keeps_numbering_drops_telegraph_codes():
    pat = re.compile(SCOPE["code_pattern"])
    assert b23.norm_code("JY 01", pat) == "JY01" and b23.norm_code("G-09", pat) == "G09" and b23.norm_code("KS1", pat) == "KS01"
    assert b23.norm_code("ミウ", pat) is None and b23.norm_code("MI-U", pat) is None and b23.norm_code("URW", pat) is None


def test_non_station_pattern():
    n = re.compile(SCOPE["non_station_pattern"])
    assert all(n.search(x) for x in ["根古屋信号場 (京成)", "相模大野分岐点", "東京貨物ターミナル駅", "相模国分信号所"])
    assert not any(n.search(x) for x in ["荒川車庫前停留場", "新宿駅", "貨物線前"])


real = pytest.mark.skipif(not (JP / "lines.json").exists(), reason="도쿄 데이터 없음")


@real
def test_tokyo_metro_lines_in_code_order():
    lines = {l["name"]: l for l in json.loads((JP / "lines.json").read_text(encoding="utf-8"))["lines"]}
    st = {s["id"]: s for s in json.loads((JP / "stations.json").read_text(encoding="utf-8"))["stations"]}
    # 도쿄메트로 긴자선: G01(시부야) → G19(아사쿠사) 역번호 오름차순 한 줄
    g = lines["東京メトロ銀座線"]["sequences"]
    assert len(g) == 1
    codes = [st[x]["code"] for x in g[0]["station_ids"]]
    assert codes == sorted(codes) and codes[0] == "G01" and codes[-1] == "G19"
    assert [st[x]["name_ko"] for x in g[0]["station_ids"]][:3] == ["渋谷", "表参道", "外苑前"]


@real
def test_no_operator_prefix_or_non_station_left():
    st = json.loads((JP / "stations.json").read_text(encoding="utf-8"))["stations"]
    nonst = re.compile(SCOPE["non_station_pattern"])
    assert not [s["name_ko"] for s in st if re.match(r"^(JR東日本|東京メトロ|都営地下鉄|京王電鉄|西武鉄道|相模鉄道|東急電鉄)", s["name_ko"])]
    assert not [s["name_ko"] for s in st if nonst.search(s["name_ja"] or "")]
    # 이름 출처 등급: ja 라벨 = native_label, P1448 = official, en = foreign_label
    grades = {(n["source"], n["lang"]): n["grade"] for s in st for n in s["names"]}
    assert grades[("wikidata_label", "ja")] == "native_label" and grades[("wikidata_p1448", "ja")] == "official"
    assert grades[("wikidata_label", "en")] == "foreign_label"


@real
def test_edges_reference_records_and_lines_have_edges():
    st = {s["id"] for s in json.loads((JP / "stations.json").read_text(encoding="utf-8"))["stations"]}
    edges = json.loads((JP / "ride_edges.json").read_text(encoding="utf-8"))["edges"]
    assert edges and all(e["a"] in st and e["b"] in st and e["a"] != e["b"] for e in edges)
    lines = json.loads((JP / "lines.json").read_text(encoding="utf-8"))["lines"]
    used = {e["line"] for e in edges}
    assert {l["id"] for l in lines} == used
