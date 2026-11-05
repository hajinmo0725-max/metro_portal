#!/usr/bin/env python3
"""M1-2. 한국 역 목록 정제.

입력: data/raw/kric/stations_std.xlsx (마스터: 표준데이터 역사정보)
      data/raw/kric/stations_metro.xlsx (보강: 다국어 역명, 부역명)
      config/kr_scope.yaml (스코프 제외 노선), config/kr_station_fixes.yaml (좌표·별칭 보정)
출력: data/processed/kr/stations.json

Station은 '노선별 역' 단위다 (표준데이터의 1행 = 1 Station). 같은 물리적 역의 묶음은
M3에서 StationCluster로 만든다. 다국어 보강은 정규화 이름 일치 + 거리 조건으로 붙인다.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.kric import clean_text, read_sheet, region_of  # noqa: E402
from metro_portal.normalize import normalize_name  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402

RAW = ROOT / "data" / "raw" / "kric"
OUT = ROOT / "data" / "processed" / "kr" / "stations.json"


def name(text, lang, script, source, kind="primary", official=True):
    return {"text": text, "lang": lang, "script": script, "source": source, "official": official, "kind": kind}


def main() -> int:
    vcfg = yaml.safe_load(open(ROOT / "config" / "validation.yaml", encoding="utf-8"))["stations"]
    # 보강 매칭에 쓸 정규화 규칙: ruleset(strict)의 normalize 섹션을 그대로 쓴다
    norm = load_ruleset("strict")["normalize"]

    std = read_sheet(RAW / "stations_std.xlsx")
    metro = read_sheet(RAW / "stations_metro.xlsx")
    fetch_log = json.loads((RAW / "fetch_log.json").read_text(encoding="utf-8"))

    # 보강용 인덱스: 정규화명 → [(lat, lon, row)]
    midx = defaultdict(list)
    for r in metro:
        lon, lat = r.get("역 위치(경도)"), r.get("역 위치(위도)")
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if lat > lon:  # 열 뒤바뀜 방어
            lat, lon = lon, lat
        midx[normalize_name(clean_text(r["역명(한글)"]), norm)].append((lat, lon, r))

    # 스코프 제외 (config/kr_scope.yaml)
    scope = yaml.safe_load(open(ROOT / "config" / "kr_scope.yaml", encoding="utf-8")) or {}
    excl_groups = {e["line_group"]: e["reason"] for e in scope.get("exclude_line_groups", [])}

    # 1) 표준데이터 행 정리 (중복 제거, 스코프 제외)
    rows, seen, dropped, excluded = [], {}, [], []
    for r in sorted(std, key=lambda r: (clean_text(r["노선번호"]), clean_text(r["노선명"]), clean_text(r["역번호"]), clean_text(r["역사명"]))):
        code, line_no, line_name = clean_text(r["역번호"]), clean_text(r["노선번호"]), clean_text(r["노선명"])
        ko = clean_text(r["역사명"])
        if f"{line_no}:{line_name}" in excl_groups:
            excluded.append({"line_group": f"{line_no}:{line_name}", "code": code, "name": ko})
            continue
        lat, lon = float(r["역위도"]), float(r["역경도"])
        key = (line_no, line_name, code)
        if key in seen:
            prev = seen[key]
            dropped.append({"line_no": line_no, "line_name": line_name, "code": code, "name": ko,
                            "kept": prev["name_ko"], "distance_m": round(haversine_m(lat, lon, prev["lat"], prev["lon"]), 1),
                            "reason": "같은 노선·역번호 중복 행"})
            continue
        rec = {"r": r, "code": code, "line_no": line_no, "line_name": line_name, "name_ko": ko, "lat": lat, "lon": lon}
        seen[key] = rec
        rows.append(rec)

    # 2) 다국어 보강 배정: 같은 정규화명 + 거리 이내 후보 중 (노선명 일치 우선, 거리 오름차순) 1:1 그리디
    def line_match(std_line: str, metro_line: str) -> bool:
        a, b = std_line.replace(" ", ""), metro_line.replace(" ", "")
        return bool(b) and (b in a or a in b)

    pairs = []
    for i, rec in enumerate(rows):
        for mlat, mlon, mr in midx.get(normalize_name(rec["name_ko"], norm), []):
            d = haversine_m(rec["lat"], rec["lon"], mlat, mlon)
            if d <= vcfg["enrich_max_distance_m"]:
                lm = line_match(rec["line_name"], clean_text(mr["운영노선"]))
                pairs.append((0 if lm else 1, round(d, 3), i, id(mr), mr))
    pairs.sort(key=lambda p: (p[0], p[1], p[2], clean_text(p[4]["운영노선"])))
    assign, used_metro = {}, set()
    for _, _, i, mid, mr in pairs:
        if i in assign or mid in used_metro:
            continue
        assign[i] = mr
        used_metro.add(mid)
    for _, _, i, mid, mr in pairs:  # 남은 표준 행은 재사용 허용 (가장 가까운 후보)
        if i not in assign:
            assign[i] = mr
    # 폴백: 다국어 파일 좌표가 틀린 경우(부산 1호선 등)를 위해 거리 조건 없이
    # (정규화명, 노선명, 운영기관)이 유일하게 일치하는 미사용 행을 배정
    name_only = []
    for i, rec in enumerate(rows):
        if i in assign:
            continue
        op = clean_text(rec["r"]["운영기관명"]).replace(" ", "")
        cands = [mr for _, _, mr in midx.get(normalize_name(rec["name_ko"], norm), [])
                 if id(mr) not in used_metro and line_match(rec["line_name"], clean_text(mr["운영노선"]))
                 and clean_text(mr["철도운영기관명"]).replace(" ", "") in op]
        if len(cands) == 1:
            assign[i] = cands[0]
            used_metro.add(id(cands[0]))
            name_only.append(i)

    # 같은 노선번호·역번호를 다른 노선명이 공유하는 경우(I4108 경의중앙선/경춘선)는 id에 노선명을 넣는다
    nos = Counter((rec["line_no"], rec["code"]) for rec in rows)
    stations, unenriched = [], []
    for i, rec in enumerate(rows):
        r, code, line_no, line_name, ko = rec["r"], rec["code"], rec["line_no"], rec["line_name"], rec["name_ko"]
        sid = f"kr:{line_no}:{code}" if nos[(line_no, code)] == 1 else f"kr:{line_no}:{line_name}:{code}"
        names = [name(ko, "ko", "Hang", "kric_std")]
        if clean_text(r["영문역사명"]):
            names.append(name(clean_text(r["영문역사명"]), "en", "Latn", "kric_std"))
        if clean_text(r["한자역사명"]):
            names.append(name(clean_text(r["한자역사명"]), "ko", "Hani", "kric_std"))
        mr = assign.get(i)
        if mr is not None:
            for col, lang, script, kind in [
                ("역명(영어)", "en", "Latn", "primary"), ("역명(로마자)", "ko", "Latn", "romanization"),
                ("역명(일본어)", "ja", "Jpan", "primary"), ("역명(중국어간체)", "zh", "Hans", "primary"),
                ("역명(중국어번체)", "zh", "Hant", "primary"), ("역명(부역명)", "ko", "Hang", "subname"),
            ]:
                t = clean_text(mr.get(col))
                if t and t not in vcfg["placeholder_names"] and not any(n["text"] == t and n["lang"] == lang and n["script"] == script for n in names):
                    names.append(name(t, lang, script, "kric_metro", kind=kind))
        else:
            unenriched.append(sid)
        stations.append({
            "id": sid,
            "code": code,
            "name_ko": ko,
            "lat": round(rec["lat"], 7),
            "lon": round(rec["lon"], 7),
            "line_no": line_no,
            "line_name": line_name,
            "line_group": f"{line_no}:{line_name}",
            "operator": clean_text(r["운영기관명"]),
            "region": region_of(r["역사도로명주소"]),
            "address": clean_text(r["역사도로명주소"]),
            "transfer_flag": "환승" in clean_text(r["환승역구분"]),
            "transfer_lines_raw": clean_text(r["환승노선명"]),
            # 3차 A3: 공식 환승 판정용. 노선번호 목록 (config/kr_transfer_codes.yaml로 해석)
            "transfer_line_nos_raw": clean_text(r["환승노선번호"]),
            "names": names,
            "source": "kric_std",
            "source_date": str(r["데이터기준일자"])[:10] if r["데이터기준일자"] else "",
        })
    assert len({s["id"] for s in stations}) == len(stations), "station id 중복"

    # 좌표 보정 (config/kr_station_fixes.yaml)
    fix_cfg = yaml.safe_load(open(ROOT / "config" / "kr_station_fixes.yaml", encoding="utf-8"))
    fixes = fix_cfg.get("fixes", [])
    byid = {s["id"]: s for s in stations}
    fixes_applied = []
    for fx in fixes:
        st = byid.get(fx["id"])
        if st is None:
            raise SystemExit(f"[02] 보정 대상 역 없음: {fx['id']}")
        moved = haversine_m(st["lat"], st["lon"], fx["lat"], fx["lon"])
        st["coord_fix"] = {"from": [st["lat"], st["lon"]], "reason": fx["reason"]}
        st["lat"], st["lon"] = fx["lat"], fx["lon"]
        fixes_applied.append({"id": fx["id"], "name": st["name_ko"], "moved_m": round(moved, 1)})
    for al in fix_cfg.get("aliases", []):
        st = byid.get(al["id"])
        if st is None:
            raise SystemExit(f"[02] 별칭 대상 역 없음: {al['id']}")
        st["aliases"] = sorted(set(st.get("aliases", [])) | set(al["aliases"]))
        st["alias_reason"] = al["reason"]

    unused_metro = sorted(
        {(clean_text(mr["철도운영기관명"]), clean_text(mr["운영노선"]), clean_text(mr["역명(한글)"]))
         for lst in midx.values() for _, _, mr in lst if id(mr) not in used_metro})

    # 좌표 범위 검증
    bb = vcfg["bbox"]
    out_of_bbox = [s["id"] for s in stations if not (bb["lat_min"] <= s["lat"] <= bb["lat_max"] and bb["lon_min"] <= s["lon"] <= bb["lon_max"])]

    langs = Counter(f"{n['lang']}-{n['script']}" for s in stations for n in s["names"])
    doc = {
        "meta": {
            "description": "한국 도시철도·광역철도 역 (노선별 역 단위). 표준데이터 범위에서 config/kr_scope.yaml 제외분만 뺐다.",
            "sources": {k: {"title": v["title"], "url": v["url"], "downloaded_at": v.get("downloaded_at", ""),
                            "file": v.get("content_disposition", "")} for k, v in sorted(fetch_log["files"].items())},
            "license": "공공데이터포털/레일포털 표준데이터: 이용허락범위 제한 없음",
            "counts": {
                "stations": len(stations),
                "line_groups": len({s["line_group"] for s in stations}),
                "names_by_lang_script": dict(sorted(langs.items())),
                "unenriched": len(unenriched),
                "enriched_by_name_only": len(name_only),
                "dropped_duplicates": len(dropped),
                "out_of_bbox": len(out_of_bbox),
                "coord_fixes": len(fixes_applied),
                "excluded_by_scope": len(excluded),
            },
            "excluded_by_scope": {"line_groups": excl_groups, "stations": excluded},
            "dropped_duplicates": dropped,
            "coord_fixes": fixes_applied,
            "unenriched_station_ids": unenriched,
            "enriched_by_name_only_ids": [stations[i]["id"] for i in name_only],
            "metro_rows_not_in_std": [list(x) for x in unused_metro],
        },
        "stations": stations,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc["meta"]["counts"], ensure_ascii=False, indent=1))
    print(f"[02] dropped duplicates: {dropped}")
    print(f"[02] metro rows not matched to std ({len(unused_metro)}): {unused_metro[:40]}")
    print(f"[02] wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
