#!/usr/bin/env python3
"""4차 S 보고서용 표 생성: data/processed/schematic/summary.json → docs/reports/schematic/tables.md
(권역 표, 수도권 변형 비교 표). 보고서 본문(docs/reports/schematic.md)은 이 표를 옮겨 쓴다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402


def main() -> int:
    s = json.loads((ROOT / "data" / "processed" / "schematic" / "summary.json").read_text(encoding="utf-8"))
    order = ["seoul", "busan", "daegu", "daejeon", "gwangju", "taipei"]
    L = ["| 권역 | 역/엣지 | 축약 keep | 엔진 | 상태 | 시간 | 반복 | 교차 제약 | 8방향 아님 | 교차 (지리) | 굴곡 (지리) | 변위 |",
         "| :- | :- | -: | :- | :- | -: | -: | -: | -: | :- | :- | -: |"]
    for k in order:
        r = s["regions"].get(k)
        if not r:
            continue
        st, sg = r["stats"], r["stats_geo"]
        L.append(f"| {r['city']} | {st['nodes']}/{st['edges']} | {r['keep_every']} | {r['engine']} | {r['status']} | {r['seconds']}s | {r['iterations']} | "
                 f"{r['crossing_constraints']} | {st['non_octilinear_edges']} | {st['crossings']} ({sg['crossings']}) | {st['bend_units_45deg']} ({sg['bend_units_45deg']}) | "
                 f"{st['mean_displacement_norm']} |")
    V = ["| 변형 | keep | w_bend / w_dir | 엔진 | 상태 | 시간 | 반복 | 8방향 아님 | 교차 | 굴곡 | 변위 |", "| :- | -: | :- | :- | :- | -: | -: | -: | -: | -: | -: |"]
    b = s["regions"].get("seoul")
    if b:
        V.append(f"| B 균형 (기본) | {b['keep_every']} | 1.0 / 2.0 | {b['engine']} | {b['status']} | {b['seconds']}s | {b['iterations']} | "
                 f"{b['stats']['non_octilinear_edges']} | {b['stats']['crossings']} | {b['stats']['bend_units_45deg']} | {b['stats']['mean_displacement_norm']} |")
    for v in s.get("seoul_variants", []):
        st = v.get("stats")
        p = v.get("params", {})
        if st:
            V.append(f"| {v['name']} | {v['keep_every']} | {p.get('w_bend')} / {p.get('w_dir')} | {v['engine']} | {v['status']} | {v['seconds']}s | {v['iterations']} | "
                     f"{st['non_octilinear_edges']} | {st['crossings']} | {st['bend_units_45deg']} | {st['mean_displacement_norm']} |")
        else:
            V.append(f"| {v['name']} | {v['keep_every']} | - | {v.get('engine')} | {v['status']} | {v['seconds']}s | - | - | - | - | - |")
    out = ROOT / "docs" / "reports" / "schematic" / "tables.md"
    out.write_text("## 권역\n\n" + "\n".join(L) + "\n\n## 수도권 변형\n\n" + "\n".join(V) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
