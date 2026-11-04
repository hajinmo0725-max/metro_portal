#!/usr/bin/env python3
"""M5. 워프 포함 길찾기 CLI.

입력: data/processed/kr/{stations,lines,ride_edges}.json, config/rulesets/<ruleset>.yaml
사용: python3 pipeline/05_route.py 목동 "부산 동래" [--ruleset strict] [--no-warp] [--json]
      python3 pipeline/05_route.py --examples   # config/report.yaml route_examples 실행 → docs/reports/route_examples.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.graph import build_clusters, build_graph, build_portals  # noqa: E402
from metro_portal.route import StationIndex, describe, shortest_path, summarize, without_warps  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402

PROC = ROOT / "data" / "processed" / "kr"


def load_world(ruleset: str):
    rs = load_ruleset(ruleset)
    stations = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]
    lines = json.loads((PROC / "lines.json").read_text(encoding="utf-8"))["lines"]
    edges = json.loads((PROC / "ride_edges.json").read_text(encoding="utf-8"))["edges"]
    city_of = {}
    for ln in lines:
        for sq in ln["sequences"]:
            for sid in sq["station_ids"]:
                city_of.setdefault(sid, ln.get("city", ""))
    group_city = {g: ln.get("city", "") for ln in lines for g in ln["pools"]}
    for s in stations:
        s["city"] = city_of.get(s["id"]) or group_city.get(s["line_group"], "")
    clusters = build_clusters(stations, rs)
    scity = {s["id"]: s["city"] for s in stations}
    for c in clusters:
        c["cities"] = sorted({scity[x] for x in c["station_ids"]})
    portals, _ = build_portals(stations, clusters, rs)
    adj = build_graph(stations, edges, clusters, portals, rs)
    idx = StationIndex(stations, clusters, rs["normalize"])
    return rs, idx, adj, {l["id"]: l for l in lines}, {p["id"]: p for p in portals}


def route(world, src_q, dst_q, warp=True):
    rs, idx, adj, lines_by_id, portals_by_id = world
    res = {"from": src_q, "to": dst_q, "warp": warp}
    src, dst = idx.resolve(src_q), idx.resolve(dst_q)
    for k, c in (("from", src), ("to", dst)):
        if not c:
            res["error"] = f"역을 찾지 못함: {res[k]}"
            return res
        if len(c) > 1:
            res["error"] = f"여러 역이 일치함 ({res[k]}): " + ", ".join(f"{x['id']}[{'/'.join(x['cities'])}]" for x in c) + " — 도시명을 앞에 붙여라 (예: '부산 동래')"
            return res
    g = adj if warp else without_warps(adj)
    r = shortest_path(g, src[0]["station_ids"], dst[0]["station_ids"])
    res["from_cluster"], res["to_cluster"] = src[0]["id"], dst[0]["id"]
    if r is None:
        res["reachable"] = False
        return res
    cost, path = r
    segs, text = describe(path, idx, lines_by_id, portals_by_id)
    res.update(reachable=True, cost=cost, **summarize(path), steps=text, path=[p[0] for p in path])
    return res


def fmt(res):
    head = f"{res['from']} → {res['to']} ({'워프 허용' if res['warp'] else '워프 없음'})"
    if "error" in res:
        return f"{head}\n  오류: {res['error']}"
    if not res["reachable"]:
        return f"{head}\n  연결 안 됨: {res['from_cluster']} 와 {res['to_cluster']} 는 같은 컴포넌트가 아니다"
    return "\n".join([f"{head}\n  총비용 {res['cost']} = 승차 {res['rides']}역 + 워프 {res['warps']}회 (환승 비용 0)"] + ["  " + t for t in res["steps"]])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--ruleset", default="strict")
    ap.add_argument("--no-warp", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--examples", action="store_true")
    a = ap.parse_args()
    world = load_world(a.ruleset)
    if a.examples:
        ex = yaml.safe_load(open(ROOT / "config" / "report.yaml", encoding="utf-8"))["route_examples"]
        L = [f"# 경로 예시 — ruleset `{a.ruleset}`", "", "생성: `python3 pipeline/05_route.py --examples`", ""]
        allres = []
        for s, d in ex:
            for warp in (True, False):
                r = route(world, s, d, warp)
                allres.append(r)
                L += ["```", fmt(r), "```", ""]
        (ROOT / "docs" / "reports" / f"route_examples_{a.ruleset}.md").write_text("\n".join(L), encoding="utf-8")
        print("\n".join(L))
        return 0
    if not (a.src and a.dst):
        ap.error("출발·도착 역을 지정하거나 --examples")
    r = route(world, a.src, a.dst, not a.no_warp)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else fmt(r))
    return 0 if r.get("reachable") else 1


if __name__ == "__main__":
    sys.exit(main())
