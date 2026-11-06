"""개통 예정 노선 (config/kr_planned.yaml). 4차 Q0-5.

enabled: true인 노선만 02(역 레코드)·03(정차 순서) 단계가 넣는다. enabled와 무관하게 전부 넣은 결과는
pipeline/18_planned_preview.py가 "켰을 때 새로 생기는 포탈" 미리보기로만 쓴다.
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from . import ROOT

DEFAULT_PATH = ROOT / "config" / "kr_planned.yaml"


def load_planned(path: Path | str | None = DEFAULT_PATH, include_disabled: bool = False) -> list[dict]:
    if path is None or not Path(path).exists():
        return []
    cfg = yaml.safe_load(open(path, encoding="utf-8")) or {}
    return [ln for ln in cfg.get("lines", []) if include_disabled or ln.get("enabled")]


def station_records(planned: list[dict]) -> list[dict]:
    """계획 노선의 역 레코드 (02 단계 Station 형식). 공식 환승 정보 필드(transfer_line_nos_raw)는 일부러 넣지 않는다 →
    환승 판정에서 '정보 없음'(unknown)이 되어 거리 D 규칙으로 넘어간다."""
    out = []
    for ln in planned:
        for st in ln["stations"]:
            out.append({
                "id": f"kr:{ln['line_no']}:{st['code']}", "code": st["code"], "name_ko": st["name"],
                "lat": float(st["lat"]), "lon": float(st["lon"]),
                "line_no": ln["line_no"], "line_name": ln["line_name"], "line_group": f"{ln['line_no']}:{ln['line_name']}",
                "operator": ln.get("operator", ""), "region": "", "address": "", "transfer_flag": False,
                "names": [{"text": st["name"], "lang": "ko", "script": "Hang", "source": "planned_config",
                           "official": True, "kind": "primary", "grade": "official"}],
                "source": "planned_config", "planned": ln["id"], "wikidata": st.get("wikidata", ""),
            })
    return out


def apply_line_defs(planned: list[dict], defs: dict, src_rows: list[dict]) -> None:
    """03 단계 노선 정의에 계획 노선을 더한다 (제자리 수정).
    new_line: 새 노선 정의 + 원본 행. extension: 기존 노선 정의(id 일치)에 지선 시퀀스를 붙인다 (양산–양산중앙처럼 끝에 잇는 구간)."""
    by_id = {d.get("id"): k for k, d in defs.items()}
    for ln in planned:
        if ln["kind"] == "new_line":
            src_rows.append({"노선번호": ln["line_no"], "노선명": ln["line_name"], "정거장구성": "", "운영기관명": ln.get("operator", "")})
            defs[(ln["line_no"], ln["line_name"])] = {
                "source": {"line_no": ln["line_no"], "name": ln["line_name"]}, "id": ln["id"], "name": ln["name"],
                "city": ln["city"], "color": ln["color"], "pools": [f"{ln['line_no']}:{ln['line_name']}"],
                "sequences": [{"id": q["id"], "stops": q["stops"]} for q in ln["sequences"]], "planned": ln["id"]}
        elif ln["kind"] == "extension":
            key = by_id.get(ln["extends"])
            if key is None:
                raise ValueError(f"계획 연장 대상 노선 없음: {ln['extends']}")
            d = copy.deepcopy(defs[key])
            slot = "sequences" if "sequences" in d else "branches"
            d.setdefault(slot, [])
            d[slot] = list(d[slot]) + [{"id": q["id"], "stops": q["stops"]} for q in ln["sequences"]]
            d.setdefault("planned_extensions", []).append(ln["id"])
            defs[key] = d
        else:
            raise ValueError(f"알 수 없는 계획 노선 종류: {ln['kind']}")
