"""3차 B3: 한국 + 타이베이 통합 그래프 ruleset 비교 결과 (pipeline/17 산출물)."""
import json

import pytest

from metro_portal import ROOT

CMP = ROOT / "data" / "processed" / "world" / "compare.json"
pytestmark = pytest.mark.skipif(not CMP.exists(), reason="world compare missing")


def load():
    return json.loads(CMP.read_text(encoding="utf-8"))["results"]


def test_official_rulesets_have_no_cross_country_portals():
    r = load()
    for n in ("tw_t1", "tw_t12", "tw_t123"):
        assert not [p for p in r[n]["portals"] if p["cross_country"]], n
        assert r[n]["countries_connected"] is False
        assert r[n]["judge"]["explosion"] is False


def test_label_reference_finds_classic_hanja_portals():
    r = load()
    cross = {p["name"]: p for p in r["tw_t12_label"]["portals"] if p["cross_country"]}
    texts = {t for p in cross.values() for t in p["texts"]}
    assert "板橋" in texts and "中和" in texts            # 판교 ↔ 板橋, 중화 ↔ 中和
    assert all(p["tier"] == "T2" for p in cross.values())
    assert r["tw_t12_label"]["countries_connected"] is True


def test_no_placeholder_or_hangul_in_t2_keys():
    r = load()
    for n, v in r.items():
        for p in v["portals"]:
            if p["tier"] == "T2":
                assert "한자가없음" not in p["texts"] and not any("가" <= ch <= "힣" for ch in p["name"]), (n, p["name"])


def test_monotone_portal_sets_by_tier():
    r = load()
    sig = lambda n: {(p["tier"], p["name"]) for p in r[n]["portals"]}  # noqa: E731
    assert sig("tw_t1") <= sig("tw_t12") <= sig("tw_t123")
    assert sig("tw_t1_label") <= sig("tw_t12_label") <= sig("tw_t123_label")
