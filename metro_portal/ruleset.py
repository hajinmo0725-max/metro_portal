"""ruleset 로더. 매칭 룰은 전부 config/rulesets/*.yaml에서 읽는다."""
from __future__ import annotations

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


def load_ruleset(name_or_path: str | Path = "strict") -> dict:
    path = resolve_path(name_or_path)
    with open(path, encoding="utf-8") as f:
        rs = yaml.safe_load(f)
    validate(rs)
    rs["_path"] = str(path)
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
