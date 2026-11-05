#!/usr/bin/env python3
"""N4. ruleset 비교: 환승 비용 × 환승 판정 거리 D 조합별 그래프 지표와 포탈 목록 차이.

입력: data/processed/kr/{stations,ride_edges,lines}.json, config/ruleset_grid.yaml (+ base ruleset)
출력: data/processed/kr/ruleset_compare.json, docs/reports/n4_ruleset_compare.md
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.metrics import compute_metrics  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base  # noqa: E402

PROC = ROOT / "data" / "processed" / "kr"


def combo_name(base, t, d):
    return f"{base}_t{t}_d{d}"


def portal_sig(p, clusters_by_id):
    """조합 간 비교용 포탈 표현: 이름 + 연결 클러스터의 (도시, 노선 묶음)."""
    parts = []
    for cid in p["cluster_ids"]:
        c = clusters_by_id[cid]
        parts.append(f"{'/'.join(c['cities'])}:{'+'.join(sorted(set(l.split(':', 1)[1] for l in c['lines'])))}")
    return f"{p['name']} [{' | '.join(sorted(parts))}]"


def main() -> int:
    grid = yaml.safe_load(open(ROOT / "config" / "ruleset_grid.yaml", encoding="utf-8"))
    base = grid["base"]
    rows, portal_sets, merged = [], {}, {}
    for t, d in itertools.product(grid["axes"]["transfer"], grid["axes"]["D"]):
        name = combo_name(base, t, d)
        rs = load_ruleset(base, overrides={"costs": {"transfer": t}, "cluster": {"transfer_distance_m": d}}, name=name)
        st, ed, ln = load_base()
        w = build_world(st, ed, ln, rs)
        m = compute_metrics(st, ed, ln, w["clusters"], w["portals"], w["adj"], rs)
        cmap = {c["id"]: c for c in w["clusters"]}
        portal_sets[(t, d)] = {portal_sig(p, cmap): p for p in w["portals"]}
        # 같은 이름 레코드가 한 클러스터로 묶인 이름 → 이 D에서 '환승'으로 처리되는 동명 레코드
        merged[(t, d)] = {c["name"]: len(c["station_ids"]) for c in w["clusters"]}
        cnt = {}
        for c in w["clusters"]:
            cnt[c["name"]] = cnt.get(c["name"], 0) + 1
        merged[(t, d)] = cnt
        rows.append({"name": name, "transfer": t, "D": d, "counts": m["counts"],
                     "with_warp": {k: v for k, v in m["with_warp"].items()},
                     "without_warp": {k: v for k, v in m["without_warp"].items() if k != "component_list"},
                     "top_portals": m["top_portals"][:5],
                     "same_city_portals": sorted(p["name"] for p in w["portals"]
                                                 if len({tuple(cmap[c]["cities"]) for c in p["cluster_ids"]}) == 1)})
        print(f"[09] {name}: clusters={m['counts']['clusters']} portals={m['counts']['portals_total']} "
              f"dia_warp={m['with_warp']['diameter']['value']} dia_nowarp={m['without_warp']['diameter']['value']}")
    ref = (grid["reference"]["transfer"], grid["reference"]["D"])
    diffs = []
    for key, ps in portal_sets.items():
        if key == ref:
            continue
        added = sorted(set(ps) - set(portal_sets[ref]))
        removed = sorted(set(portal_sets[ref]) - set(ps))
        diffs.append({"transfer": key[0], "D": key[1], "added": added, "removed": removed})
    # D에 따라 클러스터 수가 달라지는 이름 (환승 ↔ 포탈 경계 사례)
    names = sorted(set().union(*[set(v) for v in merged.values()]))
    ds = grid["axes"]["D"]
    boundary = [{"name": n, **{f"D{d}": merged[(ref[0], d)].get(n, 0) for d in ds}} for n in names
                if len({merged[(ref[0], d)].get(n, 0) for d in ds}) > 1]
    doc = {"grid": grid, "rows": rows, "portal_diffs_vs_reference": diffs, "cluster_count_changes_by_D": boundary}
    (PROC / "ruleset_compare.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(doc, ref)
    return 0


def write_report(doc, ref):
    rows = doc["rows"]
    L = ["# N4 ruleset 비교 — 환승 비용 × 환승 판정 거리 D", "",
         f"생성: `python3 pipeline/09_compare_rulesets.py` (격자: `config/ruleset_grid.yaml`, base `{doc['grid']['base']}`). "
         f"기준 조합: 환승 {ref[0]}, D={ref[1]}m (= 현재 strict).", "",
         "지표는 클러스터(물리적 역) 수준. 환승 비용 1일 때 지름·평균 비용은 역 수준 그래프에서 계산해 환승 비용이 반영된다.", "",
         "## 1. 그래프 지표", "",
         "| 환승 | D(m) | 클러스터 | 다중 레코드 클러스터 | T1 포탈 | 포탈 연결 | 같은 도시 포탈 | 워프 有 지름 | 워프 有 평균 | 워프 無 컴포넌트 | 워프 無 최대 비율 | 워프 無 지름 | 워프 無 평균 |",
         "| -: | -: | -: | -: | -: | -: | -: | -: | -: | -: | -: | -: | -: |"]
    for r in rows:
        c, w, n = r["counts"], r["with_warp"], r["without_warp"]
        mark = "**" if (r["transfer"], r["D"]) == ref else ""
        L.append(f"| {mark}{r['transfer']}{mark} | {mark}{r['D']}{mark} | {c['clusters']} | {c['transfer_clusters_multi']} | {c['portals_total']} | "
                 f"{c['portal_links']} | {len(r['same_city_portals'])} | {w['diameter']['value']} | {w['diameter']['mean_cost']} | "
                 f"{n['components']} | {n['largest_component_ratio']:.1%} | {n['diameter']['value']} | {n['diameter']['mean_cost']} |")
    L += ["", "지름 양 끝 (워프 있음):", ""]
    L += [f"- 환승 {r['transfer']}, D={r['D']}: {r['with_warp']['diameter']['from']} ↔ {r['with_warp']['diameter']['to']} "
          f"(비용 {r['with_warp']['diameter']['value']})" for r in rows]
    L += ["", "## 2. 포탈 목록 차이 (기준 조합 대비)", "",
          "포탈은 '이름 [도시:노선 묶음 | ...]'로 비교한다. 환승 비용은 포탈 생성에 영향이 없어서 D만 차이를 만든다.", "",
          "| 환승 | D(m) | 추가된 포탈 | 사라진 포탈 |", "| -: | -: | :- | :- |"]
    for d in doc["portal_diffs_vs_reference"]:
        L.append(f"| {d['transfer']} | {d['D']} | {'<br>'.join(d['added']) or '-'} | {'<br>'.join(d['removed']) or '-'} |")
    L += ["", "## 3. 같은 도시 포탈 (조합별)", "", "| 환승 | D(m) | 같은 도시 포탈 |", "| -: | -: | :- |"]
    L += [f"| {r['transfer']} | {r['D']} | {', '.join(r['same_city_portals']) or '-'} |" for r in rows]
    L += ["", f"## 4. D에 따라 클러스터 수가 바뀌는 이름 (환승 비용 {ref[0]})", "",
          "같은 이름 역이 D 안에 들어오면 한 클러스터(환승), 밖이면 별개 클러스터(포탈 후보)다.", "",
          "| 이름 | " + " | ".join(f"D={k[1:]}" for k in doc["cluster_count_changes_by_D"][0] if k.startswith("D")) + " |"
          if doc["cluster_count_changes_by_D"] else "변화 없음.",
          ]
    if doc["cluster_count_changes_by_D"]:
        ks = [k for k in doc["cluster_count_changes_by_D"][0] if k.startswith("D")]
        L.append("| :- | " + " | ".join("-:" for _ in ks) + " |")
        L += [f"| {b['name']} | " + " | ".join(str(b[k]) for k in ks) + " |" for b in doc["cluster_count_changes_by_D"]]
    (ROOT / "docs" / "reports" / "n4_ruleset_compare.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
