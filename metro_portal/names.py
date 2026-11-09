"""이름 출처 등급 (config/name_grades.yaml). 4차 Q6-1.

grade_of(name, country): official / native_label / foreign_label. 데이터에 grade가 있으면 그대로 쓰고, 없으면 source·lang으로 판정한다.
is_native(name, country): 이름의 언어가 그 나라 현지어인가 (한국 역의 zh·ja 번역명은 공식 소스라도 현지어가 아니다).
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from . import ROOT

PATH = ROOT / "config" / "name_grades.yaml"
GRADE_ORDER = ["official", "native_label", "foreign_label"]


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load(open(PATH, encoding="utf-8"))


def is_native(name: dict, country: str) -> bool:
    return name.get("lang") in config()["native_langs"].get(country or "KR", [])


def grade_of(name: dict, country: str = "KR") -> str:
    if name.get("grade"):
        return name["grade"]
    # official 플래그는 수집 단계가 공식 소스(official_sources)에서 온 이름에만 켠다
    if name.get("official"):
        return "official"
    return "native_label" if is_native(name, country) else "foreign_label"


def assign_grades(stations: list[dict], country: str | None = None) -> None:
    """역 레코드의 이름마다 grade를 기록한다 (제자리 수정)."""
    for s in stations:
        cc = country or s.get("country", "KR")
        for n in s.get("names", []):
            n["grade"] = grade_of({k: v for k, v in n.items() if k != "grade"}, cc)


def confidence(grades) -> str:
    """매칭에 쓰인 등급 집합 → 포탈 신뢰도 (가장 낮은 등급 기준)."""
    worst = max((GRADE_ORDER.index(g) for g in grades), default=0)
    return config()["confidence_by_grade"][GRADE_ORDER[worst]]


# ---------- 5차 R2: 화면 표시 이름 ('역' 유지 규칙, config/display.yaml) ----------
import re as _re  # noqa: E402
from collections import defaultdict as _dd  # noqa: E402

_PAREN = _re.compile(r"^(.*?)(\s*[(\[].*)?$")


def split_paren(name: str) -> tuple[str, str]:
    m = _PAREN.match(name)
    return m.group(1), m.group(2) or ""


@lru_cache(maxsize=1)
def display_config() -> dict:
    return yaml.safe_load(open(ROOT / "config" / "display.yaml", encoding="utf-8"))["keep_station_suffix"]


def region_names(stations: list[dict], cfg: dict | None = None) -> set[str]:
    """역 주소 앞 두 토큰의 시·도·군 이름 (접미사 뗀 것)."""
    cfg = cfg or display_config()
    suf = sorted(cfg["region_suffixes"], key=len, reverse=True)
    out = set(cfg.get("extra_region_names") or [])
    for s in stations:
        for tok in (s.get("address") or "").split()[:2]:
            for x in suf:
                if tok.endswith(x) and len(tok) - len(x) >= cfg["region_min_length"]:
                    out.add(tok[: -len(x)])
                    break
    return out - set(cfg.get("exclude_region_names") or [])


def strip_display_suffix(name: str, norm: dict) -> str:
    """4차 Q5 표시 규칙: '역' 등 접미사를 매칭 정규화(ruleset normalize.remove_suffixes)와 같은 규칙으로 뗀다. 괄호 부역명은 유지."""
    base, paren = split_paren(name)
    for suf in norm["remove_suffixes"]:
        if base.endswith(suf) and len(base) - len(suf) >= norm["min_length_after_suffix"]:
            base = base[: -len(suf)]
            break
    return base + paren


def world_display_names(world: dict) -> dict:
    """build_world 결과 → 클러스터 id → 화면 표시 이름 (도식 SVG 라벨 등)."""
    st = {s["id"]: s for s in world["stations"]}
    cd, _, _ = display_names(world["clusters"], st, lambda n: strip_display_suffix(n, world["rs"]["normalize"]))
    return cd


def display_names(clusters: list[dict], stations: dict, strip_suffix, cfg: dict | None = None):
    """클러스터·역 표시 이름. strip_suffix(name) = 4차 Q5 표시 규칙(매칭 정규화와 같은 접미사 떼기, 괄호 부역명 유지).
    클러스터가 '역'을 유지하면 그 클러스터의 역 레코드도 전부 유지한다 (한 물리적 역은 한 표기).
    반환 (cluster_id → 표시 이름, station_id → 표시 이름, cluster_id → 사유 'region'|'collision')."""
    cfg = cfg or display_config()
    suffix = cfg["suffix"]
    countries = set(cfg.get("countries") or ["KR"])
    kr_st = [s for s in stations.values() if s.get("country", "KR") in countries]
    regions = region_names(kr_st, cfg) if cfg.get("enabled") else set()
    by_name = _dd(list)
    for c in clusters:
        by_name[c["name"]].append(c["id"])
    keep = {}
    for c in clusters:
        if not cfg.get("enabled") or not (set(c.get("countries") or ["KR"]) & countries) or c["name"].endswith(suffix):
            continue
        raws = [stations[x]["name_ko"] for x in c["station_ids"] if x in stations]
        if c["name"] in regions:
            keep[c["id"]] = "region"
        elif cfg.get("collision") and len(by_name[c["name"]]) > 1 and any(split_paren(r)[0].endswith(suffix) for r in raws):
            keep[c["id"]] = "collision"
    cdisp = {c["id"]: c["name"] + (suffix if c["id"] in keep else "") for c in clusters}
    sdisp = {}
    for c in clusters:
        for sid in c["station_ids"]:
            if sid not in stations:
                continue
            base, paren = split_paren(strip_suffix(stations[sid]["name_ko"]))
            if c["id"] in keep and not base.endswith(suffix):
                base += suffix
            sdisp[sid] = base + paren
    return cdisp, sdisp, keep
