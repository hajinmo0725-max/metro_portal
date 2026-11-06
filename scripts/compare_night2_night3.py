#!/usr/bin/env python3
"""A7: 2차 결과(origin/main, PR #1·#2 머지본)와 3차 결과의 전후 비교표.

2차 산출물은 git에서 읽는다 (`git show <ref>:<path>`). 3차는 작업 트리의 산출물.
사용: python3 scripts/compare_night2_night3.py [--before origin/main]
출력: docs/reports/night3_compare.md, data/processed/kr/night3_compare.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_git(ref, path):
    out = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def load_now(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def portal_sigs(clusters, portals):
    cm = {c["id"]: c for c in clusters}
    out = set()
    for p in portals:
        parts = []
        for cid in p["cluster_ids"]:
            c = cm[cid]
            parts.append(f"{'/'.join(c['cities'])}:{'+'.join(sorted(set(l.split(':', 1)[1] for l in c['lines'])))}")
        out.add(f"{p['name']} [{' ↔ '.join(sorted(parts))}]")
    return out


def wd_counts(chk):
    edges = [e for r in chk["sequences"] for e in r["edges"]]
    from collections import Counter
    return len(edges), Counter(e["wikidata"] for e in edges)


def route_txt(path):
    return " ".join(("⇢" if x["via"] == "warp" else ("" if x["via"] == "start" else "→")) + x["label"].split(" ", 1)[1].split("#")[0] for x in path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default="origin/main")
    a = ap.parse_args()
    B = lambda p: load_git(a.before, p)  # noqa: E731
    N = load_now
    rows = []

    def row(group, item, b, n, note=""):
        rows.append({"group": group, "item": item, "before": b, "after": n, "note": note})

    for rs in ("strict", "strict_transfer1"):
        mb, mn = B(f"data/processed/kr/{rs}/metrics.json"), N(f"data/processed/kr/{rs}/metrics.json")
        cb, cn = mb["counts"], mn["counts"]
        g = f"그래프 `{rs}`"
        for k, t in (("stations", "역 레코드"), ("clusters", "클러스터(물리적 역)"), ("transfer_clusters_multi", "다중 레코드 클러스터"),
                     ("lines", "노선"), ("sequences", "시퀀스"), ("ride_edges", "승차 엣지")):
            row(g, t, cb[k], cn[k])
        row(g, "유향 승차 엣지", cb.get("ride_edges_directed", 0), cn.get("ride_edges_directed", 0), "A2 응암순환")
        row(g, "T1 포탈 / 포탈 연결", f"{cb['portals_total']} / {cb['portal_links']}", f"{cn['portals_total']} / {cn['portal_links']}")
        row(g, "라우팅 노드 / 방향 엣지", f"{cb['routing_nodes']} / {cb['routing_edges']}", f"{cn['routing_nodes']} / {cn['routing_edges']}")
        for key, t in (("with_warp", "워프 有"), ("without_warp", "워프 無")):
            wb, wn = mb[key], mn[key]
            row(g, f"{t} 컴포넌트 (강연결)", f"{wb['components']} (-)", f"{wn['components']} ({wn.get('strong_components', '-')})")
            row(g, f"{t} 최대 컴포넌트", f"{wb['largest_component_size']} ({wb['largest_component_ratio']:.1%})",
                f"{wn['largest_component_size']} ({wn['largest_component_ratio']:.1%})")
            row(g, f"{t} 지름 (양 끝)", f"{wb['diameter']['value']} ({wb['diameter']['from']}↔{wb['diameter']['to']})",
                f"{wn['diameter']['value']} ({wn['diameter']['from']}→{wn['diameter']['to']})", "3차는 순서쌍 (출발→도착)")
            row(g, f"{t} 평균 최단 비용", wb["diameter"]["mean_cost"], wn["diameter"]["mean_cost"])

    clb, cln = B("data/processed/kr/strict/clusters.json")["clusters"], N("data/processed/kr/strict/clusters.json")["clusters"]
    pb, pn = B("data/processed/kr/strict/portals.json")["portals"], N("data/processed/kr/strict/portals.json")["portals"]
    sb, sn = portal_sigs(clb, pb), portal_sigs(cln, pn)

    kb, kn = B("data/processed/kr/lines_check.json"), N("data/processed/kr/lines_check.json")
    eb, cb_ = wd_counts(kb)
    en, cn_ = wd_counts(kn)
    for k, t in (("adjacent", "Wikidata 인접 확인"), ("not_adjacent", "Wikidata 비인접"), ("not_adjacent_weak", "Wikidata 비인접(약)"),
                 ("unmatched", "Wikidata 매칭 불가")):
        row("노선 검증 (08)", t, f"{cb_.get(k, 0)} / {eb}", f"{cn_.get(k, 0)} / {en}")

    zb, zn = B("data/processed/puzzles.json"), N("data/processed/puzzles.json")
    for k, t in (("pairs", "쌍 (2차 무순서, 3차 순서쌍)"), ("pairs_reachable_without_warp", "워프 없이 도달"), ("pairs_warp_shortens", "워프로 단축"),
                 ("pairs_cross_component", "워프 없으면 불가"), ("pairs_unique_optimum", "최적해 유일"),
                 ("candidates_shortcut", "후보 shortcut"), ("candidates_crosscity", "후보 crosscity")):
        row("퍼즐 (10)", t, zb["stats"][k], zn["stats"][k])
    row("퍼즐 (10)", "선정 퍼즐 수", len(zb["puzzles"]), len(zn["puzzles"]))
    keyf = lambda p: (p["from"], p["to"])  # noqa: E731
    pz_b, pz_n = {keyf(p): p for p in zb["puzzles"]}, {keyf(p): p for p in zn["puzzles"]}
    same = sum(1 for k in pz_n if k in pz_b and pz_b[k]["cost_warp"] == pz_n[k]["cost_warp"])
    row("퍼즐 (10)", "2차와 같은 (출발, 도착, 최적 비용) 퍼즐", "-", same)
    row("퍼즐 (10)", "데일리 1번 퍼즐", f"{zb['puzzles'][[p['id'] for p in zb['puzzles']].index(zb['daily_order'][0])]['from_label']} → "
        f"{zb['puzzles'][[p['id'] for p in zb['puzzles']].index(zb['daily_order'][0])]['to_label']}",
        f"{pz_first(zn)['from_label']} → {pz_first(zn)['to_label']}")

    nb, nn = B("data/processed/n_stops_max.json"), N("data/processed/n_stops_max.json")
    for key, t in (("great_circle", "대권거리"), ("track", "구간 거리 합")):
        for w, wt in (("with_warp", "워프 허용"), ("without_warp", "워프 금지")):
            xb, xn = nb[w][key][0], nn[w][key][0]
            row("13정류장 (10)", f"{t} 1위 ({wt})", f"{xb['value_m'] / 1000:.1f}km {xb['start_label']} → {xb['end_label']}",
                f"{xn['value_m'] / 1000:.1f}km {xn['start_label']} → {xn['end_label']}")

    fb, fn = B("data/processed/fun_facts.json"), N("data/processed/fun_facts.json")
    row("fun facts (11)", "지름", f"{fb['diameter']['cost']} {fb['diameter']['from']} → {fb['diameter']['to']}",
        f"{fn['diameter']['cost']} {fn['diameter']['from']} → {fn['diameter']['to']}")
    row("fun facts (11)", "매개 중심성 1위 포탈", f"{fb['portal_hubs'][0]['portal']} {fb['portal_hubs'][0]['betweenness_share']:.1%}",
        f"{fn['portal_hubs'][0]['portal']} {fn['portal_hubs'][0]['betweenness_share']:.1%}")
    row("fun facts (11)", "전국 중심역", f"{fb['center_with_warp'][0]['station']} {fb['center_with_warp'][0]['mean_cost']}",
        f"{fn['center_with_warp'][0]['station']} {fn['center_with_warp'][0]['mean_cost']}")
    row("fun facts (11)", "최적해 최다 워프", fb["most_warps"]["warps"], fn["most_warps"]["warps"])

    # 13정류장 상위 5 상세
    top = {}
    for key in ("great_circle", "track"):
        top[key] = {"before": [(x["value_m"], x["start_label"], x["end_label"], x["warps"], route_txt(x["path"])) for x in nb["with_warp"][key][:5]],
                    "after": [(x["value_m"], x["start_label"], x["end_label"], x["warps"], route_txt(x["path"])) for x in nn["with_warp"][key][:5]]}
    out = {"before_ref": a.before, "rows": rows, "portals_added": sorted(sn - sb), "portals_removed": sorted(sb - sn), "n_stops_top5": top}
    (ROOT / "data" / "processed" / "kr" / "night3_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    L = ["# 2차 → 3차 전후 비교", "", f"생성: `python3 scripts/compare_night2_night3.py` (2차 = `{a.before}`의 산출물, 3차 = 이 브랜치 산출물)", "",
         "| 구분 | 항목 | 2차 | 3차 | 비고 |", "| :- | :- | :- | :- | :- |"]
    L += [f"| {r['group']} | {r['item']} | {r['before']} | {r['after']} | {r['note']} |" for r in rows]
    L += ["", "## T1 포탈 차이 (strict)", "", "| 구분 | 포탈 [도시:노선 ↔ ...] |", "| :- | :- |"]
    L += [f"| 추가 | {p} |" for p in out["portals_added"]] + [f"| 삭제 | {p} |" for p in out["portals_removed"]]
    if not out["portals_added"] and not out["portals_removed"]:
        L.append("| - | 없음 |")
    for key, t in (("great_circle", "대권거리"), ("track", "구간 거리 합")):
        L += ["", f"## 13정류장 {t} 상위 5 (워프 허용)", "", "| 순위 | 2차 | 3차 |", "| -: | :- | :- |"]
        for i, (b, n) in enumerate(zip(top[key]["before"], top[key]["after"]), 1):
            L.append(f"| {i} | {b[0] / 1000:.1f}km {b[1]} → {b[2]} (워프 {b[3]}) | {n[0] / 1000:.1f}km {n[1]} → {n[2]} (워프 {n[3]}) |")
    (ROOT / "docs" / "reports" / "night3_compare.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


def pz_first(z):
    return next(p for p in z["puzzles"] if p["id"] == z["daily_order"][0])


if __name__ == "__main__":
    raise SystemExit(main())
