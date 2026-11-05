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
