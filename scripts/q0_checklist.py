#!/usr/bin/env python3
"""4차 Q0-1·3: 역 데이터 버전과 최근 개통 역 포함 여부 점검 → docs/reports/evidence/q0_checklist.md

근거 열: 표준데이터 행(노선번호·역번호·데이터기준일자) 또는 보충(config/kr_supplement.yaml), 노선 시퀀스(lines.json) 포함 여부.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.kric import clean_text, read_sheet  # noqa: E402
from metro_portal.normalize import normalize_name  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402

CHECK = [
    ("인천1호선 검단연장 (2025-06-28)", "incheon-1", ["아라", "신검단중앙", "검단호수공원"]),
    ("대경선 전체 (2024-12-14) + 북삼 (2026-02)", "daegyeong", ["구미", "사곡", "북삼", "왜관", "서대구", "대구", "동대구", "경산"]),
    ("대구1호선 안심~하양 (2024-12-21)", "daegu-1", ["대구한의대병원", "부호", "하양"]),
    ("GTX-A 운정중앙~서울역 (2024-12-28)", "gtx-a", ["운정중앙", "킨텍스", "대곡", "연신내", "서울역"]),
    ("GTX-A 수서~동탄 (2024-03-30)", "gtx-a", ["수서", "성남", "구성", "동탄"]),
]


def main() -> int:
    norm = load_ruleset("strict")["normalize"]
    log = json.loads((ROOT / "data" / "raw" / "kric" / "fetch_log.json").read_text(encoding="utf-8"))
    std = read_sheet(ROOT / "data" / "raw" / "kric" / "stations_std.xlsx")
    stations = json.loads((ROOT / "data" / "processed" / "kr" / "stations.json").read_text(encoding="utf-8"))["stations"]
    lines = {ln["id"]: ln for ln in json.loads((ROOT / "data" / "processed" / "kr" / "lines.json").read_text(encoding="utf-8"))["lines"]}
    sid = {s["id"]: s for s in stations}
    L = ["# Q0 역 데이터 점검", "", "생성: `python3 scripts/q0_checklist.py`", "", "## 1. 파이프라인이 쓰는 원본 파일", "",
         "| 키 | 파일명 (Content-Disposition) | 수집 시각 | 바이트 |", "| :- | :- | :- | -: |"]
    for k, v in sorted(log["files"].items()):
        fn = v.get("content_disposition", "").split("filename=")[-1].strip('"')
        L.append(f"| {k} | {fn} | {v.get('downloaded_at', v.get('source'))} | {v.get('bytes', '')} |")
    dates = {}
    for r in std:
        d = str(r["데이터기준일자"])[:10]
        dates[d] = dates.get(d, 0) + 1
    L += ["", f"표준데이터 역사정보 행 {len(std)}개, 행별 '데이터기준일자' 최신값 {max(dates)} (상위: "
          + ", ".join(f"{d} {n}행" for d, n in sorted(dates.items(), key=lambda kv: -kv[1])[:5]) + ")", "",
          "## 2. 최근 개통 역 포함 여부", "", "| 구간 | 역 | 역 레코드 | 출처 | 기준일자/신설일자 | 노선 시퀀스 |", "| :- | :- | :- | :- | :- | :- |"]
    missing = 0
    for title, line_id, names in CHECK:
        ln = lines.get(line_id)
        seq_ids = {x for q in (ln["sequences"] if ln else []) for x in q["station_ids"]}
        for nm in names:
            key = normalize_name(nm, norm)
            hits = [s for s in stations if s["id"] in seq_ids and normalize_name(s["name_ko"], norm) == key]
            if not hits:
                missing += 1
                L.append(f"| {title} | {nm} | **없음** | - | - | - |")
                continue
            s = hits[0]
            src = "표준데이터" if s["source"] == "kric_std" else ("보충 (kr_supplement.yaml, 다국어 파일 행)" if s["source"] == "kric_metro_supplement" else s["source"])
            date = s.get("source_date", "") + (f" / 신설 {s['opened']}" if s.get("opened") else "")
            L.append(f"| {title} | {nm} | `{s['id']}` {s['name_ko']} | {src} | {date} | {line_id} ✓ |")
    # 자기부상 제외 확인
    maglev = [r for r in std if clean_text(r["노선명"]) == "자기부상철도"]
    in_data = [s for s in stations if s["line_group"].startswith("S28M1")]
    L += ["", "## 3. 스코프 제외", "",
          f"- 인천공항 자기부상철도: 원본 표준데이터에 {len(maglev)}행 있음 → `config/kr_scope.yaml`로 제외, 산출물 {len(in_data)}행.",
          "", f"누락 {missing}건."]
    out = ROOT / "docs" / "reports" / "evidence" / "q0_checklist.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
