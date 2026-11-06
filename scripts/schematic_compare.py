#!/usr/bin/env python3
"""4차 S5: 도식 엔진 비교 — 자체 MIP vs snap-lp(방향 고정 LP 반복) vs 지리 좌표. LOOM은 빌드가 막혀 비교에서 빠졌다.
권역별로 같은 지표(8방향 아닌 엣지, 교차, 노선 굴곡 45° 단위 합, 지리 대비 정규화 평균 변위)를 낸다.
입력: data/processed/schematic/summary.json (20단계 MIP 결과), config/schematic.yaml
출력: docs/reports/schematic/engine_compare.md, docs/reports/schematic/<region>_snaplp.svg
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal import schematic as S  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base, load_multi  # noqa: E402


def main() -> int:
    cfg = yaml.safe_load(open(ROOT / "config" / "schematic.yaml", encoding="utf-8"))
    summ = json.loads((ROOT / "data" / "processed" / "schematic" / "summary.json").read_text(encoding="utf-8"))
    w_kr = build_world(*load_base(), load_ruleset(cfg["ruleset"]))
    w_tw = None
    L = ["# S5 도식 엔진 비교", "", "생성: `python3 scripts/schematic_compare.py` (MIP 결과는 `pipeline/20_build_schematic.py`)", "",
         "- MIP = 자체 octilinear MIP (N&W 2011식, HiGHS). snap-lp = 엣지 방향을 가까운 8방향으로 고정하고 LP로 좌표를 푼 뒤 어긋난 엣지만 다시 고정 (순환 순서·평면성 보장 없음). 지리 = 투영 좌표 그대로.",
         "- LOOM(topo → loom → octi → transitmap)은 받기·빌드가 막혀 비교하지 못했다 (보고서 S2).",
         "- 지표: 8방향 아닌 엣지 수, 비인접 엣지 교차 수, 노선 굴곡(같은 노선의 연속 세 역에서 꺾인 각도를 45° 단위로 반올림한 합), 정규화 평균 변위(두 배치를 중심 0·RMS 1로 맞춘 뒤 역별 거리 평균, 지리 = 0).", "",
         "| 권역 | 역/엣지 | 엔진 | 8방향 아님 | 교차 | 굴곡(45°) | 변위 | 시간 | 상태 |", "| :- | :- | :- | -: | -: | -: | -: | -: | :- |"]
    for reg in cfg["regions"]:
        s = summ["regions"].get(reg["id"])
        if not s:
            continue
        if reg["country"] == "TW":
            w_tw = w_tw or build_world(*load_multi(("KR", "TW")), load_ruleset("tw_t12"))
            w = w_tw
        else:
            w = w_kr
        g = S.region_graph(w, reg["city"])
        cg = S.contract(g, keep_every=reg.get("keep_every", 2))
        t = time.time()
        r = S.solve_snap_lp(g, cg, {**cfg["solver"], **{k: v for k, v in reg.items() if k in cfg["solver"]}})
        pos = S.expand(g, cg, r["pos"])
        sec = round(time.time() - t, 1)
        st = S.layout_stats(g, pos)
        (ROOT / "docs" / "reports" / "schematic" / f"{reg['id']}_snaplp.svg").write_text(
            S.render_svg(g, pos, f"{reg['city']} — snap-lp (비교용)", size=1100), encoding="utf-8")
        sg, sm = s["stats_geo"], s["stats"]
        ne = f"{sm['nodes']}/{sm['edges']}"
        L.append(f"| {reg['city']} | {ne} | 지리 | {sg['non_octilinear_edges']} | {sg['crossings']} | {sg['bend_units_45deg']} | 0 | - | - |")
        L.append(f"| | | **{s['engine']}** | {sm['non_octilinear_edges']} | {sm['crossings']} | {sm['bend_units_45deg']} | {sm['mean_displacement_norm']} | {s['seconds']}s | {s['status']} |")
        L.append(f"| | | snap-lp | {st['non_octilinear_edges']} | {st['crossings']} | {st['bend_units_45deg']} | {st['mean_displacement_norm']} | {sec}s | 고정 6회 |")
        print(f"[cmp] {reg['id']} snap-lp {st}")
    out = ROOT / "docs" / "reports" / "schematic" / "engine_compare.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
