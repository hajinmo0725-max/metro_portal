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
