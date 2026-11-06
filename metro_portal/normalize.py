"""역명 정규화 (DESIGN 5.1). 규칙 값은 전부 ruleset['normalize']에서 받는다."""
from __future__ import annotations

import re
import unicodedata


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def _strip_parenthetical(s: str, pairs: list[list[str]]) -> tuple[str, list[str]]:
    """괄호 안 부역명을 제거하고, 제거한 내용(별칭 후보)을 돌려준다. 중첩·닫히지 않은 괄호도 처리."""
    removed: list[str] = []
    for open_ch, close_ch in pairs:
        pat = re.compile(re.escape(open_ch) + r"([^" + re.escape(open_ch + close_ch) + r"]*)" + re.escape(close_ch))
        while True:
            m = pat.search(s)
            if not m:
                break
            removed.append(m.group(1))
            s = s[: m.start()] + s[m.end():]
        # 닫히지 않은 여는 괄호: 그 뒤를 전부 부역명으로 간주
        idx = s.find(open_ch)
        if idx >= 0:
            removed.append(s[idx + 1:])
            s = s[:idx]
        s = s.replace(close_ch, "")
    return s, removed


def _base(text: str, cfg: dict) -> str:
    s = unicodedata.normalize(cfg["unicode_form"], text or "")
    # 선택 옵션 (Phase 1 T3 영문명용): 문자 치환표, 대소문자 접기
    for a, b in (cfg.get("char_map") or {}).items():
        s = s.replace(a, b)
    if cfg.get("casefold"):
        s = s.casefold()
    if cfg["collapse_whitespace"]:
        s = _collapse(s)
    if cfg["strip"]:
        s = s.strip()
    canon = cfg["middle_dot_canonical"]
    for v in cfg["middle_dot_variants"]:
        s = s.replace(v, canon)
    return s


def _finish(s: str, cfg: dict) -> str:
    if cfg["collapse_whitespace"]:
        s = _collapse(s)
    if cfg["strip"]:
        s = s.strip()
    for suf in cfg["remove_suffixes"]:
        if s.endswith(suf) and len(s) - len(suf) >= cfg["min_length_after_suffix"]:
            s = s[: -len(suf)]
            if cfg["strip"]:
                s = s.strip()
            break
    return s


def normalize_name(text: str, cfg: dict) -> str:
    """정규화된 역명. 매칭은 이 결과의 '완전 일치'로만 한다 (부분 일치 금지)."""
    s = _base(text, cfg)
    if cfg["remove_parenthetical"]:
        s, _ = _strip_parenthetical(s, cfg["parenthesis_pairs"])
    return _finish(s, cfg)


def parenthetical_aliases(text: str, cfg: dict) -> list[str]:
    """괄호 속 부역명을 정규화해서 돌려준다. 환승 클러스터 판정 보조용 (포탈 매칭에는 쓰지 않는다)."""
    s = _base(text, cfg)
    _, removed = _strip_parenthetical(s, cfg["parenthesis_pairs"])
    out = []
    for r in removed:
        n = _finish(r, cfg)
        if n:
            out.append(n)
    return out


_SCRIPT_PREFIX = {"Hani": ("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH"),
                  "Hant": ("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH"),
                  "Hans": ("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH"),
                  "Latn": ("LATIN ",), "Hang": ("HANGUL ",)}


def script_ok(text: str, script: str) -> bool:
    """정규화된 이름의 글자(Unicode 범주 L*)가 모두 선언한 문자 체계인가. 한자 칸에 '한자가없음' 같은 한글이 든 표기 오류를 거른다.
    알 수 없는 문자 체계면 검사하지 않는다(True)."""
    pre = _SCRIPT_PREFIX.get(script)
    if not pre:
        return True
    letters = [ch for ch in text if unicodedata.category(ch).startswith("L")]
    return bool(letters) and all(unicodedata.name(ch, "").startswith(pre) for ch in letters)
