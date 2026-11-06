#!/usr/bin/env python3
"""4차 Q0-7: 3차(main) ↔ 4차(현재) 전후 비교 — 그래프 지표, 포탈 목록, 퍼즐, 13정류장 최대거리, 한국-타이베이 국가 간 포탈.
출력: docs/reports/evidence/run3_vs_run4.md, data/processed/run3_vs_run4.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402

BASE = "origin/main"


def old(path):
    try:
        out = subprocess.run(["git", "show", f"{BASE}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return json.loads(out)
    except subprocess.CalledProcessError:
        return None


def new(path):
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> int:
    L = ["# 3차(main) ↔ 4차 전후 비교", "", f"생성: `python3 scripts/compare_run3_run4.py` (3차 = `{BASE}`의 산출물, 4차 = 이 브랜치)", "",
         "## 1. 한국 그래프 지표 (strict)", "", "| 항목 | 3차 | 4차 | 변화 원인 |", "| :- | -: | -: | :- |"]
    mo, mn = old("data/processed/kr/strict/metrics.json"), new("data/processed/kr/strict/metrics.json")
    why = {"stations": "고아 레코드 광운대역[경의중앙선] 제외 (Q5)", "clusters": "부전 역외 환승 재클러스터 (Q6-3)",
           "portals_total": "부전 포탈 소멸 (Q6-3)", "portal_links": "부전 포탈 소멸", "transfer_clusters_multi": "부전 재클러스터",
           "routing_nodes": "역 1 + 포탈 1 감소", "routing_edges": "고아 레코드·부전 포탈 엣지 감소"}
    rows = []
    for k in ("stations", "clusters", "lines", "sequences", "ride_edges", "transfer_clusters_multi", "portals_total", "portal_links",
              "routing_nodes", "routing_edges"):
        a, b = mo["counts"][k], mn["counts"][k]
        L.append(f"| {k} | {a} | {b} | {why.get(k, '') if a != b else ''} |")
        rows.append((k, a, b))
    for label, key in (("워프 有 컴포넌트", ("with_warp", "components")), ("워프 有 지름", ("with_warp", "diameter", "value")),
                       ("워프 有 평균 최단 비용", ("with_warp", "diameter", "mean_cost")), ("워프 無 컴포넌트", ("without_warp", "components")),
                       ("워프 無 지름(최대 컴포넌트)", ("without_warp", "diameter", "value"))):
        a, b = mo, mn
        for x in key:
            a, b = a[x], b[x]
        L.append(f"| {label} | {a} | {b} | |")
        rows.append((label, a, b))
    L.append(f"| 지름 양 끝 | {mo['with_warp']['diameter']['from']} → {mo['with_warp']['diameter']['to']} | "
             f"{mn['with_warp']['diameter']['from']} → {mn['with_warp']['diameter']['to']} | |")
    po, pn = old("data/processed/kr/strict/portals.json"), new("data/processed/kr/strict/portals.json")
    so, sn = {p["name"] for p in po["portals"]}, {p["name"] for p in pn["portals"]}
    L += ["", "## 2. 한국 포탈 목록 (strict, T1)", "",
          f"- 3차 {len(so)}개 → 4차 {len(sn)}개. 사라짐: {', '.join(sorted(so - sn)) or '없음'} · 새로 생김: {', '.join(sorted(sn - so)) or '없음'}",
          f"- 4차 목록: {', '.join(sorted(sn))}",
          "- 개통 예정 노선을 켜면 추가될 포탈: T1 신기 (양산선 ↔ 대구1호선) — `docs/reports/q0_planned_preview.md`"]
    wo, wn = old("data/processed/world/compare.json"), new("data/processed/world/compare.json")
    L += ["", "## 3. 한국 + 타이베이 국가 간 포탈", "", "| ruleset | 3차 | 4차 |", "| :- | :- | :- |"]
    for n in ("tw_t1", "tw_t12", "tw_t123"):
        a = [p["name"] for p in wo["results"][n]["portals"] if p["cross_country"]]
        b = [f"{p['name']}({p['confidence']})" for p in wn["results"][n]["portals"] if p["cross_country"]]
        L.append(f"| `{n}` | {len(a)}개 (공식명만) | {len(b)}개: {', '.join(b) or '-'} |")
    L.append(f"| 참고 `tw_t12_label` → `tw_t12_official` | {len([p for p in wo['results']['tw_t12_label']['portals'] if p['cross_country']])}개 (라벨 허용) | "
             f"{len([p for p in wn['results']['tw_t12_official']['portals'] if p['cross_country']])}개 (공식명만) |")
    t3o = [p["name"] for p in wo["results"]["tw_t123"]["portals"] if p["tier"].startswith("T3")]
    t3n = [f"{p['tier']} {p['name']}" for p in wn["results"]["tw_t123"]["portals"] if p["tier"].startswith("T3")]
    t3b = [f"{p['tier']} {p['name']}" for p in wn["results"]["tw_t123b"]["portals"] if p["tier"].startswith("T3")]
    L.append(f"| T3 포탈 (`tw_t123`) | {', '.join(t3o) or '-'} | {', '.join(t3n) or '없음'} (T3b를 켠 `tw_t123b`: {', '.join(t3b) or '-'}) |")
    zo, zn = old("data/processed/puzzles.json"), new("data/processed/puzzles.json")
    L += ["", "## 4. 퍼즐", "", "| 항목 | 3차 | 4차 |", "| :- | -: | -: |",
          f"| 퍼즐 풀 | {len(zo['puzzles'])} | {len(zn['puzzles'])} |",
          f"| 데일리 일정 길이 | {len(zo['daily_order'])} (풀 전체 셔플) | {len(zn['daily_order'])} (제약 일정) |",
          f"| 유일 최적해 순서쌍 | {zo['stats']['pairs_unique_optimum']:,} | {zn['stats']['pairs_unique_optimum']:,} |",
          f"| 순서쌍 전체 | {zo['stats']['pairs']:,} | {zn['stats']['pairs']:,} |"]
    d4 = zn["stats"]["daily_order"]["violations"]
    L.append(f"| 일정 제약 위반 (i/ii/iii/iv) | (`docs/reports/q2_daily_order.md`) | {d4['signature']}/{d4['jaccard']}/{d4['window']}/{d4['weekday']} |")
    by_o, by_n = {p["id"]: p for p in zo["puzzles"]}, {p["id"]: p for p in zn["puzzles"]}
    L += ["", "데일리 1~4일차:", "", "| 일 | 3차 | 4차 |", "| -: | :- | :- |"]
    for i in range(4):
        a, b = by_o[zo["daily_order"][i]], by_n[zn["daily_order"][i]]
        L.append(f"| {i + 1} | {a['from_label']} → {a['to_label']} ({'+'.join(a['warp_portals'])}) | {b['from_label']} → {b['to_label']} ({'+'.join(b['warp_portals'])}) |")
    no, nn = old("data/processed/n_stops_max.json"), new("data/processed/n_stops_max.json")
    L += ["", f"## 5. {nn['N']}정류장 최대 거리 (워프 허용)", "", "| 기준 | 3차 1위 | 4차 1위 |", "| :- | :- | :- |"]
    for k, t in (("great_circle", "시작-끝 대권거리"), ("track", "탑승 구간 거리 합")):
        a, b = no["with_warp"][k][0], nn["with_warp"][k][0]
        L.append(f"| {t} | {a['value_m'] / 1000:.1f}km {a['start_label']} → {a['end_label']} (워프 {a['warps']}) | "
                 f"{b['value_m'] / 1000:.1f}km {b['start_label']} → {b['end_label']} (워프 {b['warps']}) |")
    same_top = [(x["start"], x["end"]) for x in no["with_warp"]["great_circle"][:20]] == [(x["start"], x["end"]) for x in nn["with_warp"]["great_circle"][:20]]
    L.append(f"\n상위 20 (대권거리) 목록 동일: {'예' if same_top else '아니오'}")
    out = ROOT / "docs" / "reports" / "evidence" / "run3_vs_run4.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "processed" / "run3_vs_run4.json").write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
