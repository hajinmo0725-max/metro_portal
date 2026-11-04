"""환승 클러스터, 포탈, 라우팅 그래프 (DESIGN 4·5장). 룰 값은 전부 ruleset에서 받는다."""
from __future__ import annotations

from collections import Counter, defaultdict

from .geo import haversine_m
from .normalize import normalize_name, parenthetical_aliases


class UnionFind:
    def __init__(self, items):
        self.p = {x: x for x in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # 결정성: 사전순 작은 쪽을 대표로
            if rb < ra:
                ra, rb = rb, ra
            self.p[rb] = ra


def station_match_names(st: dict, tier_cfg: dict, norm: dict) -> set[str]:
    """포탈 매칭에 쓰는 정규화 이름 집합 (ruleset의 언어·문자·종류·official 조건)."""
    out = set()
    for n in st.get("names", []):
        if n["lang"] not in tier_cfg["langs"]:
            continue
        if tier_cfg.get("scripts") and n["script"] not in tier_cfg["scripts"]:
            continue
        if tier_cfg.get("kinds") and n.get("kind", "primary") not in tier_cfg["kinds"]:
            continue
        if tier_cfg.get("official_only") and not n.get("official"):
            continue
        k = normalize_name(n["text"], norm)
        if k:
            out.add(k)
    return out


def build_clusters(stations: list[dict], rs: dict) -> list[dict]:
    """정규화 이름이 같고 거리 D 이하인 역을 묶는다. 옵션: 괄호 부역명 별칭도 같은 조건으로 묶는다."""
    norm, ccfg = rs["normalize"], rs["cluster"]
    D = ccfg["transfer_distance_m"]
    st = sorted(stations, key=lambda s: s["id"])
    key = {s["id"]: normalize_name(s["name_ko"], norm) for s in st}
    by_name = defaultdict(list)
    for s in st:
        by_name[key[s["id"]]].append(s)
    uf = UnionFind([s["id"] for s in st])
    reasons = []
    for name, group in sorted(by_name.items()):
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
                if d <= D:
                    uf.union(a["id"], b["id"])
    if ccfg.get("use_parenthetical_alias"):
        for a in st:
            for alias in parenthetical_aliases(a["name_ko"], norm):
                for b in by_name.get(alias, []):
                    if b["id"] == a["id"]:
                        continue
                    d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
                    if d <= D:
                        uf.union(a["id"], b["id"])
                        reasons.append((a["id"], b["id"], alias, round(d, 1)))
    members = defaultdict(list)
    for s in st:
        members[uf.find(s["id"])].append(s)
    raw = []
    for mem in members.values():
        names = Counter(key[s["id"]] for s in mem)
        primary = sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        lat = sum(s["lat"] for s in mem) / len(mem)
        lon = sum(s["lon"] for s in mem) / len(mem)
        raw.append({"name": primary, "names": sorted(names), "station_ids": sorted(s["id"] for s in mem),
                    "lat": round(lat, 6), "lon": round(lon, 6),
                    "regions": sorted({s.get("region", "") for s in mem}),
                    "lines": sorted({s.get("line_group", "") for s in mem})})
    # 결정적 id: 대표 이름 + 같은 이름 클러스터 내 (위도, 경도) 순번
    raw.sort(key=lambda c: (c["name"], c["lat"], c["lon"]))
    cnt = Counter()
    for c in raw:
        cnt[c["name"]] += 1
        c["id"] = f"{c['name']}#{cnt[c['name']]}"
    alias_links = [{"a": a, "b": b, "alias": al, "distance_m": d} for a, b, al, d in reasons]
    for c in raw:
        c["alias_links"] = [x for x in alias_links if x["a"] in c["station_ids"]]
    return raw


def build_portals(stations: list[dict], clusters: list[dict], rs: dict) -> tuple[list[dict], list[dict]]:
    """이름 노드(포탈). 같은 매칭 이름을 가진 클러스터가 2개 이상이면 포탈 하나. (포탈, 상한 초과로 버린 것)"""
    norm = rs["normalize"]
    cap = rs["portals"].get("hub_degree_cap")
    cluster_of = {sid: c["id"] for c in clusters for sid in c["station_ids"]}
    portals, capped = [], []
    for tier in sorted(k for k in rs["portals"] if k != "hub_degree_cap"):
        tcfg = rs["portals"][tier]
        if not tcfg.get("enabled"):
            continue
        by_name = defaultdict(lambda: defaultdict(list))
        for s in sorted(stations, key=lambda s: s["id"]):
            for nm in station_match_names(s, tcfg, norm):
                by_name[nm][cluster_of[s["id"]]].append(s["id"])
        for nm in sorted(by_name):
            cl = by_name[nm]
            if len(cl) < 2:
                continue
            p = {"id": f"P:{tier}:{nm}", "tier": tier, "name": nm, "cost": tcfg["cost"],
                 "cluster_ids": sorted(cl), "station_ids": sorted(sid for v in cl.values() for sid in v),
                 "degree": len(cl)}
            if cap is not None and p["degree"] > cap:
                capped.append(p)
                continue
            portals.append(p)
    return portals, capped


def build_graph(stations: list[dict], ride_edges: list[dict], clusters: list[dict], portals: list[dict], rs: dict) -> dict:
    """방향 그래프 인접 리스트. 노드 = 역(노선별) + 포탈. 엣지 = (to, cost, kind, meta)."""
    c_ride, c_transfer = rs["costs"]["ride"], rs["costs"]["transfer"]
    adj: dict[str, list] = {s["id"]: [] for s in stations}
    for e in ride_edges:
        adj[e["a"]].append((e["b"], c_ride, "ride", e["line"]))
        adj[e["b"]].append((e["a"], c_ride, "ride", e["line"]))
    for c in clusters:
        ids = c["station_ids"]
        for a in ids:
            for b in ids:
                if a != b:
                    adj[a].append((b, c_transfer, "transfer", c["id"]))
    for p in portals:
        adj[p["id"]] = []
        for sid in p["station_ids"]:
            adj[sid].append((p["id"], p["cost"], "warp_in", p["tier"]))
            adj[p["id"]].append((sid, 0, "warp_out", p["tier"]))
    for k in adj:
        adj[k].sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return adj
