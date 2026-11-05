"""게임·통계용 클러스터 수준 그래프 (클러스터 + 포탈 노드)와 탐색 함수. 환승 비용 0 ruleset 전제."""
from __future__ import annotations

import heapq
from collections import deque

from .geo import haversine_m

INF = float("inf")


class ClusterGraph:
    """클러스터 + 포탈 노드. 인덱스 0..C-1 = 클러스터, C.. = 포탈."""

    def __init__(self, w):
        rs = w["rs"]
        self.cl = sorted(w["clusters"], key=lambda c: c["id"])
        self.C = len(self.cl)
        self.ix = {c["id"]: i for i, c in enumerate(self.cl)}
        cof = {x: c["id"] for c in self.cl for x in c["station_ids"]}
        self.portals = sorted(w["portals"], key=lambda p: p["id"])
        self.P = len(self.portals)
        n = self.C + self.P
        ride = rs["costs"]["ride"]
        self.adj = [dict() for _ in range(n)]       # v -> cost
        self.ride_len = {}                           # (a,b) -> 구간 거리(m), a<b
        self.ride_lines = {}                         # (a,b) -> 노선 id 집합
        for e in w["edges"]:
            a, b = self.ix[cof[e["a"]]], self.ix[cof[e["b"]]]
            if a == b:
                continue
            self.adj[a][b] = ride
            self.adj[b][a] = ride
            k = (min(a, b), max(a, b))
            self.ride_len[k] = max(self.ride_len.get(k, 0.0), e["distance_m"])
            self.ride_lines.setdefault(k, set()).add(e["line"])
        for j, p in enumerate(self.portals):
            pn = self.C + j
            for cid in p["cluster_ids"]:
                c = self.ix[cid]
                self.adj[c][pn] = p["cost"]
                self.adj[pn][c] = 0
        self.adj = [sorted(d.items()) for d in self.adj]
        self.ride_adj = [[(v, c) for v, c in self.adj[u] if v < self.C] for u in range(self.C)]
        self.rev = [[] for _ in range(n)]
        for u in range(n):
            for v, c in self.adj[u]:
                self.rev[v].append((u, c))
        for lst in self.rev:
            lst.sort()

    def name(self, i):
        if i < self.C:
            c = self.cl[i]
            return f"{'/'.join(c['cities'])} {c['name']}"
        return f"[{self.portals[i - self.C]['name']}]"

    def sssp_count(self, s):
        """워프 포함 최단 비용과 최적 경로 개수. 0비용 엣지는 포탈→클러스터뿐이라 (비용, 포탈 먼저) 순서면 DAG 순서가 된다."""
        n = self.C + self.P
        dist = [INF] * n
        cnt = [0] * n
        warps = [0] * n  # 최적 경로의 워프 수 (최적해가 유일한 노드에서만 의미 있음)
        dist[s], cnt[s] = 0, 1
        pq = [(0, 1, s)]
        done = [False] * n
        while pq:
            d, _, u = heapq.heappop(pq)
            if done[u]:
                continue
            done[u] = True
            for v, c in self.adj[u]:
                nd = d + c
                if nd < dist[v]:
                    dist[v], cnt[v] = nd, cnt[u]
                    warps[v] = warps[u] + (1 if u >= self.C else 0)
                    heapq.heappush(pq, (nd, 0 if v >= self.C else 1, v))
                elif nd == dist[v]:
                    cnt[v] += cnt[u]
        self.last_warps = warps
        return dist, cnt

    def bfs_ride(self, s):
        dist = [INF] * self.C
        dist[s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for v, c in self.ride_adj[u]:
                if dist[u] + c < dist[v]:
                    dist[v] = dist[u] + c
                    q.append(v)
        return dist

    def unique_path(self, s, t, dist):
        """최적해가 유일할 때 t에서 거꾸로 따라가 경로 복원 (s에서 시작한 dist 사용)."""
        path = [t]
        while path[-1] != s:
            v = path[-1]
            path.append(next(u for u, c in self.rev[v] if dist[u] + c == dist[v]))
        return path[::-1]


def describe_path(g, path):
    """클러스터·포탈 노드열 → 단계 목록 (ride는 노선 묶음, warp는 포탈)."""
    steps = []
    i = 0
    while i < len(path) - 1:
        u, v = path[i], path[i + 1]
        if v >= g.C:  # warp: u -> portal -> w
            w = path[i + 2]
            steps.append({"type": "warp", "portal": g.portals[v - g.C]["name"], "from": g.cl[u]["id"], "to": g.cl[w]["id"]})
            i += 2
        else:
            k = (min(u, v), max(u, v))
            steps.append({"type": "ride", "from": g.cl[u]["id"], "to": g.cl[v]["id"], "lines": sorted(g.ride_lines[k])})
            i += 1
    return steps


def n_stops(g, N, K, allow_warp=True):
    """정확히 N턴 단순 경로(클러스터 재방문 금지) 전수 탐색."""
    C = g.C
    lat = [c["lat"] for c in g.cl]
    lon = [c["lon"] for c in g.cl]
    nb = []
    for u in range(C):
        lst = [(v, g.ride_len[(min(u, v), max(u, v))], False) for v, _ in g.ride_adj[u]]
        if allow_warp:
            for pn, _ in g.adj[u]:
                if pn >= C:
                    for w, _ in g.adj[pn]:
                        if w != u:
                            lst.append((w, 0.0, True))
        # 같은 목적지가 승차·워프 둘 다면 승차 우선 (구간 거리 합에 유리)
        best = {}
        for v, d, wp in lst:
            if v not in best or (best[v][2] and not wp):
                best[v] = (v, d, wp)
        nb.append(sorted(best.values()))
    best_gc, best_tr = {}, {}
    vis = [False] * C
    path = []
    nwarps = [0]

    def dfs(u, depth, track, s):
        if depth == N:
            k = (min(s, u), max(s, u))
            gc = haversine_m(lat[s], lon[s], lat[u], lon[u])
            if k not in best_gc or gc > best_gc[k][0] + 1e-9:
                best_gc[k] = (gc, list(path), nwarps[0])
            if k not in best_tr or track > best_tr[k][0] + 1e-9:
                best_tr[k] = (track, list(path), nwarps[0])
            return
        for v, d, wp in nb[u]:
            if not vis[v]:
                vis[v] = True
                path.append((v, wp))
                nwarps[0] += wp
                dfs(v, depth + 1, track + d, s)
                nwarps[0] -= wp
                path.pop()
                vis[v] = False

    for s in range(C):
        vis[s] = True
        path.append((s, False))
        dfs(s, 0, 0.0, s)
        path.pop()
        vis[s] = False

    def top(best):
        items = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[:K]
        res = []
        for (a, b), (val, p, nw) in items:
            res.append({"value_m": round(val), "start": g.cl[p[0][0]]["id"], "end": g.cl[p[-1][0]]["id"],
                        "start_label": g.name(p[0][0]), "end_label": g.name(p[-1][0]), "warps": nw,
                        "great_circle_m": round(haversine_m(lat[p[0][0]], lon[p[0][0]], lat[p[-1][0]], lon[p[-1][0]])),
                        "track_m": round(sum(g.ride_len[(min(x[0], y[0]), max(x[0], y[0]))] for x, y in zip(p, p[1:]) if not y[1])),
                        "path": [{"cluster": g.cl[v]["id"], "label": g.name(v), "via": "warp" if wp else ("start" if i == 0 else "ride")}
                                 for i, (v, wp) in enumerate(p)]})
        return res
    return {"great_circle": top(best_gc), "track": top(best_tr), "pairs_seen": len(best_gc)}
