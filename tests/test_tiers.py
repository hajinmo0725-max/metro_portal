"""3차 B2: T2(한자 이체자 정규화)·T3(영어명 정확 일치) 포탈. 규칙은 ruleset(tw_t12, tw_t123)에서 읽는다."""
import pytest

from metro_portal import ROOT
from metro_portal.graph import build_clusters, build_portals, station_match_names
from metro_portal.normalize import script_ok
from metro_portal.ruleset import load_ruleset

UNIHAN = ROOT / "data" / "raw" / "unihan" / "Unihan_Variants.txt"
need_unihan = pytest.mark.skipif(not UNIHAN.exists(), reason="Unihan 미수신 (pipeline/16_fetch_unihan.py)")
pytest.importorskip("opencc")

RS12, RS123 = load_ruleset("tw_t12"), load_ruleset("tw_t123")
RS123L = load_ruleset("tw_t123_label")


def st(sid, ko, lat, lon, country="KR", hani=None, en=None, zh=None, zh_src="wikidata_p1448", en_src=None, official=True):
    names = [{"text": ko, "lang": "ko" if country == "KR" else "zh", "script": "Hang" if country == "KR" else "Hant",
              "source": "kric_std" if country == "KR" else zh_src, "official": official if country != "KR" else True, "kind": "primary"}]
    if hani:
        names.append({"text": hani, "lang": "ko", "script": "Hani", "source": "kric_std", "official": True, "kind": "primary"})
    if zh:
        names.append({"text": zh, "lang": "zh", "script": "Hant", "source": zh_src, "official": official, "kind": "primary"})
    if en:
        names.append({"text": en, "lang": "en", "script": "Latn", "source": en_src or ("kric_std" if country == "KR" else zh_src),
                      "official": official if country != "KR" else True, "kind": "primary"})
    return {"id": sid, "name_ko": ko, "lat": lat, "lon": lon, "line_group": sid, "line_no": sid, "region": "", "country": country,
            "names": names}


def portals(stations, rs):
    cl = build_clusters(stations, rs)
    ps, capped = build_portals(stations, cl, rs)
    return ps, capped


def tier_keys(s, rs, tier):
    from metro_portal.variants import folder_for
    t = rs["portals"][tier]
    return station_match_names(s, t, rs["normalize"], folder_for(t["variant_fold"]) if t.get("variant_fold") else None)


@need_unihan
def test_t2_variant_folding_matches_korean_hanja_and_traditional():
    a = st("k1", "교대", 37.49, 127.01, hani="敎大")
    b = st("t1", "教大", 25.0, 121.5, country="TW", zh="教大站")
    assert tier_keys(a, RS12, "T2") == tier_keys(b, RS12, "T2")
    c = st("k2", "시청", 37.56, 126.97, hani="市廳")
    d = st("t2", "市庁", 25.0, 121.6, country="TW", zh="市庁")         # 일본 신자체
    assert tier_keys(c, RS12, "T2") == tier_keys(d, RS12, "T2")
    ps, _ = portals([a, b], RS12)
    assert [(p["tier"], p["degree"]) for p in ps] == [("T2", 2)]


@need_unihan
def test_t2_partial_match_and_parenthetical():
    a = st("k1", "시청", 37.56, 126.97, hani="市廳")
    b = st("k2", "인천시청", 37.45, 126.70, hani="仁川市廳")
    assert not [p for p in portals([a, b], RS12)[0] if p["tier"] == "T2"]          # 부분 일치 금지
    m1 = st("k3", "명덕", 35.85, 128.59, hani="明德(2·28民主運動紀念會館)")
    m2 = st("t3", "明德", 25.11, 121.52, country="TW", zh="明德站")
    assert tier_keys(m1, RS12, "T2") == tier_keys(m2, RS12, "T2")                   # 괄호 부역명·'站' 접미사 제거


@need_unihan
def test_t2_ignores_placeholders_and_wrong_script():
    a = st("k1", "안지랑", 35.84, 128.56, hani="한자가없음")    # 실제 표준데이터 표기 오류
    b = st("k2", "대실", 35.85, 128.47, hani="한자가없음")
    c = st("k3", "서울역", 37.55, 126.97, hani="-")
    assert not tier_keys(a, RS12, "T2") and not tier_keys(c, RS12, "T2")
    assert not portals([a, b], RS12)[0]
    assert script_ok("板橋", "Hani") and not script_ok("한자가없음", "Hani") and not script_ok("板橋테크노밸리", "Hani")


@need_unihan
def test_official_only_excludes_wikidata_labels_but_label_variant_uses_them():
    a = st("k1", "판교", 37.39, 127.11, hani="板橋")
    b = st("t1", "板橋", 25.01, 121.46, country="TW", zh="板橋站", zh_src="wikidata_label", official=False)
    assert not [p for p in portals([a, b], RS123)[0] if p["tier"] == "T2"]
    ps, _ = portals([a, b], RS123L)
    assert [(p["tier"], p["degree"]) for p in ps] == [("T2", 2)]


def test_t3_exact_english_casefold_suffix_no_partial():
    a = st("k1", "성남", 37.39, 127.12, en="Seongnam")
    b = st("k2", "석남(거북시장)", 37.50, 126.67, en="Seongnam(Geobuk Market)")   # 로마자 동음 (실데이터)
    c = st("t1", "城南", 25.0, 121.5, country="TW", en="Seongnam Station")
    d = st("k3", "인천시청", 37.45, 126.70, en="Incheon City Hall")
    e = st("k4", "시청", 35.18, 129.07, en="City Hall")
    keys = [tier_keys(x, RS123, "T3") for x in (a, b, c)]
    assert keys[0] == keys[1] == keys[2] == {"seongnam"}
    assert tier_keys(d, RS123, "T3") != tier_keys(e, RS123, "T3")


def test_dedupe_subsumed_higher_tier():
    a = st("k1", "시청", 37.56, 126.97, en="City Hall")
    b = st("k2", "시청", 36.35, 127.38, en="City Hall")
    ps, capped = portals([a, b], RS123)
    assert [(p["tier"], p["name"]) for p in ps] == [("T1", "시청")]
    assert [(p["tier"], p.get("subsumed")) for p in capped] == [("T3", True)]
