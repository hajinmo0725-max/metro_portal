"""OSM 추출본(.osm.pbf / .osm) route relation 파서 (pyosmium). 3차 A5·B1.

두 번 읽는다: 1) route relation과 정차 멤버 id, 2) 그 노드의 좌표·이름. 결과는 정차 순서가 보존된 리스트다.
"""
from __future__ import annotations

from pathlib import Path


def read_routes(path: Path | str, route_types: list[str], stop_roles: list[str]) -> list[dict]:
    import osmium

    class Rel(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.routes, self.need = [], set()

        def relation(self, r):
            tags = {t.k: t.v for t in r.tags}
            if tags.get("type") != "route" or tags.get("route") not in route_types:
                return
            stops = [m.ref for m in r.members if m.type == "n" and m.role in stop_roles]
            if not stops:  # 정차 노드가 없으면 플랫폼 노드로 대체
                stops = [m.ref for m in r.members if m.type == "n" and m.role.startswith("platform")]
            self.need.update(stops)
            self.routes.append({"id": r.id, "tags": tags, "stop_ids": stops})

    class Nodes(osmium.SimpleHandler):
        def __init__(self, need):
            super().__init__()
            self.need, self.nodes = need, {}

        def node(self, n):
            if n.id in self.need:
                self.nodes[n.id] = {"id": n.id, "lat": n.location.lat, "lon": n.location.lon, "tags": {t.k: t.v for t in n.tags}}

    rh = Rel()
    rh.apply_file(str(path))
    nh = Nodes(rh.need)
    nh.apply_file(str(path))
    out = []
    for r in sorted(rh.routes, key=lambda r: r["id"]):
        stops = [nh.nodes[i] for i in r["stop_ids"] if i in nh.nodes]
        out.append({"id": r["id"], "tags": r["tags"], "stops": stops, "missing_nodes": len(r["stop_ids"]) - len(stops)})
    return out


def stop_names(node: dict, keys: list[str]) -> list[str]:
    return [node["tags"][k] for k in keys if node["tags"].get(k)]
