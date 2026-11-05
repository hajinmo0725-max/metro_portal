"""N2·N3: 노선 순서·좌표 검증 로직과 실데이터 보정 결과 회귀."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from metro_portal.lineval import (dist_matrix, edges_of, geometry_flags, interior_angle_deg, optimize_order,
                                  path_length, spike_flags)

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed" / "kr"
VCFG = yaml.safe_load(open(ROOT / "config" / "validation.yaml", encoding="utf-8"))
G, C = VCFG["line_geometry"], VCFG["coords"]


def straight(n, step=0.01):
    return [(37.5, 127.0 + i * step) for i in range(n)]  # 동서 일직선, 약 880m 간격


def test_optimal_keeps_correct_order():
    pts = straight(8)
    opt, L = optimize_order(pts, list(range(8)))
    assert path_length(list(range(8)), dist_matrix(pts)) == pytest.approx(L)
    assert edges_of(opt) == edges_of(list(range(8)))


def test_swapped_order_detected():
    pts = straight(8)
    order = [0, 1, 2, 4, 3, 5, 6, 7]  # 3·4 뒤바뀜
    p2 = [pts[i] for i in order]
    opt, Lo = optimize_order(p2, list(range(8)))
    Lc = path_length(list(range(8)), dist_matrix(p2))
    assert Lc / Lo > 1.2
    kinds = {f["kind"] for f in geometry_flags(p2, G)}
    assert "swap" in kinds and "backtrack" in kinds


def test_circular_is_closed_tour():
    import math
    pts = [(37.5 + 0.02 * math.sin(2 * math.pi * k / 10), 127.0 + 0.02 * math.cos(2 * math.pi * k / 10)) for k in range(10)]
    opt, L = optimize_order(pts, list(range(10)), closed=True)
    assert path_length(list(range(10)), dist_matrix(pts), closed=True) == pytest.approx(L)
    assert not geometry_flags(pts, G, closed=True)


def test_interior_angle():
    assert interior_angle_deg((37.5, 127.0), (37.5, 127.01), (37.5, 127.02)) == pytest.approx(180, abs=0.5)
    assert interior_angle_deg((37.5, 127.0), (37.5, 127.01), (37.5, 127.0001)) < 5


def test_spike_like_yangwon():
    # 가운데 역 좌표가 190km 떨어진 동명역 좌표로 바뀐 경우 (양원 사례)
    pts = straight(5)
    pts[2] = (36.96, 129.09)
    hits = spike_flags(pts, C)
    assert [h["i"] for h in hits] == [2]
    assert not spike_flags(straight(5), C)


def test_spike_endpoint():
    pts = straight(5)
    pts[0] = (35.0, 129.0)
    assert any(h.get("end") and h["i"] == 0 for h in spike_flags(pts, C))


def _load_mod():
    spec = importlib.util.spec_from_file_location("v08", ROOT / "pipeline" / "08_validate_lines.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wikidata_matcher_prefers_adjacency_over_distance():
    """양원 시나리오: 우리 좌표가 봉화(영동선 양원) 쪽으로 틀려도, 이웃(망우·구리)과 P197 인접한 서울 양원을 골라야 한다."""
    from metro_portal.ruleset import load_ruleset
    mod = _load_mod()
    norm = load_ruleset("strict")["normalize"]

    def it(q, label, lat, lon, adj=()):
        return {"qid": q, "label_ko": label, "lat": lat, "lon": lon, "n_coords": 1, "lines": [], "codes": [], "classes": [],
                "adjacent": [{"qid": a, "line": ""} for a in adj]}
    items = [it("Q1", "망우역", 37.5991, 127.092, ["Q2"]), it("Q2", "양원역", 37.6066, 127.108, ["Q1", "Q3"]),
             it("Q3", "구리역", 37.6034, 127.1435, ["Q2"]), it("Q9", "양원역", 36.96, 129.09)]
    wm = mod.WikidataMatcher(items, norm)

    def st(i, name, lat, lon):
        return {"id": i, "name_ko": name, "lat": lat, "lon": lon}
    stations = [st("a", "망우역", 37.5991, 127.092), st("b", "양원역", 36.96, 129.09), st("c", "구리역", 37.6034, 127.1435)]
    lines = [{"id": "L", "sequences": [{"id": "main", "station_ids": ["a", "b", "c"], "circular": False}]}]
    m = mod.match_stations(stations, lines, wm)
    assert m["b"]["qid"] == "Q2" and m["b"]["method"] == "adj" and m["b"]["adj_score"] == 2


real = pytest.mark.skipif(not (PROC / "lines.json").exists(), reason="processed data missing")


def _seq(line, seq="main"):
    lines = json.loads((PROC / "lines.json").read_text(encoding="utf-8"))["lines"]
    st = {s["id"]: s for s in json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]}
    for ln in lines:
        if ln["id"] == line:
            for sq in ln["sequences"]:
                if sq["id"] == seq:
                    return [st[x]["name_ko"] for x in sq["station_ids"]], sq["circular"]
    raise KeyError((line, seq))


@real
def test_line6_eungam_loop_fixed():
    main, circ = _seq("seoul-6")
    assert main[:2] == ["응암", "새절(신사)"] and not circ
    loop, circ = _seq("seoul-6", "eungam-loop")
    assert circ and loop == ["응암", "역촌", "불광", "독바위", "연신내", "구산"]
    edges = json.loads((PROC / "ride_edges.json").read_text(encoding="utf-8"))["edges"]
    st = {s["id"]: s["name_ko"] for s in json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]}
    pairs = {frozenset((st[e["a"]], st[e["b"]])) for e in edges if e["line"] == "seoul-6"}
    assert frozenset(("구산", "새절(신사)")) not in pairs
    assert frozenset(("구산", "응암")) in pairs and frozenset(("응암", "새절(신사)")) in pairs


@real
def test_dongnae_donghae_coord_fixed_and_split():
    st = {s["id"]: s for s in json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]}
    d = st["kr:I26K6:8005"]
    assert d.get("coord_fix") and abs(d["lat"] - 35.1976) < 1e-6
    cl = json.loads((PROC / "strict" / "clusters.json").read_text(encoding="utf-8"))["clusters"]
    cof = {x: c["id"] for c in cl for x in c["station_ids"]}
    assert cof["kr:I26K6:8005"] != cof["kr:S2601:0125"]
    assert cof["kr:L2604:0402"] == cof["kr:S2601:0125"]  # 1·4호선 동래는 여전히 환승


@real
def test_validation_report_has_no_both_flags():
    p = PROC / "lines_check.json"
    if not p.exists():
        pytest.skip("lines_check.json missing")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert not [e for r in doc["sequences"] for e in r["edges"] if e["both"]]
    assert all(x["detected_by_spike"] or x["detected_by_near_dup"] for x in doc["spike_regression"])
