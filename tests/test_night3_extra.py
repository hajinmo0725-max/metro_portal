"""3차 테스트 보강: 퍼즐 정·역방향 중복 금지, 이체자 클래스 상한, 정규화 옵션, 다국가 로더."""
import json

import pytest

from metro_portal import ROOT
from metro_portal.normalize import normalize_name, script_ok
from metro_portal.ruleset import load_ruleset

BASE = load_ruleset("strict")["normalize"]


def test_puzzles_no_reverse_duplicates_and_daily_permutation():
    p = ROOT / "data" / "processed" / "puzzles.json"
    if not p.exists():
        pytest.skip("puzzles missing")
    pz = json.loads(p.read_text(encoding="utf-8"))
    pairs = [frozenset((x["from"], x["to"])) for x in pz["puzzles"]]
    assert len(pairs) == len(set(pairs))                          # 같은 두 역의 정·역방향 퍼즐은 하나만
    assert sorted(pz["daily_order"]) == sorted(x["id"] for x in pz["puzzles"])


def test_normalize_casefold_and_char_map_are_opt_in():
    cfg = dict(BASE, casefold=True, char_map={"’": "'", "–": "-"}, remove_suffixes=[" station"])
    assert normalize_name("Seoul Station", cfg) == "seoul"
    assert normalize_name("Children’s Grand Park", cfg) == "children's grand park"
    assert normalize_name("Tamsui–Xinyi", cfg) == "tamsui-xinyi"
    assert normalize_name("Seoul Station", BASE) == "Seoul Station"   # 기본 규칙(strict)에는 영향 없음


def test_script_ok_cases():
    assert script_ok("板橋", "Hani") and script_ok("板橋", "Hant")
    assert not script_ok("한자가없음", "Hani") and not script_ok("-", "Hani") and not script_ok("", "Latn")
    assert script_ok("seongnam", "Latn") and not script_ok("성남", "Latn")
    assert script_ok("anything", "Zyyy")                              # 모르는 문자 체계는 검사 안 함


def test_variant_class_cap_skips_large_classes(tmp_path):
    pytest.importorskip("opencc")
    from metro_portal.variants import VariantFolder
    f = tmp_path / "v.txt"
    # A-B-C-D 사슬(크기 4)과 E-F(크기 2)
    f.write_text("U+4E00\tkSemanticVariant\tU+4E01\nU+4E01\tkSemanticVariant\tU+4E02\nU+4E02\tkZVariant\tU+4E03\n"
                 "U+4E10\tkZVariant\tU+4E11<kFenn\n", encoding="utf-8")
    fv = VariantFolder({"unihan_fields": ["kSemanticVariant", "kZVariant"], "unihan_file": str(f), "max_class_size": 3})
    assert fv.fold("七") == "七"                              # 크기 4 > 3 → 접지 않음
    assert fv.fold("丑") == "丐"                              # 크기 2 → 최소 코드포인트로
    assert fv.skipped_classes == ["一丁丂七"]
    fv2 = VariantFolder({"unihan_fields": ["kZVariant"], "unihan_file": str(f), "max_class_size": 8})
    assert fv2.fold("丁") == "丁" and fv2.fold("七") == "丂"   # 필드 선택이 반영된다


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "tw" / "stations.json").exists(), reason="tw data missing")
def test_multi_country_loader_and_clusters_never_mix_countries():
    from metro_portal.world import build_world, load_multi
    st, ed, ln = load_multi(("KR", "TW"))
    assert {s["country"] for s in st} == {"KR", "TW"}
    assert len({s["id"] for s in st}) == len(st)
    ids = {s["id"] for s in st}
    assert all(e["a"] in ids and e["b"] in ids for e in ed)
    w = build_world(st, ed, ln, load_ruleset("tw_t1"))
    assert all(len(c["countries"]) == 1 for c in w["clusters"])
    assert {s["city"] for s in w["stations"] if s["country"] == "TW"} == {"타이베이"}


def test_intuition_search_backtracks_and_is_deterministic():
    """직관 탐색: 목적지 쪽(남쪽) 막다른 역 B보다, 반대 방향이지만 워프 도착지가 목적지 옆인 C를 먼저 펼친다."""
    from metro_portal.game import ClusterGraph, intuition_search
    rs = load_ruleset("strict")
    # A(출발) - B(목적지 방향 막다른 길), A - C(반대 방향, 포탈 '가'), 포탈 '가' → D(목적지 옆) - T
    pts = {"A": (37.0, 127.0), "B": (36.9, 127.0), "C": (37.1, 127.0), "D": (35.1, 129.0), "T": (35.0, 129.0), "C2": (35.05, 129.05)}
    cl = [{"id": f"{k}#1", "name": k if k != "C2" else "C", "names": [k], "station_ids": [k], "lat": v[0], "lon": v[1],
           "regions": [""], "lines": ["L"], "cities": ["X"]} for k, v in pts.items()]
    E = [{"line": "L", "a": "A", "b": "B", "distance_m": 1.0}, {"line": "L", "a": "A", "b": "C", "distance_m": 1.0},
         {"line": "L", "a": "C2", "b": "D", "distance_m": 1.0}, {"line": "L", "a": "D", "b": "T", "distance_m": 1.0}]
    portals = [{"id": "P:T1:C", "tier": "T1", "name": "C", "cost": 1, "cluster_ids": ["C#1", "C2#1"], "station_ids": ["C", "C2"], "degree": 2}]
    g = ClusterGraph({"rs": rs, "clusters": cl, "portals": portals, "edges": E})
    a, t = g.ix["A#1"], g.ix["T#1"]
    r1, r2 = intuition_search(g, a, t), intuition_search(g, a, t)
    assert r1 == r2
    assert r1 == (4, 5)                   # A → C ⇢ C2 → D → T, 펼친 역 A·C·C2·D·T (B는 안 펼침)
