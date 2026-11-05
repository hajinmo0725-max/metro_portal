"""공식 환승 정보 (표준데이터 '환승역구분'·'환승노선번호') 해석. 3차 A3.

판정은 역 레코드 두 개 (a, b) 사이의 관계 하나로 끝난다.
- same_line: 같은 노선 패밀리 (직결 경계·같은 노선번호의 그룹 분할). 공식 환승 정보가 말할 수 없다
- yes: a의 공식 환승노선 목록에 b의 노선이 있거나 그 반대 (패밀리로 넓혀 비교)
- no: 둘 다 공식 정보가 완전한데 (목록이 있거나 '일반역') 서로를 적지 않았다
- unknown: 어느 한쪽이라도 정보가 불완전 (해석 못 하는 코드, '환승역'인데 노선 목록 없음, 정보 필드 자체가 없음)
클러스터링 정책(yes/no/unknown을 어떻게 쓸지)은 ruleset이 정한다 (graph.build_clusters).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import ROOT

DEFAULT_CODES = ROOT / "config" / "kr_transfer_codes.yaml"
_SPLIT = re.compile(r"[+,/\s]+")


class OfficialTransfers:
    def __init__(self, stations: list[dict], codes_path: Path | str | None = DEFAULT_CODES):
        cfg = yaml.safe_load(open(codes_path, encoding="utf-8")) if codes_path else {}
        self.alias = {k: set(v["line_nos"]) for k, v in (cfg.get("code_aliases") or {}).items()}
        self.families = [set(f["line_nos"]) for f in (cfg.get("line_families") or [])]
        # 알려진 노선번호: 역 데이터 + 설정(패밀리·별칭 대상)에 적힌 것
        self.known = {s.get("line_no", "") for s in stations}
        for f in self.families:
            self.known |= f
        for v in self.alias.values():
            self.known |= v
        self.info = {s["id"]: self.station_info(s) for s in stations}

    def family_of(self, line_no: str) -> set[str]:
        out = {line_no}
        for f in self.families:
            if line_no in f:
                out |= f
        return out

    def station_info(self, s: dict) -> dict:
        """{'status': listed|none|unknown, 'lines': 공식 환승 노선번호(패밀리 확장), 'unknown_codes': [...]}"""
        if "transfer_line_nos_raw" not in s:
            return {"status": "unknown", "lines": set(), "unknown_codes": [], "reason": "공식 환승 필드 없음"}
        toks = [t for t in _SPLIT.split(s["transfer_line_nos_raw"] or "") if t and t != "-"]
        # 별칭 코드는 큐레이션한 노선번호 그대로 쓰고, 원래 노선번호 코드만 패밀리로 넓힌다
        # (I41K4 → I4108을 다시 넓히면 I4108이 속한 경춘선 패밀리까지 번진다)
        expanded, unk = set(), []
        for t in toks:
            if t in self.alias:
                expanded |= self.alias[t]
            elif t in self.known:
                expanded |= self.family_of(t)
            else:
                unk.append(t)
        own = self.family_of(s.get("line_no", ""))
        expanded -= own  # 자기 노선(패밀리) 자기참조는 잡음 (에버라인 전 역이 L41E1을 적는 등)
        if unk:
            return {"status": "unknown", "lines": expanded, "unknown_codes": unk, "reason": "해석 못 하는 코드"}
        if expanded:
            return {"status": "listed", "lines": expanded, "unknown_codes": [], "reason": ""}
        if s.get("transfer_flag"):
            return {"status": "unknown", "lines": set(), "unknown_codes": [], "reason": "환승역인데 노선 목록 없음"}
        return {"status": "none", "lines": set(), "unknown_codes": [], "reason": "일반역"}

    def relation(self, a: dict, b: dict) -> str:
        la, lb = a.get("line_no", ""), b.get("line_no", "")
        if la == lb or any(la in f and lb in f for f in self.families):
            return "same_line"
        ia, ib = self.info[a["id"]], self.info[b["id"]]
        if lb in ia["lines"] or la in ib["lines"]:
            return "yes"
        if ia["status"] != "unknown" and ib["status"] != "unknown":
            return "no"
        return "unknown"


def coord_copy_pairs(stations: list[dict], official: "OfficialTransfers", norm: dict, limit_m: float) -> list[dict]:
    """3차 A4: 정규화 이름이 같고 좌표 차이 limit_m 미만인데 공식 환승(yes)이 아닌 역 레코드 쌍.
    relation이 no면 좌표 복사 의심, same_line이면 같은 역의 노선 레코드(정상), unknown이면 판정 보류."""
    from collections import defaultdict

    from .geo import haversine_m
    from .normalize import normalize_name
    by = defaultdict(list)
    for s in sorted(stations, key=lambda s: s["id"]):
        by[normalize_name(s["name_ko"], norm)].append(s)
    out = []
    for nm, g in sorted(by.items()):
        for i, x in enumerate(g):
            for y in g[i + 1:]:
                d = haversine_m(x["lat"], x["lon"], y["lat"], y["lon"])
                if d >= limit_m:
                    continue
                rel = official.relation(x, y)
                if rel != "yes":
                    out.append({"name": nm, "a": x["id"], "b": y["id"], "distance_m": round(d, 1), "relation": rel})
    return out
