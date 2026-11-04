#!/usr/bin/env python3
"""M2. 노선별 정차 순서와 승차 엣지.

입력: data/raw/kric/lines_std.xlsx (표준데이터 노선정보 '정거장구성')
      data/processed/kr/stations.json
      config/kr_lines.yaml (순서 보정·지선 분리·직결 분기점 연결)
출력: data/processed/kr/lines.json, data/processed/kr/ride_edges.json,
      data/processed/kr/lines_validation.json, docs/reports/m2_lines_validation.md

OSM route relation을 쓰려 했으나 세션 네트워크에서 Overpass 접근이 막혀(TLS 리셋)
레일포털 표준데이터의 정거장구성 순서를 기본으로 쓰고, 깨진 노선만 설정 파일로 보정한다.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.kric import clean_text, code_key, read_sheet  # noqa: E402
from metro_portal.normalize import normalize_name  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402

PROC = ROOT / "data" / "processed" / "kr"
TOKEN = re.compile(r"^\s*([A-Za-z]*\d+(?:-\d+)?)\s*-\s*(.+?)\s*$")


def parse_stops(raw: str) -> list[tuple[str, str]]:
    raw = clean_text(raw).replace('"', "")
    out = []
    for tok in re.split(r"[,+]", raw):
        tok = tok.strip()
        if not tok:
            continue
        m = TOKEN.match(tok)
        out.append((m.group(1), m.group(2)) if m else ("", tok))
    return out


class Resolver:
    """정차역 표기 → station id. 'name' 은 노선 풀에서, 'name@line_group' 은 지정 그룹에서 찾는다."""

    def __init__(self, stations: list[dict], norm: dict):
        self.norm = norm
        self.by_group = defaultdict(list)
        for s in stations:
            self.by_group[s["line_group"]].append(s)
        self.groups_by_no = defaultdict(list)
        for g in sorted(self.by_group):
            self.groups_by_no[g.split(":", 1)[0]].append(g)

    def resolve(self, ref: str, pools: list[str], code: str = "") -> tuple[str | None, str]:
        if "@" in ref:
            nm, grp = ref.rsplit("@", 1)
            pools = [grp]
        else:
            nm = ref
        key = normalize_name(nm, self.norm)
        ck = code_key(code) if code else ""
        for grp in pools:
            cands = [s for s in self.by_group.get(grp, []) if normalize_name(s["name_ko"], self.norm) == key]
            if ck:
                exact = [s for s in cands if code_key(s["code"]) == ck]
                if exact:
                    return exact[0]["id"], "code+name"
            if len(cands) == 1:
                return cands[0]["id"], "name"
            if len(cands) > 1:
                return sorted(cands, key=lambda s: s["id"])[0]["id"], "name(ambiguous)"
        if ck:  # 이름이 달라도 역번호가 유일하게 맞으면 채택 (표기 차이: 디엠시 ↔ 디지털미디어시티)
            for grp in pools:
                cands = [s for s in self.by_group.get(grp, []) if code_key(s["code"]) == ck]
                if len(cands) == 1:
                    return cands[0]["id"], "code-only"
        return None, "unresolved"


def apply_patch(stops: list[str], patch: dict) -> list[str]:
    def k(x):
        return x.split("@")[0]
    out = [s for s in stops if k(s) not in set(patch.get("remove", []))]
    for anchor, items in (patch.get("insert_after") or {}).items():
        idx = [k(s) for s in out].index(anchor)
        out[idx + 1:idx + 1] = items
    out = list(patch.get("prepend", [])) + out + list(patch.get("append", []))
    if patch.get("reverse"):
        out.reverse()
    return out


def main() -> int:
    norm = load_ruleset("strict")["normalize"]
    vcfg = yaml.safe_load(open(ROOT / "config" / "validation.yaml", encoding="utf-8"))["lines"]
    lcfg = yaml.safe_load(open(ROOT / "config" / "kr_lines.yaml", encoding="utf-8"))
    stations = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]
    sidx = {s["id"]: s for s in stations}
    res = Resolver(stations, norm)

    defs = {(str(d["source"]["line_no"]), d["source"]["name"]): d for d in lcfg.get("lines", []) if "source" in d}
    used_defs = set()
    src_rows = read_sheet(ROOT / "data" / "raw" / "kric" / "lines_std.xlsx")

    lines, failures, edges = [], [], {}
    for row in sorted(src_rows, key=lambda r: (clean_text(r["노선번호"]), clean_text(r["노선명"]))):
        no, nm = clean_text(row["노선번호"]), clean_text(row["노선명"])
        d = defs.get((no, nm), {})
        if d:
            used_defs.add((no, nm))
        if d.get("skip"):
            continue
        pools = d.get("pools") or res.groups_by_no.get(no, [])
        parsed = parse_stops(row["정거장구성"])
        line_id = d.get("id") or f"kr-{no}-{nm}".replace(" ", "")
        # 기본 시퀀스: 원본 순서. 이름+역번호로 해석
        if "sequences" in d:
            seq_specs = [(sq["id"], [(x, "") for x in sq["stops"]], bool(sq.get("circular"))) for sq in d["sequences"]]
        else:
            main = [(c, n) for c, n in parsed]
            names = apply_patch([n for _, n in main], d.get("patch", {}))
            codes = {n: c for c, n in main}
            seq_specs = [("main", [(n, codes.get(n, "")) for n in names], bool(d.get("circular")))]
            for br in d.get("branches", []):
                seq_specs.append((br["id"], [(x, "") for x in br["stops"]], bool(br.get("circular"))))
        seqs = []
        for seq_id, stop_refs, circular in seq_specs:
            ids = []
            for ref, code in stop_refs:
                sid, how = res.resolve(ref, pools, code)
                if sid is None:
                    failures.append({"line": line_id, "sequence": seq_id, "stop": ref, "code": code})
                    continue
                if ids and ids[-1] == sid:
                    continue
                ids.append(sid)
            seqs.append({"id": seq_id, "station_ids": ids, "circular": circular})
            pairs = list(zip(ids, ids[1:])) + ([(ids[-1], ids[0])] if circular and len(ids) > 2 else [])
            for a, b in pairs:
                key = (line_id,) + tuple(sorted((a, b)))
                if key not in edges:
                    sa, sb = sidx[a], sidx[b]
                    edges[key] = {"line": line_id, "sequence": seq_id, "a": key[1], "b": key[2],
                                  "distance_m": round(haversine_m(sa["lat"], sa["lon"], sb["lat"], sb["lon"]), 1)}
        lines.append({
            "id": line_id, "name": d.get("name", nm), "source_no": no, "source_name": nm,
            "operator": clean_text(row["운영기관명"]), "city": d.get("city", ""), "color": d.get("color", ""),
            "pools": pools, "sequences": seqs, "patched": bool(d),
        })

    unused = [k for k in defs if k not in used_defs]
    edge_list = sorted(edges.values(), key=lambda e: (e["line"], e["a"], e["b"]))

    # --- 검증 ---
    sequenced = {sid for ln in lines for sq in ln["sequences"] for sid in sq["station_ids"]}
    not_sequenced = sorted(
        ({"id": s["id"], "name": s["name_ko"], "line_group": s["line_group"]} for s in stations if s["id"] not in sequenced),
        key=lambda x: x["id"])
    by_line = defaultdict(list)
    for e in edge_list:
        by_line[e["line"]].append(e["distance_m"])
    outliers = []
    for e in edge_list:
        med = statistics.median(by_line[e["line"]])
        reason = []
        if e["distance_m"] > vcfg["adjacent_max_m"]:
            reason.append(f">{vcfg['adjacent_max_m']}m")
        if e["distance_m"] > vcfg["adjacent_median_factor"] * med:
            reason.append(f">{vcfg['adjacent_median_factor']}×중앙값({med:.0f}m)")
        if e["distance_m"] < vcfg["adjacent_min_m"]:
            reason.append(f"<{vcfg['adjacent_min_m']}m")
        if reason:
            an, bn = sidx[e["a"]]["name_ko"], sidx[e["b"]]["name_ko"]
            known = any(k[0] == e["line"] and {k[1], k[2]} == {an, bn} for k in vcfg.get("known_long_segments", []))
            outliers.append({**e, "a_name": an, "b_name": bn, "reason": ", ".join(reason),
                             "verdict": "실제 장거리 구간(판단)" if known else "확인 필요"})
    coverage = []
    for ln in lines:
        pool_ids = {s["id"] for g in ln["pools"] for s in res.by_group.get(g, [])}
        seq_ids = {sid for sq in ln["sequences"] for sid in sq["station_ids"]}
        coverage.append({"line": ln["id"], "name": ln["name"], "pool": len(pool_ids), "sequenced": len(seq_ids),
                         "from_pool": len(seq_ids & pool_ids), "sequences": len(ln["sequences"]),
                         "edges": len(by_line[ln["id"]])})
    val = {"stop_failures": failures, "unused_line_defs": [list(k) for k in unused],
           "stations_not_sequenced": not_sequenced, "adjacent_outliers": outliers, "coverage": coverage,
           "totals": {"lines": len(lines), "sequences": sum(len(l["sequences"]) for l in lines),
                      "ride_edges": len(edge_list), "stations": len(stations), "stations_sequenced": len(sequenced),
                      "stop_failures": len(failures), "outliers": len(outliers),
                      "outliers_unexplained": sum(o["verdict"] == "확인 필요" for o in outliers)}}
    meta = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["meta"]
    val["coord_fixes"] = meta.get("coord_fixes", [])
    val["patched_lines"] = [
        {"id": d.get("id", ""), "source": f"{d['source']['line_no']} {d['source']['name']}",
         "ops": sorted(k for k in ("pools", "patch", "branches", "sequences", "circular", "skip") if k in d)}
        for d in lcfg.get("lines", []) if any(k in d for k in ("pools", "patch", "branches", "sequences", "circular", "skip"))]

    (PROC / "lines.json").write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (PROC / "ride_edges.json").write_text(json.dumps({"edges": edge_list}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (PROC / "lines_validation.json").write_text(json.dumps(val, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(val)
    print(json.dumps(val["totals"], ensure_ascii=False))
    return 0


def write_report(val: dict) -> None:
    L = ["# M2 노선 검증 리포트", "", "생성: `python3 pipeline/03_build_kr_lines.py`", "",
         "## 요약", "", "| 항목 | 값 |", "| :- | -: |"]
    L += [f"| {k} | {v} |" for k, v in val["totals"].items()]
    L += ["", "노선 순서 소스: 레일포털 표준데이터 노선정보 '정거장구성' + config/kr_lines.yaml 보정.",
          "OSM route relation은 세션 네트워크에서 Overpass 접근 불가(TLS 리셋)라 쓰지 못했다.",
          "", "## 1. 정차역 매칭 실패", ""]
    if val["stop_failures"]:
        L += ["| 노선 | 시퀀스 | 표기 | 역번호 |", "| :- | :- | :- | :- |"]
        L += [f"| {f['line']} | {f['sequence']} | {f['stop']} | {f['code']} |" for f in val["stop_failures"]]
    else:
        L += ["없음."]
    L += ["", "## 2. 어떤 시퀀스에도 안 들어간 역", ""]
    if val["stations_not_sequenced"]:
        L += ["| id | 역명 | 노선그룹 |", "| :- | :- | :- |"]
        L += [f"| {s['id']} | {s['name']} | {s['line_group']} |" for s in val["stations_not_sequenced"]]
    else:
        L += ["없음."]
    L += ["", "## 3. 인접역 간 거리 이상치", "",
          "기준: config/validation.yaml. 이상치가 곧 오류는 아니다 (교외 구간은 원래 길다). 목록을 보고 순서 오류만 보정한다.", ""]
    if val["adjacent_outliers"]:
        L += ["| 노선 | A | B | 거리(m) | 사유 | 판정 |", "| :- | :- | :- | -: | :- | :- |"]
        L += [f"| {o['line']} | {o['a_name']} | {o['b_name']} | {o['distance_m']:.0f} | {o['reason']} | {o['verdict']} |" for o in val["adjacent_outliers"]]
    else:
        L += ["없음."]
    L += ["", "## 4. 노선별 커버리지", "", "pool = 이 노선에 속한 표준데이터 역 수, sequenced = 시퀀스에 들어간 역 수 (직결 분기점 포함)", "",
          "| 노선 | 이름 | pool | sequenced | pool∩seq | 시퀀스 | 엣지 |", "| :- | :- | -: | -: | -: | -: | -: |"]
    L += [f"| {c['line']} | {c['name']} | {c['pool']} | {c['sequenced']} | {c['from_pool']} | {c['sequences']} | {c['edges']} |" for c in val["coverage"]]
    L += ["", "## 5. 보정 내역", "", "### 좌표 보정 (config/kr_station_fixes.yaml)", "",
          "| id | 역명 | 이동 거리(m) |", "| :- | :- | -: |"]
    L += [f"| {f['id']} | {f['name']} | {f['moved_m']:.0f} |" for f in val["coord_fixes"]]
    L += ["", "### 노선 보정 (config/kr_lines.yaml)", "", "| 노선 id | 원본 | 보정 종류 |", "| :- | :- | :- |"]
    L += [f"| {p['id']} | {p['source']} | {', '.join(p['ops'])} |" for p in val["patched_lines"]]
    if val["unused_line_defs"]:
        L += ["", "## 경고: 원본에 없는 노선 정의", ""] + [f"- {u}" for u in val["unused_line_defs"]]
    (ROOT / "docs" / "reports" / "m2_lines_validation.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
