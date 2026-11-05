import pytest

from metro_portal.normalize import normalize_name, parenthetical_aliases
from metro_portal.ruleset import RulesetError, load_ruleset


@pytest.fixture(scope="module")
def norm():
    return load_ruleset("strict")["normalize"]


@pytest.mark.parametrize("raw,expected", [
    # 부역명 괄호
    ("교대(법원·검찰청)", "교대"),
    ("하남시청(덕풍∙신장)", "하남시청"),
    ("용산(서부법원․검찰청입구)", "용산"),
    ("청량리(서울시립대입구)", "청량리"),
    ("아라(북부법원, 검찰청)", "아라"),
    # 괄호 뒤 '역' 접미사
    ("신창(순천향대)역", "신창"),
    ("홍대입구(경의선)역", "홍대입구"),
    # 접미사 '역'
    ("서울역", "서울"),
    ("양평역", "양평"),
    ("광주송정역", "광주송정"),
    # 공백·개행
    ("  강남  ", "강남"),
    ("북구청\n(대구iM뱅크파크)", "북구청"),
])
def test_normalize(norm, raw, expected):
    assert normalize_name(raw, norm) == expected


def test_suffix_not_removed_to_empty(norm):
    assert normalize_name("역", norm) == "역"


def test_suffix_only_at_end(norm):
    assert normalize_name("역삼", norm) == "역삼"
    assert normalize_name("역곡역", norm) == "역곡"


def test_middle_dot_variants_unify(norm):
    variants = ["4·19민주묘지", "4.19민주묘지", "4ㆍ19민주묘지", "4∙19민주묘지", "4・19민주묘지"]
    assert len({normalize_name(v, norm) for v in variants}) == 1


def test_fullwidth_parenthesis(norm):
    assert normalize_name("교대（법원·검찰청）", norm) == "교대"


def test_unclosed_parenthesis(norm):
    assert normalize_name("교대(법원", norm) == "교대"


def test_partial_match_is_not_equal(norm):
    # 부분 일치 금지: 정규화 결과가 포함 관계여도 다른 이름이다
    assert normalize_name("시청", norm) != normalize_name("인천시청", norm)
    assert normalize_name("시청(연제)", norm) == "시청"


def test_aliases(norm):
    assert parenthetical_aliases("총신대입구(이수)", norm) == ["이수"]
    assert parenthetical_aliases("강남", norm) == []


def test_rules_come_from_ruleset(norm):
    cfg = dict(norm, remove_suffixes=[], remove_parenthetical=False)
    assert normalize_name("서울역", cfg) == "서울역"
    assert normalize_name("교대(법원·검찰청)", cfg) == "교대(법원·검찰청)"


def test_bad_ruleset(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("name: bad\nnormalize: {}\n", encoding="utf-8")
    with pytest.raises(RulesetError):
        load_ruleset(p)
