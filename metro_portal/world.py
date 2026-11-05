"""ruleset 하나로 클러스터·포탈·라우팅 그래프를 한 번에 만든다 (04 단계와 같은 규칙). 비교·게임 데이터 단계에서 쓴다."""
from __future__ import annotations

import json

from . import ROOT
from .graph import build_clusters, build_graph, build_portals

PROC = ROOT / "data" / "processed" / "kr"


def load_base():
    ld = lambda n: json.loads((PROC / n).read_text(encoding="utf-8"))  # noqa: E731
    return ld("stations.json")["stations"], ld("ride_edges.json")["edges"], ld("lines.json")["lines"]


def assign_cities(stations, lines):
    """표시용 도시: 노선 정의의 city. 시퀀스에 없는 역은 노선 pool로 찾는다 (04와 같음)."""
    city_of = {}
    for ln in lines:
        for sq in ln["sequences"]:
            for sid in sq["station_ids"]:
                city_of.setdefault(sid, ln.get("city", ""))
    group_city = {g: ln.get("city", "") for ln in lines for g in ln["pools"]}
    for s in stations:
        s["city"] = city_of.get(s["id"]) or group_city.get(s["line_group"], "")


def build_world(stations, edges, lines, rs):
    assign_cities(stations, lines)
    clusters = build_clusters(stations, rs)
    scity = {s["id"]: s["city"] for s in stations}
    for c in clusters:
        c["cities"] = sorted({scity[x] for x in c["station_ids"]})
    portals, capped = build_portals(stations, clusters, rs)
    adj = build_graph(stations, edges, clusters, portals, rs)
    return {"stations": stations, "edges": edges, "lines": lines, "clusters": clusters,
            "portals": portals, "capped": capped, "adj": adj, "rs": rs}
