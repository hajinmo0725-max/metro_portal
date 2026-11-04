"""그래프 지표 (DESIGN 6장). 클러스터(물리적 역) 수준에서 계산한다."""
from __future__ import annotations

import heapq
from collections import Counter, defaultdict, deque


def cluster_graph(clusters, ride_edges, portals, rs, with_warp=True):
    """클러스터 수준 방향 그래프. 환승은 클러스터 내부라 비용 0으로 접힌다."""
    cof = {sid: c["id"] for c in clusters for sid in c["station_ids"]}
    adj = defaultdict(set)
    for c in clusters:
        adj[c["id"]]
    ride = rs["costs"]["ride"]
    for e in ride_edges:
        a, b = cof[e["a"]], cof[e["b"]]
        if a != b:
            adj[a].add((b, ride))
            adj[b].add((a, ride))
    if with_warp:
        for p in portals:
            for cid in p["cluster_ids"]:
                adj[cid].add((p["id"], p["cost"]))
                adj[p["id"]].add((cid, 0))
    return {k: sorted(v) for k, v in adj.items()}


def components(adj, nodes):
    seen, comps = set(), []
    und = defaultdict(set)
    for a, outs in adj.items():
        for b, _ in outs:
            und[a].add(b)
            und[b].add(a)
    for n in sorted(nodes):
        if n in seen:
            continue
        comp, q = [], deque([n])
        seen.add(n)
        while q:
            x = q.popleft()
            comp.append(x)
            for y in sorted(und[x]):
                if y not in seen:
                    seen.add(y)
                    q.append(y)
        comps.append(sorted(comp))
    comps.sort(key=lambda c: (-len(c), c[0]))
    return comps


def sssp(adj, src):
    """비용이 0/1뿐이면 0-1 BFS, 아니면 Dijkstra."""
    costs = {c for outs in adj.values() for _, c in outs}
    dist = {src: 0}
    if costs <= {0, 1}:
        dq = deque([src])
        while dq:
            x = dq.popleft()
            for y, c in adj.get(x, ()):
                nd = dist[x] + c
                if nd < dist.get(y, float("inf")):
                    dist[y] = nd
                    (dq.appendleft if c == 0 else dq.append)(y)
        return dist
    pq = [(0, src)]
    while pq:
        d, x = heapq.heappop(pq)
        if d > dist.get(x, float("inf")):
            continue
        for y, c in adj.get(x, ()):
            nd = d + c
            if nd < dist.get(y, float("inf")):
                dist[y] = nd
                heapq.heappush(pq, (nd, y))
    return dist


def diameter(adj, comp_clusters, exact_max, seed):
    """클러스터 쌍 최단 비용의 최댓값. 크면 double-sweep 근사."""
    import random
    nodes = sorted(comp_clusters)
    cset = set(nodes)
    if len(nodes) <= exact_max:
        best, total, pairs = (-1, None, None), 0, 0
        for s in nodes:
            d = sssp(adj, s)
            for t in nodes:
                if t in d and t != s:
                    total += d[t]
                    pairs += 1
                    if d[t] > best[0] or (d[t] == best[0] and (s, t) < (best[1], best[2])):
                        best = (d[t], s, t)
        return {"value": best[0], "from": best[1], "to": best[2], "exact": True,
                "mean_cost": round(total / pairs, 3) if pairs else 0}
    rnd = random.Random(seed)
    s = rnd.choice(nodes)
    best = (0, s, s)
    for _ in range(4):
        d = sssp(adj, s)
        t = max((n for n in d if n in cset), key=lambda n: (d[n], n))
        if d[t] > best[0]:
            best = (d[t], s, t)
        s = t
    return {"value": best[0], "from": best[1], "to": best[2], "exact": False, "mean_cost": None}


def compute_metrics(stations, ride_edges, lines, clusters, portals, adj_station, rs):
    mcfg = rs.get("metrics", {})
    cid = {c["id"]: c for c in clusters}
    cl_ids = [c["id"] for c in clusters]
    g_warp = cluster_graph(clusters, ride_edges, portals, rs, True)
    g_none = cluster_graph(clusters, ride_edges, portals, rs, False)

    def comp_summary(adj):
        comps = [[n for n in comp if n in cid] for comp in components(adj, set(adj))]
        comps = [c for c in comps if c]
        return comps

    cw, cn = comp_summary(g_warp), comp_summary(g_none)
    giant_w = set(cw[0])
    by_tier = Counter(p["tier"] for p in portals)

    def describe(comp):
        regions = Counter(r for c in comp for r in cid[c].get("cities") or cid[c]["regions"])
        lines_ = Counter(l for c in comp for l in cid[c]["lines"])
        return {"size": len(comp), "regions": dict(regions.most_common()), "lines": sorted(lines_),
                "sample": sorted(comp)[:8], "joins_giant_with_warp": bool(set(comp) & giant_w)}

    exact_max = mcfg.get("exact_diameter_max_nodes", 4000)
    seed = mcfg.get("random_seed", 42)
    return {
        "ruleset": rs["name"],
        "counts": {
            "stations": len(stations),
            "clusters": len(clusters),
            "lines": len(lines),
            "sequences": sum(len(l["sequences"]) for l in lines),
            "ride_edges": len(ride_edges),
            "transfer_clusters_multi": sum(1 for c in clusters if len(c["station_ids"]) > 1),
            "portals_total": len(portals),
            "portals_by_tier": dict(sorted(by_tier.items())),
            "portal_links": sum(p["degree"] for p in portals),
            "routing_nodes": len(adj_station),
            "routing_edges": sum(len(v) for v in adj_station.values()),
        },
        "with_warp": {
            "components": len(cw),
            "largest_component_ratio": round(len(cw[0]) / len(cl_ids), 4),
            "largest_component_size": len(cw[0]),
            "diameter": diameter(g_warp, cw[0], exact_max, seed),
        },
        "without_warp": {
            "components": len(cn),
            "largest_component_ratio": round(len(cn[0]) / len(cl_ids), 4),
            "largest_component_size": len(cn[0]),
            "diameter": diameter(g_none, cn[0], exact_max, seed),
            "component_list": [describe(c) for c in cn],
        },
        "top_portals": [{"name": p["name"], "tier": p["tier"], "degree": p["degree"],
                         "clusters": p["cluster_ids"]}
                        for p in sorted(portals, key=lambda p: (-p["degree"], p["name"]))[: mcfg.get("top_portals", 20)]],
        "isolated_without_warp": [describe(c) for c in cn[1:]],
    }


def render_report(m, portals, clusters, stations, rs, candidates=None):
    cid = {c["id"]: c for c in clusters}
    sid = {s["id"]: s for s in stations}
    c = m["counts"]
    L = [f"# 그래프 지표 — ruleset `{m['ruleset']}`", "",
         "생성: `python3 pipeline/04_build_graph.py --ruleset " + m["ruleset"] + "`. 지표는 클러스터(물리적 역) 수준.", "",
         "## 규모", "", "| 항목 | 값 |", "| :- | -: |",
         f"| 역 (노선별 역 레코드) | {c['stations']} |",
         f"| 환승 클러스터 (물리적 역) | {c['clusters']} |",
         f"| 2개 이상 레코드를 가진 환승 클러스터 | {c['transfer_clusters_multi']} |",
         f"| 노선 / 시퀀스 | {c['lines']} / {c['sequences']} |",
         f"| 승차 엣지 | {c['ride_edges']} |",
         f"| 포탈 (전체) | {c['portals_total']} |"]
    L += [f"| 포탈 {t} | {n} |" for t, n in c["portals_by_tier"].items()]
    L += [f"| 포탈-클러스터 연결 수 | {c['portal_links']} |",
          f"| 라우팅 그래프 노드 / 방향 엣지 | {c['routing_nodes']} / {c['routing_edges']} |", "",
          "## 연결성", "", "| | 워프 있음 | 워프 없음 |", "| :- | -: | -: |"]
    w, n = m["with_warp"], m["without_warp"]
    L += [f"| 연결 컴포넌트 수 | {w['components']} | {n['components']} |",
          f"| 최대 컴포넌트 비율 | {w['largest_component_ratio']:.1%} ({w['largest_component_size']}) | {n['largest_component_ratio']:.1%} ({n['largest_component_size']}) |",
          f"| 최대 컴포넌트 지름 (비용) | {w['diameter']['value']} ({'정확' if w['diameter']['exact'] else '근사'}) | {n['diameter']['value']} ({'정확' if n['diameter']['exact'] else '근사'}) |",
          f"| 지름 양 끝 | {w['diameter']['from']} ↔ {w['diameter']['to']} | {n['diameter']['from']} ↔ {n['diameter']['to']} |",
          f"| 최대 컴포넌트 평균 최단 비용 | {w['diameter']['mean_cost']} | {n['diameter']['mean_cost']} |", "",
          "워프 있음 지름은 최대 컴포넌트가 커져서(여러 도시 합류) 워프 없음 지름과 직접 비교하면 안 된다.", "",
          f"## 포탈 차수 상위 {len(m['top_portals'])}", "", "| 순위 | 포탈 | 등급 | 차수 | 연결 클러스터 |", "| -: | :- | :- | -: | :- |"]
    for i, p in enumerate(m["top_portals"], 1):
        L.append(f"| {i} | {p['name']} | {p['tier']} | {p['degree']} | {', '.join(_cl_label(cid[x]) for x in p['clusters'])} |")
    L += ["", "## 워프가 없으면 고립되는 컴포넌트", "",
          "워프 없는 그래프에서 최대 컴포넌트를 뺀 나머지. '워프로 합류' = 워프를 켜면 최대 컴포넌트에 붙는지.", "",
          f"최대 컴포넌트(워프 없음): {n['component_list'][0]['size']}개 클러스터, 지역 {n['component_list'][0]['regions']}", "",
          "| 크기 | 지역 | 노선 그룹 | 워프로 합류 |", "| -: | :- | :- | :- |"]
    for comp in m["isolated_without_warp"]:
        L.append(f"| {comp['size']} | {', '.join(f'{k}({v})' for k, v in comp['regions'].items())} | {', '.join(comp['lines'])} | {'예' if comp['joins_giant_with_warp'] else '아니오'} |")
    L += ["", "## 포탈 전체 목록", "", "| 포탈 | 등급 | 비용 | 차수 | 연결 역 (노선) |", "| :- | :- | -: | -: | :- |"]
    for p in sorted(portals, key=lambda p: (p["tier"], p["name"])):
        parts = []
        for cl in p["cluster_ids"]:
            mem = [sid[s] for s in p["station_ids"] if s in cid[cl]["station_ids"]]
            parts.append(f"{_city(mem[0])} " + "/".join(sorted({x['name_ko'] + '[' + x['line_name'] + ']' for x in mem})))
        L.append(f"| {p['name']} | {p['tier']} | {p['cost']} | {p['degree']} | {'; '.join(parts)} |")
    if candidates:
        L += _candidate_table(candidates, portals, clusters, stations, rs)
    return "\n".join(L) + "\n"


def _candidate_table(candidates, portals, clusters, stations, rs):
    from .normalize import normalize_name
    norm = rs["normalize"]
    pmap = {p["name"]: p for p in portals}
    cid = {c["id"]: c for c in clusters}
    nn = {s["id"]: normalize_name(s["name_ko"], norm) for s in stations}
    sid = {s["id"]: s for s in stations}
    L = ["", "## 포탈 후보 판정", "",
         "참 = 이 ruleset으로 T1 포탈이 실제로 생성됨. 정규화 이름 완전 일치만 인정하고 부분 일치는 제외한다.", "",
         "| 후보 | 판정 | 연결 클러스터 (도시: 역[노선]) | 같은 이름이지만 같은 클러스터(환승) | 부분 일치라 제외된 역 |",
         "| :- | :- | :- | :- | :- |"]
    for cand in candidates:
        key = normalize_name(cand, norm)
        same = sorted({c["id"] for c in clusters for x in c["station_ids"] if nn[x] == key})
        partial = sorted({sid[x]["name_ko"] for x in sid if key in nn[x] and nn[x] != key})
        p = pmap.get(key)
        if p:
            parts = []
            for cl in p["cluster_ids"]:
                mem = [sid[x] for x in p["station_ids"] if x in cid[cl]["station_ids"]]
                parts.append(f"{_city(mem[0])}: " + "/".join(sorted({m['name_ko'] + '[' + m['line_name'] + ']' for m in mem})))
            verdict = f"**참** (차수 {p['degree']})"
            conn = "; ".join(parts)
        else:
            verdict = "**거짓**"
            conn = "포탈 없음" if not same else f"클러스터 {len(same)}개뿐: {', '.join(same)}"
        multi = [c for c in same if len([x for x in cid[c]['station_ids'] if nn[x] == key]) > 1]
        transfer = ", ".join(f"{c}({len(cid[c]['station_ids'])}개 레코드)" for c in multi) or "-"
        L.append(f"| {cand} | {verdict} | {conn} | {transfer} | {', '.join(partial[:8]) or '-'}{' …' if len(partial) > 8 else ''} |")
    return L


REGION_SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
                "대전광역시": "대전", "울산광역시": "울산", "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원",
                "충청남도": "충남", "충청북도": "충북", "경상남도": "경남", "경상북도": "경북", "세종특별자치시": "세종"}


def _region_short(r):
    return REGION_SHORT.get(r, r or "?")


def _cl_label(c):
    return f"{c['id']}({'/'.join(_region_short(r) for r in (c.get('cities') or c['regions']))})"


def _city(st):
    return st.get("city") or _region_short(st.get("region", ""))
