"""3차 A5: OSM route relation 파서 (pyosmium). 실데이터는 Geofabrik 차단으로 못 받아서 합성 .osm으로 고정한다."""
import importlib.util

import pytest

from metro_portal import ROOT

osmium = pytest.importorskip("osmium")

XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" lat="37.5652" lon="126.9772" version="1"><tag k="name" v="시청"/><tag k="name:en" v="City Hall"/></node>
  <node id="2" lat="37.5662" lon="126.9824" version="1"><tag k="name" v="을지로입구"/></node>
  <node id="3" lat="37.5665" lon="126.9910" version="1"><tag k="name" v="을지로3가"/></node>
  <node id="4" lat="37.5660" lon="126.9800" version="1"><tag k="public_transport" v="platform"/></node>
  <relation id="10" version="1">
    <member type="node" ref="1" role="stop"/>
    <member type="node" ref="4" role="platform"/>
    <member type="node" ref="2" role="stop"/>
    <member type="node" ref="3" role="stop_exit_only"/>
    <tag k="type" v="route"/><tag k="route" v="subway"/><tag k="name" v="2호선"/>
  </relation>
  <relation id="11" version="1">
    <member type="node" ref="3" role="stop"/>
    <tag k="type" v="route"/><tag k="route" v="bus"/>
  </relation>
</osm>
"""


def test_read_routes_order_and_filter(tmp_path):
    from metro_portal.osm import read_routes, stop_names
    f = tmp_path / "t.osm"
    f.write_text(XML, encoding="utf-8")
    routes = read_routes(f, ["subway", "light_rail"], ["stop", "stop_entry_only", "stop_exit_only"])
    assert [r["id"] for r in routes] == [10]                       # 버스 노선 제외
    assert [n["id"] for n in routes[0]["stops"]] == [1, 2, 3]      # 정차 순서 보존, 플랫폼 제외
    assert stop_names(routes[0]["stops"][0], ["name:en", "name"]) == ["City Hall", "시청"]
    assert abs(routes[0]["stops"][0]["lat"] - 37.5652) < 1e-6


def test_match_stops_name_and_distance(tmp_path):
    from metro_portal.osm import read_routes
    from metro_portal.ruleset import load_ruleset
    spec = importlib.util.spec_from_file_location("v13", ROOT / "pipeline" / "13_validate_osm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    f = tmp_path / "t.osm"
    f.write_text(XML, encoding="utf-8")
    routes = read_routes(f, ["subway"], ["stop"])
    st = [{"id": "a", "name_ko": "시청", "lat": 37.5653, "lon": 126.9771},
          {"id": "b", "name_ko": "인천시청", "lat": 37.5662, "lon": 126.9824},     # 부분 일치 금지
          {"id": "c", "name_ko": "을지로입구", "lat": 37.60, "lon": 126.9824}]     # 이름은 같지만 4km 밖
    r = mod.match_stops(routes, st, load_ruleset("strict")["normalize"], 400)
    assert [n["match"] for n in r[0]["stops"]] == ["a", None]


def test_compare_flags_order_disagreement_with_real_stations(tmp_path):
    """실데이터 2호선 앞 역들로 합성 OSM 노선을 만들고 두 역 순서를 바꾸면 '같은 노선에 있는데 비인접'으로 잡히는지."""
    import json
    from metro_portal.osm import read_routes
    from metro_portal.ruleset import load_ruleset
    proc = ROOT / "data" / "processed" / "kr"
    if not (proc / "lines.json").exists():
        pytest.skip("processed data missing")
    spec = importlib.util.spec_from_file_location("v13b", ROOT / "pipeline" / "13_validate_osm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    st = json.loads((proc / "stations.json").read_text(encoding="utf-8"))["stations"]
    sid = {s["id"]: s for s in st}
    edges = json.loads((proc / "ride_edges.json").read_text(encoding="utf-8"))["edges"]
    chk = json.loads((proc / "lines_check.json").read_text(encoding="utf-8"))
    wd = json.loads((proc / "wikidata_stations.json").read_text(encoding="utf-8"))["items"]
    line = next(ln for ln in json.loads((proc / "lines.json").read_text(encoding="utf-8"))["lines"] if ln["id"] == "seoul-2")
    seq = [sid[x] for x in line["sequences"][0]["station_ids"][:6]]
    osm_order = [seq[0], seq[1], seq[3], seq[2], seq[4], seq[5]]          # 2·3번째 역 순서를 바꾼 OSM
    nodes = "".join(f'<node id="{i + 1}" lat="{s["lat"]}" lon="{s["lon"]}" version="1"><tag k="name" v="{s["name_ko"]}"/></node>'
                    for i, s in enumerate(osm_order))
    members = "".join(f'<member type="node" ref="{i + 1}" role="stop"/>' for i in range(len(osm_order)))
    f = tmp_path / "k.osm"
    f.write_text(f'<?xml version="1.0"?><osm version="0.6">{nodes}<relation id="9" version="1">{members}'
                 '<tag k="type" v="route"/><tag k="route" v="subway"/><tag k="name" v="2호선"/></relation></osm>', encoding="utf-8")
    routes = mod.match_stops(read_routes(f, ["subway"], ["stop"]), st, load_ruleset("strict")["normalize"], 400)
    rows, extra, coords, stats = mod.compare(routes, st, edges, chk, wd, {"coord_flag_m": 300})
    by = {frozenset((r["a"], r["b"])): r for r in rows if r["line"] == "seoul-2"}
    n = [s["name_ko"] for s in seq]
    assert by[frozenset((n[0], n[1]))]["osm"] == "adjacent"
    assert by[frozenset((n[1], n[2]))]["osm"] == "not_adjacent"         # 우리 순서 1-2가 OSM에선 이웃 아님
    assert by[frozenset((n[1], n[2]))]["verdict"] == "suspect"          # Wikidata는 인접이라 근거 1개 → 의심만
    assert all(r["osm"] == "no_info" for r in rows if r["line"] != "seoul-2" and r["a"] not in n and r["b"] not in n)
    # OSM에만 있는 인접(1-3, 2-4)은 우리 그래프에서 2역 거리 → 급행 패턴으로 분류
    assert {x["kind"] for x in extra} <= {"express_pattern", "missing_edge_two_sources", "missing_edge_osm_only"}
    assert any(x["kind"] == "express_pattern" for x in extra)
    assert stats["stops_matched"] == 6 and not coords
