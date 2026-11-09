#!/usr/bin/env python3
"""5차 R4: 도식 라벨 배치 전후 비교 → docs/reports/r4_labels.md, data/processed/schematic/label_compare.json

같은 도식 좌표(캐시)에서 4차 배치(origin/main의 place_labels: 라벨·역 원 겹침만 비용)와 5차 배치(노선 선분 클리핑 길이 비용 + 8방위 후보)를 비교한다.
지표: 선 위 라벨 = 라벨 사각형 안을 노선 선분이 2px 넘게 지나는 라벨 수, 겹침 쌍 = 외접 사각형이 0.5px 넘게 겹치는 라벨 쌍 수.
배율: 보고서 SVG(1100px)와, 웹 기본 확대(수도권 3배 = 3300px 상당, 글자 크기는 그대로)에서 각각 잰다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal import schematic as S  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base, load_multi  # noqa: E402

OLD_REV = "origin/main"


def old_place_labels():
    src = subprocess.run(["git", "show", f"{OLD_REV}:metro_portal/schematic.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    mod = types.ModuleType("schematic_v4")
    exec(compile(src, "schematic_v4", "exec"), mod.__dict__)
    return mod.place_labels


def as_geom(items, placed):
    """4차 배치 결과를 5차 라벨 기하(원점·회전·라벨 좌표계 사각형)로 바꿔 같은 지표로 잰다."""
    out = []
    for it, lp in zip(items, placed):
        w, h = len(it["text"]) * it["size"] * 0.95, it["size"] * 1.2
        r = (0, -h * 0.85, w, h * 0.15) if lp["anchor"] == "start" else (-w, -h * 0.85, 0, h * 0.15)
        c = {"ox": lp["x"], "oy": lp["y"], "rot": lp["rot"], "r": r}
        c["box"] = S.label_geom(c)
        out.append(c)
    return out


def main() -> int:
    cfg = yaml.safe_load(open(ROOT / "config" / "schematic.yaml", encoding="utf-8"))
    old_fn = old_place_labels()
    w_kr = build_world(*load_base(), load_ruleset(cfg["ruleset"]))
    w_tw = None
    rows = []
    for reg in cfg["regions"]:
        if reg["country"] == "TW":
            w_tw = w_tw or build_world(*load_multi(("KR", "TW")), load_ruleset("tw_t12"))
        g = S.region_graph(w_tw if reg["country"] == "TW" else w_kr, reg["city"])
        doc = json.loads((ROOT / "data" / "processed" / "schematic" / f"{reg['id']}.json").read_text(encoding="utf-8"))
        pos = {k: tuple(v) for k, v in doc["schematic"].items()}
        sizes = [1100] + ([3300] if reg["id"] == "seoul" else [])
        for size in sizes:
            res = {}
            for ver, fn in (("4차", lambda its, sg: old_fn(its)), ("5차", None)):
                st = {}
                S.render_svg(g, pos, "", size=size, label_fn=fn, stats_out=st)
                placed = st["_placed"] if ver == "5차" else as_geom([], [])
                if ver == "4차":
                    # render_svg가 만든 items를 다시 얻기 위해 같은 함수로 한 번 더 (결정적)
                    cap = {}
                    S.render_svg(g, pos, "", size=size, label_fn=lambda its, sg: cap.setdefault("its", its) and old_fn(its), stats_out=None)
                    placed = as_geom(cap["its"], st["_placed"])
                res[ver] = S.label_stats(placed, st["_segs"])
            rows.append({"region": reg["id"], "city": reg["city"], "size": size, **{f"{k}_{m}": v[m] for k, v in res.items() for m in ("labels", "on_line", "overlap_pairs")}})
            print(rows[-1], flush=True)
    (ROOT / "data" / "processed" / "schematic" / "label_compare.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    L = ["# R4 라벨 배치 전후 비교", "", "생성: `python3 scripts/label_compare.py`. 같은 도식 좌표(캐시)에서 4차 배치(라벨·역 원 겹침만 비용)와 "
         "5차 배치(+ 노선 선분이 라벨 안을 지나는 길이 × 0.45·글자 높이, 8방위 후보 추가)를 비교한다.", "",
         "- 선 위 라벨: 라벨 사각형 안을 노선 선분이 2px 넘게 지나는 라벨 수. 겹침 쌍: 라벨 외접 사각형끼리 0.5px 넘게 겹치는 쌍 수.",
         "- 1100px = 보고서 SVG 크기. 3300px = 웹 수도권 기본 확대(3배, 글자 크기 고정)와 같은 간격.", "",
         "| 권역 | 화면 폭 | 라벨 | 선 위 라벨 4차 → 5차 | 겹침 쌍 4차 → 5차 |", "| :- | -: | -: | :- | :- |"]
    for r in rows:
        L.append(f"| {r['city']} | {r['size']} | {r['5차_labels']} | {r['4차_on_line']} → **{r['5차_on_line']}** | {r['4차_overlap_pairs']} → **{r['5차_overlap_pairs']}** |")
    (ROOT / "docs" / "reports" / "r4_labels.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
