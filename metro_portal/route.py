"""워프 포함 길찾기 (DESIGN 5.4). 비용이 0/1뿐이면 0-1 BFS, 아니면 Dijkstra."""
from __future__ import annotations

import heapq
from collections import deque

from .normalize import normalize_name


def is_01(adj) -> bool:
    return all(c in (0, 1) for outs in adj.values() for _, c, _, _ in outs)


def shortest_path(adj, sources, targets, algorithm="auto"):
    """multi-source → multi-target 최단 경로. 반환: (cost, [(node, edge_kind, meta)...]) 또는 None.
    결정성: 인접 리스트가 정렬돼 있고, 같은 비용이면 먼저 확정된 경로를 유지한다."""
    targets = set(targets)
    if algorithm == "auto":
        algorithm = "01bfs" if is_01(adj) else "dijkstra"
    dist, prev = {}, {}
    for s in sorted(sources):
        dist[s] = 0
        prev[s] = None
    if algorithm == "01bfs":
        dq = deque(sorted(sources))
        done = set()
        while dq:
            x = dq.popleft()
            if x in done:
                continue
            done.add(x)
            if x in targets:
                return dist[x], _unwind(prev, x)
            for y, c, kind, meta in adj.get(x, ()):
                nd = dist[x] + c
                if nd < dist.get(y, float("inf")):
                    dist[y] = nd
                    prev[y] = (x, kind, meta)
                    (dq.appendleft if c == 0 else dq.append)(y)
        return None
    pq = [(0, i, s) for i, s in enumerate(sorted(sources))]
    heapq.heapify(pq)
    counter = len(pq)
    done = set()
    while pq:
        d, _, x = heapq.heappop(pq)
        if x in done:
            continue
        done.add(x)
        if x in targets:
            return d, _unwind(prev, x)
        for y, c, kind, meta in adj.get(x, ()):
            nd = d + c
            if nd < dist.get(y, float("inf")):
                dist[y] = nd
                prev[y] = (x, kind, meta)
                counter += 1
                heapq.heappush(pq, (nd, counter, y))
    return None


def _unwind(prev, x):
    out = []
    while prev[x] is not None:
        p, kind, meta = prev[x]
        out.append((x, kind, meta))
        x = p
    out.append((x, "start", None))
    return list(reversed(out))


def without_warps(adj):
    return {k: [e for e in v if e[2] not in ("warp_in", "warp_out")] for k, v in adj.items() if not k.startswith("P:")}


class StationIndex:
    def __init__(self, stations, clusters, norm):
        self.norm = norm
        self.st = {s["id"]: s for s in stations}
        self.clusters = clusters
        self.by_name = {}
        for c in clusters:
            for n in c["names"]:
                self.by_name.setdefault(n, []).append(c)

    def resolve(self, query: str):
        """'목동', '부산 동래', '광주 녹동' → 클러스터 후보 리스트. 앞 토큰이 도시명이면 그걸로 거른다."""
        q = query.strip()
        city = None
        parts = q.split()
        if len(parts) >= 2:
            city, q = parts[0], " ".join(parts[1:])
        key = normalize_name(q, self.norm)
        cands = self.by_name.get(key, [])
        if city:
            cands = [c for c in cands if any(city in x for x in c.get("cities", []) + c.get("regions", []))]
        return sorted(cands, key=lambda c: c["id"])

    @staticmethod
    def city_multi_ok(query: str, cands) -> bool:
        """도시 접두어가 있는 질의에서 후보가 여럿이고 모두 같은 도시면 전부를 출발/도착 후보로 써도 된다."""
        if len(query.split()) < 2 or len(cands) < 2:
            return False
        cities = {tuple(c.get("cities") or c.get("regions") or []) for c in cands}
        return len(cities) == 1


def describe(path, idx: StationIndex, lines_by_id, portals_by_id):
    """경로를 사람이 읽는 구간 목록으로 묶는다."""
    segs = []
    for i in range(1, len(path)):
        node, kind, meta = path[i]
        prev_node = path[i - 1][0]
        if kind == "ride":
            if segs and segs[-1]["type"] == "ride" and segs[-1]["line"] == meta:
                segs[-1]["stations"].append(node)
            else:
                segs.append({"type": "ride", "line": meta, "stations": [prev_node, node]})
        elif kind == "transfer":
            segs.append({"type": "transfer", "from": prev_node, "to": node})
        elif kind == "warp_in":
            segs.append({"type": "warp", "portal": node, "from": prev_node, "tier": meta})
        elif kind == "warp_out":
            segs[-1]["to"] = node
    # 환승 구간 정리: 탑승 사이의 연속 환승을 하나로
    out = []
    for s in segs:
        if s["type"] == "transfer" and out and out[-1]["type"] == "transfer":
            out[-1]["to"] = s["to"]
        else:
            out.append(s)
    text = []
    for s in out:
        if s["type"] == "ride":
            ln = lines_by_id.get(s["line"], {}).get("name", s["line"])
            names = [idx.st[x]["name_ko"] for x in s["stations"]]
            text.append(f"[{ln}] {names[0]} → {names[-1]} ({len(names) - 1}역)")
        elif s["type"] == "transfer":
            a, b = idx.st[s["from"]], idx.st[s["to"]]
            text.append(f"  환승: {a['name_ko']}({a['line_name']}) → {b['name_ko']}({b['line_name']})")
        elif s["type"] == "warp":
            p = portals_by_id[s["portal"]]
            a, b = idx.st[s["from"]], idx.st[s["to"]]
            text.append(f"  ⇢ 워프 {p['tier']} [{p['name']}]: {a.get('city') or a['region']} {a['name_ko']} ⇢ {b.get('city') or b['region']} {b['name_ko']}")
    return out, text


def summarize(path):
    rides = sum(1 for _, k, _ in path if k == "ride")
    warps = sum(1 for _, k, _ in path if k == "warp_in")
    return {"rides": rides, "warps": warps}
