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
RS12O = load_ruleset("tw_t12_official")   # 4차: 공식명만 (3차 기본 재현)
RS123B = load_ruleset("tw_t123b")         # 4차: T3b(로마자 우연 일치) 켬


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
def test_grades_native_label_allowed_by_default_official_only_excludes():
    """4차 Q6-1: 기본은 official + native_label. 타이베이 zh-Hant 라벨(native_label)은 T2에 쓰고, 공식명만 ruleset은 제외."""
    a = st("k1", "판교", 37.39, 127.11, hani="板橋")
    b = st("t1", "板橋", 25.01, 121.46, country="TW", zh="板橋站", zh_src="wikidata_label", official=False)
    ps, _ = portals([a, b], RS12)
    assert [(p["tier"], p["degree"], p["confidence"]) for p in ps] == [("T2", 2, "medium")]
    assert sorted(ps[0]["grades"]) == ["native_label", "official"]
    assert not [p for p in portals([a, b], RS12O)[0] if p["tier"] == "T2"]


def test_foreign_label_never_used_in_t1_t2():
    """현지어가 아닌 라벨: 타이베이 역의 ko 라벨, 한국 역의 중국어 번역명(공식 소스라도)은 T1·T2 매칭에 쓰지 않는다."""
    tw = st("t1", "台北車站", 25.04, 121.51, country="TW", zh="台北車站", zh_src="wikidata_label", official=False)
    tw["names"].append({"text": "중화", "lang": "ko", "script": "Hang", "source": "wikidata_label", "official": False, "kind": "primary"})
    kr = st("k1", "중화", 37.60, 127.08)
    assert not portals([tw, kr], RS12)[0]
    kr2 = st("k2", "중화", 37.60, 127.08)
    kr2["names"].append({"text": "中和", "lang": "zh", "script": "Hant", "source": "kric_metro", "official": True, "kind": "primary"})
    tw2 = st("t2", "中和", 25.0, 121.5, country="TW", zh="中和", zh_src="wikidata_label", official=False)
    assert not [p for p in portals([kr2, tw2], RS12)[0] if p["tier"] == "T1"]   # 한국 역 중국어 번역명은 현지어 아님


def test_english_label_only_in_t3_with_low_confidence():
    a = st("k1", "시청", 35.18, 129.07, en="City Hall")
    b = st("t1", "市府", 25.04, 121.56, country="TW", zh="市政府站", zh_src="wikidata_label", official=False,
           en="City Hall Station", en_src="wikidata_label")
    ps, _ = portals([a, b], RS123)
    assert [(p["tier"], p["name"], p["confidence"]) for p in ps] == [("T3a", "city hall", "low")]
    assert not portals([a, b], RS12)[0]


def test_t3_exact_english_casefold_suffix_no_partial():
    a = st("k1", "성남", 37.39, 127.12, en="Seongnam")
    b = st("k2", "석남(거북시장)", 37.50, 126.67, en="Seongnam(Geobuk Market)")   # 로마자 동음 (실데이터)
    c = st("t1", "城南", 25.0, 121.5, country="TW", en="Seongnam Station")
    d = st("k3", "인천시청", 37.45, 126.70, en="Incheon City Hall")
    e = st("k4", "시청", 35.18, 129.07, en="City Hall")
    keys = [tier_keys(x, RS123B, "T3b") for x in (a, b, c)]
    assert keys[0] == keys[1] == keys[2] == {"seongnam"}
    assert tier_keys(d, RS123, "T3a") != tier_keys(e, RS123, "T3a")


def test_t3a_translation_vs_t3b_romanization():
    """4차 Q6-6: 성남 ↔ 석남(Seongnam)은 T3b(로마자 우연 일치)라 기본(tw_t123)에서는 꺼져 있고, 번역형 'city hall'은 T3a."""
    from metro_portal.graph import english_type
    a = st("k1", "성남", 37.39, 127.12, en="Seongnam")
    b = st("k2", "석남(거북시장)", 37.50, 126.67, en="Seongnam(Geobuk Market)")
    assert not portals([a, b], RS123)[0]
    assert [(p["tier"], p["name"]) for p in portals([a, b], RS123B)[0]] == [("T3b", "seongnam")]
    t3a = RS123["portals"]["T3a"]
    assert english_type("city hall", t3a) == "translation" and english_type("seoul nat'l univ. of education", t3a) == "translation"
    assert english_type("seongnam", t3a) == "romanization" and english_type("gangnam", t3a) == "romanization"
    assert tier_keys(a, RS123, "T3a") == set() and tier_keys(a, RS123, "T3b") == {"seongnam"}


def test_t2_same_hanja_different_reading_stays_t2():
    """4차 Q6-6: 大峙(서울 대치 ↔ 부산 대티)는 한자가 같고 독음이 다르다. T2 정의(이체자 정규화 후 일치)에 맞으므로 T2."""
    a = st("k1", "대치", 37.49, 127.06, hani="大峙")
    b = st("k2", "대티", 35.10, 129.01, hani="大峙")
    assert [(p["tier"], p["name"]) for p in portals([a, b], RS12)[0]] == [("T2", "大峙")]


def test_dedupe_subsumed_higher_tier():
    a = st("k1", "시청", 37.56, 126.97, en="City Hall")
    b = st("k2", "시청", 36.35, 127.38, en="City Hall")
    ps, capped = portals([a, b], RS123)
    assert [(p["tier"], p["name"]) for p in ps] == [("T1", "시청")]
    assert [(p["tier"], p.get("subsumed")) for p in capped] == [("T3a", True)]
