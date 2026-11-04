#!/usr/bin/env python3
"""M3·M4. 환승 클러스터, 포탈, 라우팅 그래프 빌드와 지표 출력.

입력: data/processed/kr/{stations,ride_edges}.json, config/rulesets/<ruleset>.yaml
출력: data/processed/kr/<ruleset>/{clusters,portals,graph}.json
      docs/reports/graph_<ruleset>.md (지표·포탈 목록)
사용: python3 pipeline/04_build_graph.py [--ruleset strict]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.graph import build_clusters, build_graph, build_portals  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402

PROC = ROOT / "data" / "processed" / "kr"


def load(name):
    return json.loads((PROC / name).read_text(encoding="utf-8"))


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruleset", default="strict")
    args = ap.parse_args()
    rs = load_ruleset(args.ruleset)
    stations = load("stations.json")["stations"]
    edges = load("ride_edges.json")["edges"]
    lines = load("lines.json")["lines"]

    clusters = build_clusters(stations, rs)
    portals, capped = build_portals(stations, clusters, rs)
    adj = build_graph(stations, edges, clusters, portals, rs)

    out = PROC / rs["name"]
    dump(out / "clusters.json", {"ruleset": rs["name"], "clusters": clusters})
    dump(out / "portals.json", {"ruleset": rs["name"], "portals": portals, "capped": capped})
    dump(out / "graph.json", {
        "ruleset": rs["name"], "costs": rs["costs"],
        "nodes": sorted(adj),
        "edges": [[a, b, c, k, m] for a in sorted(adj) for (b, c, k, m) in adj[a]],
    })
    print(f"[04] ruleset={rs['name']} stations={len(stations)} clusters={len(clusters)} "
          f"portals={len(portals)} capped={len(capped)}")

    try:
        from metro_portal.metrics import compute_metrics, render_report  # noqa: E402
    except ImportError:
        return 0
    m = compute_metrics(stations, edges, lines, clusters, portals, adj, rs)
    dump(out / "metrics.json", m)
    report = render_report(m, portals, clusters, stations, rs)
    (ROOT / "docs" / "reports" / f"graph_{rs['name']}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
