"""3차 B3 (4차 Q6 갱신): 한국 + 타이베이 통합 그래프 ruleset 비교 결과 (pipeline/17 산출물)."""
import json

import pytest

from metro_portal import ROOT

CMP = ROOT / "data" / "processed" / "world" / "compare.json"
pytestmark = pytest.mark.skipif(not CMP.exists(), reason="world compare missing")


def load():
    return json.loads(CMP.read_text(encoding="utf-8"))["results"]


def test_official_only_reference_has_no_cross_country_portals():
    """공식명만(tw_t12_official, 3차 기본 재현)이면 타이베이 공식명이 0건이라 국가 간 포탈이 없다."""
    r = load()
    assert not [p for p in r["tw_t12_official"]["portals"] if p["cross_country"]]
    assert r["tw_t12_official"]["countries_connected"] is False
    for n in ("tw_t1", "tw_t12", "tw_t123", "tw_t12_official", "tw_t123b"):
        assert r[n]["judge"]["explosion"] is False, n


def test_default_rulesets_find_classic_hanja_portals_with_native_labels():
    """4차 Q6-1: 기본(official + native_label)에서 한국-타이베이 국가 간 포탈은 T2 6개, 전부 신뢰도 medium (zh-Hant 라벨 사용)."""
    r = load()
    assert not [p for p in r["tw_t1"]["portals"] if p["cross_country"]]   # 한글 ↔ 한자는 T1로 안 맞는다
    cross = {p["name"]: p for p in r["tw_t12"]["portals"] if p["cross_country"]}
    texts = {t for p in cross.values() for t in p["texts"]}
    assert "板橋" in texts and "中和" in texts            # 판교 ↔ 板橋, 중화 ↔ 中和
    assert len(cross) == 6 and all(p["tier"] == "T2" and p["confidence"] == "medium" for p in cross.values())
    assert r["tw_t12"]["countries_connected"] is True


def test_no_placeholder_or_hangul_in_t2_keys():
    r = load()
    for n, v in r.items():
        for p in v["portals"]:
            if p["tier"] == "T2":
                assert "한자가없음" not in p["texts"] and not any("가" <= ch <= "힣" for ch in p["name"]), (n, p["name"])


def test_monotone_portal_sets_by_tier():
    r = load()
    sig = lambda n: {(p["tier"], p["name"]) for p in r[n]["portals"]}  # noqa: E731
    assert sig("tw_t1") <= sig("tw_t12") <= sig("tw_t123") <= sig("tw_t123b")
    assert sig("tw_t12_official") <= sig("tw_t12")
