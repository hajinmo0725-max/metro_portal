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
