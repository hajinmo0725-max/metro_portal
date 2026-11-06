#!/usr/bin/env python3
"""4차 S3·S5. 권역별 도식 노선도 (octilinear) 생성.

엔진: 자체 MIP (metro_portal/schematic.py, Nöllenburg & Wolff 2011식, HiGHS). LOOM은 이번 세션에서 받기·빌드가 막혀 대체했다.
공식 노선도·역 배치는 쓰지 않는다. 입력은 우리 그래프(클러스터 + 승차 엣지)와 지리 좌표, 노선 색뿐이다.

입력: config/schematic.yaml, data/processed/{kr,tw}
출력: data/processed/schematic/<region>.json (도식 좌표·지리 투영 좌표·엣지·지표), web/data/schematic.json (웹 번들),
      docs/reports/schematic/<region>.svg, 수도권 파라미터 비교 docs/reports/schematic/seoul_<variant>.svg,
      data/processed/schematic/summary.json
사용: python3 pipeline/20_build_schematic.py [--regions seoul,busan] [--skip-variants]
"""
from __future__ import annotations

import argparse
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

OUT = ROOT / "data" / "processed" / "schematic"
REP = ROOT / "docs" / "reports" / "schematic"


def run_region(w, reg, solver, log):
    g = S.region_graph(w, reg["city"])
    cfg = {**solver, **{k: v for k, v in reg.items() if k in solver}}
    cg = S.contract(g, keep_every=reg.get("keep_every", 2))
    t = time.time()
    log(f"[20] {reg['id']} ({reg['city']}): 역 {len(g['nodes'])}, 엣지 {len(g['edges'])} → 축약 {len(cg['nodes'])}/{len(cg['edges'])}")
    r = S.solve_octilinear(g, cg, cfg, log=log)
    if r["pos"]:
        pos = S.expand(g, cg, r["pos"])
        r["engine"] = "mip"
    elif reg.get("fallback", "snap-lp") == "snap-lp":
        # 시간 안에 MIP 실행 가능해를 못 찾음 → 방향 고정 LP 반복(snap-lp)으로 대체하고 표시 (octilinear·평면성 보장 없음)
        mip_status = r["status"]
        r = S.solve_snap_lp(g, cg, cfg, log=log)
        r["status"] = f"MIP: {mip_status} → snap-lp"
        pos = S.expand(g, cg, r["pos"])
        r["engine"] = "snap-lp"
    else:
        pos = dict(g["pos"])
        r["engine"] = "geo-fallback"
    st = S.layout_stats(g, pos)
    st_geo = S.layout_stats(g, g["pos"])
    sec = round(time.time() - t, 1)
    log(f"[20] {reg['id']}: {r['status']} {sec}s 반복 {r['iterations']} 교차제약 {r['crossing_constraints']} → {st}")
    return g, cg, pos, r, st, st_geo, sec, cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default=None)
    ap.add_argument("--skip-variants", action="store_true")
    ap.add_argument("--time-limit", type=float, default=None, help="모든 권역의 반복당 시간 제한 덮어쓰기 (빠른 시험용)")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "config" / "schematic.yaml", encoding="utf-8"))
    if a.time_limit:
        cfg["solver"]["time_limit_s"] = a.time_limit
        for r in cfg["regions"]:
            r.pop("time_limit_s", None)
    want = set(a.regions.split(",")) if a.regions else None
    OUT.mkdir(parents=True, exist_ok=True)
    REP.mkdir(parents=True, exist_ok=True)
    rs = load_ruleset(cfg["ruleset"])
    w_kr = build_world(*load_base(), rs)
    w_tw = None
    logs = []

    def log(m):
        logs.append(m)
        print(m, flush=True)
    summary = {"engine": "own octilinear MIP (Nöllenburg & Wolff 2011 style, HiGHS via highspy)", "solver": cfg["solver"], "regions": {}}
    web = {"regions": []}
    for reg in cfg["regions"]:
        if want and reg["id"] not in want:
            continue
        if reg["country"] == "TW":
            if w_tw is None:
                w_tw = build_world(*load_multi(("KR", "TW")), load_ruleset("tw_t12"))
            w = w_tw
        else:
            w = w_kr
        g, cg, pos, r, st, st_geo, sec, rcfg = run_region(w, reg, cfg["solver"], log)
        doc = {"region": reg["id"], "city": reg["city"], "country": reg["country"], "params": rcfg, "keep_every": reg.get("keep_every", 2),
               "engine": r["engine"], "status": r["status"], "seconds": sec, "iterations": r["iterations"], "crossing_constraints": r["crossing_constraints"],
               "objective": r["objective"], "stats": st, "stats_geo": st_geo,
               "schematic": {k: [round(v[0], 3), round(v[1], 3)] for k, v in sorted(pos.items())},
               "geo": {k: [round(g["pos"][k][0], 4), round(g["pos"][k][1], 4)] for k in sorted(pos)},
               "edges": [[a_, b_, ls] for (a_, b_), ls in g["edges"].items()],
               "lines": g["lines"], "names": g["names"], "kept": cg["nodes"]}
        (OUT / f"{reg['id']}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (REP / f"{reg['id']}.svg").write_text(S.render_svg(g, pos, f"{reg['city']} — 자동 도식 (octilinear MIP)", size=1100), encoding="utf-8")
        (REP / f"{reg['id']}_geo.svg").write_text(S.render_svg(g, g["pos"], f"{reg['city']} — 지리 좌표 (비교용)", size=1100), encoding="utf-8")
        summary["regions"][reg["id"]] = {k: doc[k] for k in ("city", "country", "keep_every", "engine", "status", "seconds", "iterations",
                                                             "crossing_constraints", "objective", "stats", "stats_geo")}
        note = {"mip": "", "snap-lp": f"{reg['city']}: MIP가 시간 제한 안에 해를 못 찾아 근사 배치(snap-lp)로 보여 준다. 일부 엣지는 8방향이 아니고 교차가 있다.",
                "geo-fallback": f"{reg['city']}: 시간 제한 안에 도식 해를 못 찾아 지리 좌표로 보여 준다."}[r["engine"]]
        if r["engine"] == "mip" and st["crossings"]:
            note = f"{reg['city']}: 시간 제한으로 평면성 제약을 다 못 넣어 교차 {st['crossings']}곳이 남았다."
        web["regions"].append({"id": reg["id"], "city": reg["city"], "country": reg["country"], "engine": r["engine"], "note": note,
                               "s": doc["schematic"], "g": doc["geo"], "e": doc["edges"], "lines": doc["lines"]})
    if not a.skip_variants and (not want or "seoul" in want):
        reg0 = next(r for r in cfg["regions"] if r["id"] == "seoul")
        summary["seoul_variants"] = []
        for v in cfg.get("seoul_variants", []):
            reg = {**reg0, **{k: x for k, x in v.items() if k != "name"}, "id": "seoul_" + v["name"].split()[0]}
            solver = {**cfg["solver"], **{k: x for k, x in v.items() if k in cfg["solver"]}}
            g, cg, pos, r, st, st_geo, sec, rcfg = run_region(w_kr, reg, solver, log)
            if r["engine"] != "mip":
                summary["seoul_variants"].append({"name": v["name"], "id": reg["id"], "keep_every": reg["keep_every"], "status": r["status"],
                                                  "seconds": sec, "engine": r["engine"]})
                continue
            (REP / f"{reg['id']}.svg").write_text(S.render_svg(g, pos, f"수도권 비교 {v['name']} (keep={reg['keep_every']}, bend={solver['w_bend']}, dir={solver['w_dir']})", size=1100), encoding="utf-8")
            summary["seoul_variants"].append({"name": v["name"], "id": reg["id"], "params": {k: rcfg[k] for k in ("w_bend", "w_dir")},
                                              "keep_every": reg["keep_every"], "status": r["status"], "seconds": sec, "engine": r["engine"],
                                              "iterations": r["iterations"], "stats": st})
    if want:   # 일부 권역만 다시 돌렸으면 기존 번들·요약과 합친다
        old = json.loads((ROOT / "web" / "data" / "schematic.json").read_text(encoding="utf-8")) if (ROOT / "web" / "data" / "schematic.json").exists() else {"regions": []}
        got = {r["id"] for r in web["regions"]}
        web["regions"] = [r for r in old["regions"] if r["id"] not in got] + web["regions"]
        olds = json.loads((OUT / "summary.json").read_text(encoding="utf-8")) if (OUT / "summary.json").exists() else {}
        for k, v in olds.get("regions", {}).items():
            summary["regions"].setdefault(k, v)
        if "seoul_variants" not in summary and "seoul_variants" in olds:
            summary["seoul_variants"] = olds["seoul_variants"]
    order = [r["id"] for r in cfg["regions"]]
    web["regions"].sort(key=lambda r: order.index(r["id"]))
    (ROOT / "web" / "data" / "schematic.json").write_text(json.dumps(web, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "build_log.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
