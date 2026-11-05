"""ruleset 로더. 매칭 룰은 전부 config/rulesets/*.yaml에서 읽는다."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from . import ROOT

REQUIRED = {
    "normalize": [
        "unicode_form", "strip", "collapse_whitespace", "middle_dot_variants",
        "middle_dot_canonical", "remove_parenthetical", "parenthesis_pairs",
        "remove_suffixes", "min_length_after_suffix",
    ],
    "cluster": ["transfer_distance_m", "use_parenthetical_alias"],
    "portals": ["T1", "hub_degree_cap"],
    "costs": ["ride", "transfer"],
}


class RulesetError(ValueError):
    pass


def resolve_path(name_or_path: str | Path) -> Path:
    p = Path(name_or_path)
    if p.suffix in (".yaml", ".yml") and p.exists():
        return p
    cand = ROOT / "config" / "rulesets" / f"{name_or_path}.yaml"
    if cand.exists():
        return cand
    raise RulesetError(f"ruleset not found: {name_or_path}")


def deep_merge(base: dict, over: dict) -> dict:
    """over의 값으로 base를 덮어쓴 새 dict. dict끼리는 재귀 병합, 그 외(리스트 포함)는 통째로 교체."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_raw(name_or_path, seen: tuple = ()) -> dict:
    path = resolve_path(name_or_path)
    if str(path) in seen:
        raise RulesetError(f"extends cycle: {' -> '.join(seen + (str(path),))}")
    with open(path, encoding="utf-8") as f:
        rs = yaml.safe_load(f) or {}
    parent = rs.pop("extends", None)
    if parent:
        rs = deep_merge(_load_raw(parent, seen + (str(path),)), rs)
    rs["_path"] = str(path)
    return rs


def load_ruleset(name_or_path: str | Path = "strict", overrides: dict | None = None, name: str | None = None) -> dict:
    """ruleset 로드. `extends: <부모>`가 있으면 부모 위에 덮어쓴다.
    overrides는 비교 실험용(같은 deep merge 규칙). name을 주면 결과 ruleset 이름을 바꾼다."""
    rs = _load_raw(name_or_path)
    if overrides:
        rs = deep_merge(rs, overrides)
    if name:
        rs["name"] = name
    validate(rs)
    return rs


def validate(rs: dict) -> None:
    for section, keys in REQUIRED.items():
        if section not in rs:
            raise RulesetError(f"missing section: {section}")
        for k in keys:
            if k not in rs[section]:
                raise RulesetError(f"missing key: {section}.{k}")
    for tier, spec in rs["portals"].items():
        if tier == "hub_degree_cap":
            continue
        if "enabled" not in spec or "cost" not in spec:
            raise RulesetError(f"portal tier {tier} needs enabled and cost")
