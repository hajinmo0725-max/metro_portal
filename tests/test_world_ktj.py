"""5차 T2: 한국 + 타이베이 + 도쿄 ruleset (ktj_*). T1은 언어마다 따로(separate_langs), 일본어 이름은 한자만일 때 T2(script_check_as)."""
import json

import pytest

from metro_portal import ROOT
from metro_portal.graph import build_clusters, build_portals
from metro_portal.ruleset import load_ruleset

UNIHAN = ROOT / "data" / "raw" / "unihan" / "Unihan_Variants.txt"
need_unihan = pytest.mark.skipif(not UNIHAN.exists(), reason="Unihan 미수신 (pipeline/16_fetch_unihan.py)")
pytest.importorskip("opencc")


def jp(sid, ja, lat, lon):
    return {"id": sid, "name_ko": ja, "lat": lat, "lon": lon, "line_group": sid, "line_no": sid, "region": "", "country": "JP",
            "names": [{"text": ja, "lang": "ja", "script": "Jpan", "source": "wikidata_label", "official": False, "kind": "primary",
                       "grade": "native_label"}]}


def tw(sid, zh, lat, lon):
    return {"id": sid, "name_ko": zh, "lat": lat, "lon": lon, "line_group": sid, "line_no": sid, "region": "", "country": "TW",
            "names": [{"text": zh, "lang": "zh", "script": "Hant", "source": "wikidata_label", "official": False, "kind": "primary",
                       "grade": "native_label"}]}


def kr(sid, ko, hani, lat, lon):
    return {"id": sid, "name_ko": ko, "lat": lat, "lon": lon, "line_group": sid, "line_no": sid, "region": "", "country": "KR",
            "names": [{"text": ko, "lang": "ko", "script": "Hang", "source": "kric_std", "official": True, "kind": "primary"},
                      {"text": hani, "lang": "ko", "script": "Hani", "source": "kric_std", "official": True, "kind": "primary"}]}


def portals(stations, rs):
    cl = build_clusters(stations, rs)
    return build_portals(stations, cl, rs)[0]


@need_unihan
def test_same_kanji_across_languages_is_t2_not_t1():
    """zh '板橋'와 ja '板橋'는 같은 글자여도 언어가 달라 T1이 아니라 T2 (서울 판교 板橋와 함께 세 나라 T2 포탈 하나)."""
    st = [jp("jp:1", "板橋", 35.75, 139.72), tw("tw:1", "板橋", 25.01, 121.46), kr("kr:1", "판교", "板橋", 37.39, 127.11)]
    ps = portals(st, load_ruleset("ktj_t12"))
    assert [p["tier"] for p in ps] == ["T2"] and ps[0]["degree"] == 3
    assert portals(st, load_ruleset("ktj_t1")) == []


def test_t1_within_japanese_and_kana_variant_folding():
    """도쿄 안 같은 이름 다른 역(霞ヶ関 / 霞ケ関, 39km)은 ja T1 포탈. '@ja' 꼬리는 id에만, 표시 이름은 그대로."""
    st = [jp("jp:a", "霞ヶ関", 35.67, 139.75), jp("jp:b", "霞ケ関", 35.91, 139.41)]
    ps = portals(st, load_ruleset("ktj_t1"))
    assert len(ps) == 1 and ps[0]["tier"] == "T1" and ps[0]["name"] == "霞ケ関" and ps[0]["id"] == "P:T1:霞ケ関@ja"


@need_unihan
def test_kana_mixed_japanese_name_not_in_t2():
    """가나가 섞인 일본어 이름은 T2(한자 이체자) 대상이 아니다 (script_check_as Jpan → Hani)."""
    st = [jp("jp:a", "ひばりヶ丘", 35.75, 139.54), tw("tw:a", "ひばりヶ丘", 25.0, 121.5)]
    assert [p for p in portals(st, load_ruleset("ktj_t12")) if p["tier"] == "T2"] == []


def test_kr_tw_rulesets_unchanged_by_new_options():
    """기존 tw_* ruleset에는 separate_langs·script_check_as가 없다 (한국+타이베이 결과 불변)."""
    for n in ("tw_t1", "tw_t12", "tw_t123"):
        t = load_ruleset(n)["portals"]
        assert not t["T1"].get("separate_langs") and not (t.get("T2") or {}).get("script_check_as")


CMP = ROOT / "data" / "processed" / "world_ktj" / "compare.json"


@pytest.mark.skipif(not CMP.exists(), reason="3국 비교 결과 없음 (17 --config config/world_compare_ktj.yaml)")
def test_three_country_compare_results():
    r = json.loads(CMP.read_text(encoding="utf-8"))["results"]
    tri = [p for p in r["ktj_t12"]["portals"] if len(p["countries"]) == 3]
    assert [p["name"] for p in tri] == ["板桥"]                          # 板橋 = 세 나라 공통 (접힌 키)
    assert not any(p["cross_country"] for p in r["ktj_t1"]["portals"])   # T1만이면 국가 간 포탈 0
    assert all(not v["judge"]["explosion"] for v in r.values())          # 허브 폭발 없음
    cross = {(p["name"], tuple(p["countries"])) for p in r["ktj_t12"]["portals"] if p["cross_country"]}
    assert {("三田", ("JP", "KR")), ("田浦", ("JP", "KR")), ("中山", ("JP", "TW")), ("府中", ("JP", "TW"))} <= cross


FF = ROOT / "data" / "processed" / "fun_facts.json"


@pytest.mark.skipif(not FF.exists(), reason="fun_facts 없음")
def test_fun_facts_world_section():
    """5차: fun facts 국가 간 경로 사례 — 세 나라 공통 포탈 板橋, 나라 사이 최단 경로, 해외 경유 국내 단축."""
    w = json.loads(FF.read_text(encoding="utf-8")).get("world")
    if w is None:
        pytest.skip("world 섹션 없음 (도쿄 데이터 없이 생성)")
    assert [p["name"] for p in w["three_country_portals"]] == ["板桥"]
    assert w["diameter"]["cost"] >= 60 and len(w["diameter"]["countries_on_path"]) >= 2
    r = {(x["from"], x["to"]): x for x in w["routes"]}
    assert ("타이베이 台北車站", "도쿄권 東京") in r
    for x in w["routes"]:   # 경로가 실제로 다른 나라로 넘어간다 (국가 간 워프 포함)
        assert any(s["type"] == "warp" for s in x["steps"])
    for cc in ("KR", "TW", "JP"):
        d = w["detours"][cc]
        assert 0 < d["shortened_via_abroad"] < d["pairs"]
        e = d["example"]
        assert e["cost_domestic"] is None or e["cost"] < e["cost_domestic"]
