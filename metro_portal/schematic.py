"""도식 노선도 (octilinear) 자동 생성. 4차 S5: Nöllenburg & Wolff (2011)식 혼합정수계획(MIP)을 HiGHS(highspy)로 푼다.

입력 그래프: 권역(도시) 하나의 클러스터(물리적 역) + 승차 엣지(노선 집합). 공식 노선도·역 배치는 쓰지 않고 지리 좌표에서만 만든다.

모델 (N&W 2011의 하드 제약 H1~H4 + 소프트 목표, 단순화한 부분은 주석):
- 차수 2 체인 축약: 차수 ≠ 2인 역(환승·종점·분기)과 체인 안에서 keep_every번째 역만 남기고 나머지는 축약한다. 축약된 역은 풀이 뒤
  그 구간(직선) 위에 같은 간격으로 다시 놓는다. (N&W는 체인 전체를 축약하지만 그러면 단일 노선 도시가 직선 하나가 돼서 굴곡을 남긴다)
- 변수: 정점 x, y (연속). 엣지마다 방향 이진변수 d[e, i], i는 지리 방향 섹터 s와 그 양옆 (s-1, s, s+1) 세 개 중 정확히 하나 (H2 상대 위치 보존).
- H1 octilinear: 방향 i가 선택되면 (y 같음 | x 같음 | x-y 같음 | x+y 같음) + 그 방향으로 최소 길이 이상 (빅M).
- H3 순환 순서 보존: 차수 ≥ 3 정점에서 인접 엣지의 방향 섹터가 지리적 반시계 순서대로 엄격히 증가 (한 번만 감아 돎, 이진 β).
- H4 평면성: 엣지 쌍 교차는 지연 제약(lazy)으로 — 풀고, 교차하는 비인접 엣지 쌍을 찾아 8방향 분리 제약(이진 γ, 하나 이상)을 더하고 다시 푼다.
- 목표: Σ 노선 굴곡(같은 노선이 정점에서 꺾인 정도, 0=직진·1=45°·2=90°·3=135°) × w_bend
        + Σ 지리 섹터 이탈(0/1) × w_dir + Σ 엣지 길이(L∞) × w_len.
결정적이다: 정점·엣지 순서는 id 정렬, 솔버는 단일 스레드·고정 시드.
"""
from __future__ import annotations

import math
from collections import defaultdict

# 8방향: 0=E, 1=NE, 2=N, 3=NW, 4=W, 5=SW, 6=S, 7=SE (y는 북쪽이 +)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def project(lat, lon, lat0, lon0):
    """국지 등장방형 투영 (km)."""
    kx = 111.32 * math.cos(math.radians(lat0))
    return ((lon - lon0) * kx, (lat - lat0) * 110.57)


def sector(dx, dy):
    a = math.degrees(math.atan2(dy, dx)) % 360
    return int(round(a / 45.0)) % 8


def region_graph(world: dict, city: str) -> dict:
    """권역 하나의 클러스터 그래프. 노드 = 그 도시 클러스터, 엣지 = 클러스터 사이 승차 엣지 (노선 id 집합, 무향으로 합침).
    여러 도시에 걸친 클러스터(경계 역)는 그 도시 목록에 city가 있으면 넣는다."""
    cl = {c["id"]: c for c in world["clusters"] if city in c.get("cities", [])}
    cof = {sid: c["id"] for c in world["clusters"] for sid in c["station_ids"]}
    lines = {ln["id"]: ln for ln in world["lines"]}
    edges = defaultdict(set)
    for e in world["edges"]:
        a, b = cof[e["a"]], cof[e["b"]]
        if a == b or a not in cl or b not in cl:
            continue
        edges[tuple(sorted((a, b)))].add(e["line"])
    # 노선별 클러스터 순서 (굴곡 계산용): 시퀀스를 클러스터열로
    seqs = []
    for ln in sorted(lines.values(), key=lambda l: l["id"]):
        for sq in ln["sequences"]:
            cs = []
            for sid in sq["station_ids"]:
                c = cof[sid]
                if c in cl and (not cs or cs[-1] != c):
                    cs.append(c)
                elif c not in cl and cs:
                    if len(cs) > 1:
                        seqs.append({"line": ln["id"], "nodes": cs, "circular": False})
                    cs = []
            if len(cs) > 1:
                seqs.append({"line": ln["id"], "nodes": cs, "circular": bool(sq.get("circular")) and cs[0] != cs[-1] and len(cs) == len(sq["station_ids"])})
    lat0 = sum(c["lat"] for c in cl.values()) / max(1, len(cl))
    lon0 = sum(c["lon"] for c in cl.values()) / max(1, len(cl))
    pos = {k: project(c["lat"], c["lon"], lat0, lon0) for k, c in cl.items()}
    return {"city": city, "nodes": sorted(cl), "pos": pos, "edges": {k: sorted(v) for k, v in sorted(edges.items())},
            "seqs": seqs, "lines": {k: {"name": v["name"], "color": v.get("color") or "#888"} for k, v in lines.items()
                                    if any(k in ls for ls in edges.values())},
            "names": {k: c["name"] for k, c in cl.items()}, "origin": (lat0, lon0)}


def contract(g: dict, keep_every: int = 3) -> dict:
    """차수 2 체인 축약. 반환: 축약 그래프 {nodes, edges: {(a,b): {"lines", "chain": [a, ..., b]}}}.
    keep_every: 체인 안에서 이 간격마다 역을 남긴다 (0이면 체인 전체 축약)."""
    adj = defaultdict(set)
    for a, b in g["edges"]:
        adj[a].add(b)
        adj[b].add(a)
    deg = {v: len(adj[v]) for v in g["nodes"]}
    keep = {v for v in g["nodes"] if deg[v] != 2}
    # 같은 두 정점을 잇는 두 체인(평행 체인)과 순환(모든 정점 차수 2)을 막으려면 체인마다 최소 하나는 더 남긴다
    seen_e = set()
    chains = []
    for s in sorted(keep) or sorted(g["nodes"])[:1]:
        keep.add(s)
        for nb in sorted(adj[s]):
            if (s, nb) in seen_e:
                continue
            ch = [s, nb]
            seen_e.add((s, nb))
            seen_e.add((nb, s))
            while ch[-1] not in keep:
                nxt = [w for w in sorted(adj[ch[-1]]) if w != ch[-2]]
                if not nxt:
                    break
                seen_e.add((ch[-1], nxt[0]))
                seen_e.add((nxt[0], ch[-1]))
                ch.append(nxt[0])
                if ch[-1] == s:
                    break
            chains.append(ch)
    out_e = {}
    kept = set(keep)
    for ch in chains:
        inner = ch[1:-1]
        marks = set()
        if keep_every and len(inner) >= keep_every:
            marks = {inner[i] for i in range(keep_every - 1, len(inner), keep_every)}
            if ch[0] == ch[-1] or len(inner) // keep_every < 1:
                marks.add(inner[len(inner) // 2])
        if ch[0] == ch[-1] and not marks:   # 순환: 최소 두 개
            marks = {inner[len(inner) // 3], inner[2 * len(inner) // 3]}
        kept |= marks
        cut = [ch[0]] + [v for v in inner if v in marks] + [ch[-1]]
        idx = {v: i for i, v in enumerate(ch)}
        for a, b in zip(cut, cut[1:]):
            sub = ch[idx[a]: idx[b] + 1] if idx[a] < idx[b] else ch[idx[b]: idx[a] + 1][::-1]
            key = tuple(sorted((a, b)))
            if key in out_e:   # 평행 체인: 가운데 역을 하나 더 남겨 쪼갠다
                mid = sub[len(sub) // 2]
                if mid in (a, b):
                    continue
                kept.add(mid)
                for x, y in ((a, mid), (mid, b)):
                    k2 = tuple(sorted((x, y)))
                    i1, i2 = sub.index(x), sub.index(y)
                    out_e[k2] = {"chain": sub[min(i1, i2): max(i1, i2) + 1] if sub.index(x) < sub.index(y) else sub[min(i1, i2): max(i1, i2) + 1],
                                 "lines": sorted(set().union(*[set(g["edges"][tuple(sorted(p))]) for p in zip(sub, sub[1:])]))}
                continue
            lines = sorted(set().union(*[set(g["edges"][tuple(sorted(p))]) for p in zip(sub, sub[1:])]))
            out_e[key] = {"chain": sub if sub[0] == key[0] else sub[::-1], "lines": lines}
    return {"nodes": sorted(kept), "edges": dict(sorted(out_e.items()))}


def segments_cross(p1, p2, p3, p4, eps=1e-6):
    """두 선분이 교차하거나 겹치는가 (끝점 공유는 호출하는 쪽에서 뺀다)."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < eps else (1 if v > 0 else -1)

    def on_seg(a, b, c):
        return min(a[0], b[0]) - eps <= c[0] <= max(a[0], b[0]) + eps and min(a[1], b[1]) - eps <= c[1] <= max(a[1], b[1]) + eps
    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    if o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4):
        return True
    return (o1 == 0 and on_seg(p1, p2, p3)) or (o2 == 0 and on_seg(p1, p2, p4)) or (o3 == 0 and on_seg(p3, p4, p1)) or (o4 == 0 and on_seg(p3, p4, p2))


def point_seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * vx + (p[1] - ay) * vy) / L2))
    return math.hypot(p[0] - ax - t * vx, p[1] - ay - t * vy)


def solve_octilinear(g: dict, cg: dict, cfg: dict, log=None) -> dict:
    """축약 그래프 cg를 octilinear로 배치한다. 반환 {pos: {node: (x, y)}, status, iterations, crossings_added, objective}."""
    import highspy
    import numpy as np  # noqa: F401  (highspy 의존)

    nodes = cg["nodes"]
    E = list(cg["edges"].keys())
    P = g["pos"]
    # 지리 좌표를 격자 단위로 스케일: 평균 엣지 길이를 grid_edge 칸으로
    lens = sorted(math.dist(P[a], P[b]) for a, b in E)
    # 격자 스케일 기준: 평균(기본) 또는 중앙값(scale_by: median — 축약으로 긴 교외 엣지가 평균을 끌어올리는 큰 권역용)
    mean_len = (lens[len(lens) // 2] if cfg.get("scale_by") == "median" else sum(lens) / max(1, len(lens))) if lens else 0
    scale = cfg["grid_edge"] / mean_len if mean_len else 1.0
    G = {v: (P[v][0] * scale, P[v][1] * scale) for v in nodes}
    span = (max(max(abs(p[0]) for p in G.values()), max(abs(p[1]) for p in G.values())) * 2 + 10 * cfg["grid_edge"]) * cfg.get("span_factor", 1.0)
    M0 = M = span * 4
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("threads", 1)
    h.setOptionValue("random_seed", 7)
    h.setOptionValue("time_limit", float(cfg["time_limit_s"]))
    h.setOptionValue("mip_rel_gap", float(cfg.get("mip_rel_gap", 0.02)))
    if cfg.get("mip_heuristic_effort"):
        h.setOptionValue("mip_heuristic_effort", float(cfg["mip_heuristic_effort"]))
    inf = highspy.kHighsInf

    def var(lb, ub, cost=0.0, integer=False):
        h.addVar(lb, ub)
        j = h.getNumCol() - 1
        if cost:
            h.changeColCost(j, cost)
        if integer:
            h.changeColIntegrality(j, highspy.HighsVarType.kInteger)
        return j

    def row(coefs, lo, hi):
        idx = [j for j, _ in coefs]
        val = [c for _, c in coefs]
        h.addRow(lo, hi, len(idx), idx, val)

    # 선택: 좌표를 지리 위치 ± pos_window(전체 폭 비율) 창으로 묶어 LP 완화를 조인다 (큰 권역용, N&W에는 없는 단순화)
    R = cfg.get("pos_window")
    if R:
        R = R * span
        X = {v: var(G[v][0] - R, G[v][0] + R) for v in nodes}
        Y = {v: var(G[v][1] - R, G[v][1] + R) for v in nodes}
    else:
        X = {v: var(-span, span) for v in nodes}
        Y = {v: var(-span, span) for v in nodes}
    D = {}
    sec = {}
    KS = {}

    def choices(pa, pb, s, n):
        """허용 방향 오프셋: 3이면 (-1, 0, 1), 2이면 지리 각도에 더 가까운 이웃 섹터와 s"""
        if n >= 3:
            return (-1, 0, 1)
        ang = math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0])) % 360
        diff = (ang - 45 * s + 540) % 360 - 180
        return (0, 1) if diff >= 0 else (-1, 0)
    for e in E:
        a, b = e
        s = sector(G[b][0] - G[a][0], G[b][1] - G[a][1])
        sec[e] = s
        if cfg.get("allowed") and e in cfg["allowed"]:
            dirs_e = sorted(set(cfg["allowed"][e]))          # fix-and-optimize: 바깥에서 정한 방향 후보
        else:
            dirs_e = sorted({(s + k) % 8 for k in choices(G[a], G[b], s, cfg.get("dir_choices", 3))})
        KS[e] = dirs_e
        for i in dirs_e:
            dist8 = min((i - s) % 8, (s - i) % 8)
            D[e, i] = var(0, 1, cfg["w_dir"] * dist8, integer=True)
        row([(D[e, i], 1) for i in dirs_e], 1, 1)
        # 최소 길이: 축약한 원래 엣지 수에 비례
        n_orig = len(cg["edges"][e]["chain"]) - 1
        lmin = cfg["min_edge"] * (1 + cfg.get("chain_len_factor", 0.6) * (n_orig - 1))
        # 선택: 지리 길이 비례 하한 (긴 교외 구간이 최소 길이로 쪼그라들어 노선 끝이 뭉치는 걸 막는다, LOOM geo-pen과 비슷한 의도)
        if cfg.get("geo_len_factor"):
            lmin = max(lmin, cfg["geo_len_factor"] * max(abs(G[b][0] - G[a][0]), abs(G[b][1] - G[a][1])))
        # 엣지별 빅M: 좌표 창이 있으면 두 끝점의 가능한 최대 차이로 조인다 (LP 완화 강화)
        M = Me = (max(abs(G[b][0] - G[a][0]), abs(G[b][1] - G[a][1])) * 2 + 4 * R + 2 * lmin) if R else M0
        for i in dirs_e:
            dx, dy = DIRS[i]
            d = D[e, i]
            # 방향 직교 성분 = 0 (빅M), 진행 성분 ≥ lmin
            if dy == 0:      # E/W: y 같음
                row([(Y[b], 1), (Y[a], -1), (d, M)], -inf, M)
                row([(Y[b], 1), (Y[a], -1), (d, -M)], -M, inf)
            elif dx == 0:    # N/S: x 같음
                row([(X[b], 1), (X[a], -1), (d, M)], -inf, M)
                row([(X[b], 1), (X[a], -1), (d, -M)], -M, inf)
            elif dx == dy:   # NE/SW: x - y 같음
                row([(X[b], 1), (X[a], -1), (Y[b], -1), (Y[a], 1), (d, M)], -inf, M)
                row([(X[b], 1), (X[a], -1), (Y[b], -1), (Y[a], 1), (d, -M)], -M, inf)
            else:            # NW/SE: x + y 같음
                row([(X[b], 1), (X[a], -1), (Y[b], 1), (Y[a], -1), (d, M)], -inf, M)
                row([(X[b], 1), (X[a], -1), (Y[b], 1), (Y[a], -1), (d, -M)], -M, inf)
            # 진행 성분: dx != 0이면 dx*(xb-xa) ≥ lmin, 아니면 dy*(yb-ya) ≥ lmin
            if dx != 0:
                row([(X[b], dx), (X[a], -dx), (d, -M)], lmin - M, inf)
            else:
                row([(Y[b], dy), (Y[a], -dy), (d, -M)], lmin - M, inf)
        # 길이 비용 (L∞ 근사): len ≥ ±dx, ±dy
        Lv = var(0, inf, cfg["w_len"])
        for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            coefs = [(Lv, 1)]
            if sx:
                coefs += [(X[b], -sx), (X[a], sx)]
            else:
                coefs += [(Y[b], -sy), (Y[a], sy)]
            row(coefs, 0, inf)

    def theta_terms(v, e):
        """정점 v에서 본 엣지 e의 방향 섹터 (0..7) = Σ i·d."""
        a, b = e
        out = []
        for i in KS[e]:
            t = i if v == a else (i + 4) % 8
            out.append((D[e, i], t))
        return out

    # H3 순환 순서
    inc = defaultdict(list)
    for e in E:
        inc[e[0]].append(e)
        inc[e[1]].append(e)
    for v in nodes:
        es = inc[v]
        if len(es) < 2 or cfg.get("order") == "none":
            continue
        if len(es) > 8:
            raise ValueError(f"차수 > 8 정점: {v}")
        ang = []
        for e in es:
            o = e[1] if e[0] == v else e[0]
            ang.append((math.atan2(G[o][1] - G[v][1], G[o][0] - G[v][0]) % (2 * math.pi), e))
        ang.sort()
        order = [e for _, e in ang]
        if len(order) == 2:
            # 두 엣지가 같은 방향이면 겹친다 → 방향이 달라야 함 (|θ1-θ2| ≥ 1, 순환)
            pass
        betas = [var(0, 1, integer=True) for _ in order]
        row([(bj, 1) for bj in betas], 1, 1)
        for j, e in enumerate(order):
            f = order[(j + 1) % len(order)]
            # θ_f ≥ θ_e + 1 - 8 β_j  (order = soft이면 여유 변수에 벌점: 큰 권역에서 첫 실행 가능해를 빨리 찾게)
            extra = [(var(0, 8, cfg.get("w_order", 20.0)), 1)] if cfg.get("order", "hard") == "soft" else []
            row(theta_terms(v, f) + [(c, -t) for c, t in theta_terms(v, e)] + [(betas[j], 8)] + extra, 1, inf)

    # 굴곡: 노선 시퀀스에서 연속한 축약 엣지 쌍 (a-v-b)
    pairs = defaultdict(int)
    node_set = set(nodes)
    for sq in g["seqs"]:
        ks = [x for x in sq["nodes"] if x in node_set]
        seq_pairs = list(zip(ks, ks[1:], ks[2:]))
        if sq.get("circular") and len(ks) > 3:
            seq_pairs += [(ks[-2], ks[-1], ks[0]), (ks[-1], ks[0], ks[1])]
        for a, v, b in seq_pairs:
            e1, e2 = tuple(sorted((a, v))), tuple(sorted((v, b)))
            if e1 in cg["edges"] and e2 in cg["edges"] and e1 != e2:
                pairs[(v, e1, e2) if e1 < e2 else (v, e2, e1)] += 1
    for (v, e1, e2), w in sorted(pairs.items()):
        # 굴곡 dev = 두 엣지 방향 조합(각 3개 이하)마다 상수 → dev ≥ c·(d1 + d2 - 1) (정수변수 없이 선형화)
        dev = var(0, 4, cfg["w_bend"] * w)
        for c1, t1 in theta_terms(v, e1):
            for c2, t2 in theta_terms(v, e2):
                dvt = (t2 - t1 - 4) % 8
                cst = min(dvt, 8 - dvt)
                if cst:
                    row([(dev, 1), (c1, -cst), (c2, -cst)], -cst, inf)

    # 시작 해: 지리 좌표 근처로 끌어당기는 약한 앵커 (중심 고정) — 평행이동 자유도 제거
    v0 = nodes[0]
    row([(X[v0], 1)], G[v0][0], G[v0][0])
    row([(Y[v0], 1)], G[v0][1], G[v0][1])

    # 지리 좌표에서 이미 교차하는 엣지 쌍 (역 없이 입체 교차하는 실제 노선)은 평면성 제약에서 뺀다
    # (N&W는 교차점에 가상 정점을 넣어 평면화하지만, 여기서는 그 쌍의 교차를 허용하는 쪽으로 단순화)
    geo_cross = set()
    for i in range(len(E)):
        a, b = E[i]
        for j in range(i + 1, len(E)):
            c, d = E[j]
            if len({a, b, c, d}) == 4 and segments_cross(G[a], G[b], G[c], G[d]):
                geo_cross.add((E[i], E[j]))
    added = set()
    it = 0
    status = None
    last_ok = (0, "")
    pos = {}
    while True:
        it += 1
        h.run()
        status = h.modelStatusToString(h.getModelStatus())
        sol = h.getSolution().col_value
        if not sol or len(sol) < h.getNumCol() or h.getInfo().primal_solution_status != 2:
            # 실행 가능해 없음 (시간 제한 안에 못 찾음 등). 앞 반복의 해가 있으면 그걸 남긴다
            if log:
                log(f"    iter {it}: {status} (실행 가능해 없음)")
            status = (f"반복 {last_ok[0]} 해 사용 ({last_ok[1]}; 반복 {it}은 {status}, 해 없음)" if pos
                      else f"{status} (실행 가능해 없음)")
            break
        last_ok = (it, status)
        pos = {v: (sol[X[v]], sol[Y[v]]) for v in nodes}
        # 교차 검사 (비인접 엣지 쌍) + 정점-엣지 근접
        cross = []
        for i in range(len(E)):
            a, b = E[i]
            for j in range(i + 1, len(E)):
                c, d = E[j]
                if len({a, b, c, d}) < 4:
                    continue
                key = (E[i], E[j])
                if key in added or key in geo_cross:
                    continue
                if segments_cross(pos[a], pos[b], pos[c], pos[d]) or min(
                        point_seg_dist(pos[c], pos[a], pos[b]), point_seg_dist(pos[d], pos[a], pos[b]),
                        point_seg_dist(pos[a], pos[c], pos[d]), point_seg_dist(pos[b], pos[c], pos[d])) < cfg["min_sep"] * 0.99:
                    cross.append(key)
        if log:
            log(f"    iter {it}: {status}, obj={h.getInfo().objective_function_value:.2f}, 위반 쌍 {len(cross)}")
        if not cross or it >= cfg["max_iterations"]:
            break
        for e1, e2 in cross:
            added.add((e1, e2))
            a, b = e1
            c, d = e2
            gam = [var(0, 1, integer=True) for _ in range(8)]
            row([(gj, 1) for gj in gam], 1, inf)
            dm = cfg["min_sep"]
            # 방향 k: e2의 두 끝점이 e1의 두 끝점보다 방향 k 쪽으로 dm 이상 (k의 단위벡터와 내적)
            for k, (ux, uy) in enumerate(DIRS):
                for p in (c, d):
                    for q in (a, b):
                        Mx = (abs(G[p][0] - G[q][0]) + abs(G[p][1] - G[q][1]) + 4 * R + 2 * dm) if R else M0
                        row([(X[p], ux), (Y[p], uy), (X[q], -ux), (Y[q], -uy), (gam[k], -Mx)], dm - Mx, inf)
    obj = h.getInfo().objective_function_value if pos else None
    # 결과 통계
    bends = 0
    for (v, e1, e2), w in (pairs.items() if pos else []):
        def th(e):
            o = e[1] if e[0] == v else e[0]
            return sector(pos[o][0] - pos[v][0], pos[o][1] - pos[v][1])
        dvt = (th(e2) - th(e1) - 4) % 8
        bends += w * min(dvt, 8 - dvt)
    chosen = {}
    if pos:
        sol = h.getSolution().col_value
        for e in E:
            chosen[e] = max(KS[e], key=lambda i: sol[D[e, i]])
    return {"pos": pos, "status": status, "iterations": it, "crossing_constraints": len(added), "objective": obj,
            "scale": scale, "bend_cost": bends, "geo_crossing_pairs": len(geo_cross), "dirs": chosen}


def expand(g: dict, cg: dict, pos: dict) -> dict:
    """축약된 역을 구간 위에 같은 간격으로 다시 놓는다."""
    out = dict(pos)
    for (a, b), info in cg["edges"].items():
        ch = info["chain"]
        if ch[0] != a:
            ch = ch[::-1]
        n = len(ch) - 1
        for i, v in enumerate(ch[1:-1], 1):
            t = i / n
            out[v] = (pos[a][0] + (pos[b][0] - pos[a][0]) * t, pos[a][1] + (pos[b][1] - pos[a][1]) * t)
    return out


def layout_stats(g: dict, pos: dict) -> dict:
    """도식 품질 지표: octilinear 아닌 엣지, 비인접 엣지 교차, 노선 굴곡(45° 단위 합), 지리 대비 평균 변위(정규화, Procrustes 없이 스케일만)."""
    E = list(g["edges"].keys())
    non_oct = 0
    for a, b in E:
        dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
        if not (abs(dx) < 1e-6 or abs(dy) < 1e-6 or abs(abs(dx) - abs(dy)) < 1e-6):
            non_oct += 1
    crossings = 0
    for i in range(len(E)):
        a, b = E[i]
        for j in range(i + 1, len(E)):
            c, d = E[j]
            if len({a, b, c, d}) == 4 and segments_cross(pos[a], pos[b], pos[c], pos[d]):
                crossings += 1
    bends = 0
    for sq in g["seqs"]:
        ks = sq["nodes"]
        for a, v, b in zip(ks, ks[1:], ks[2:]):
            t1 = math.atan2(pos[a][1] - pos[v][1], pos[a][0] - pos[v][0])
            t2 = math.atan2(pos[b][1] - pos[v][1], pos[b][0] - pos[v][0])
            ang = abs((math.degrees(t2 - t1) + 360) % 360 - 180)   # 0 = 직진
            bends += round(ang / 45.0)
    # 변위: 두 좌표계를 각각 중심 0, RMS 1로 정규화한 뒤 평균 거리
    def norm(P):
        vs = list(P.values())
        cx = sum(p[0] for p in vs) / len(vs)
        cy = sum(p[1] for p in vs) / len(vs)
        r = math.sqrt(sum((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in vs) / len(vs)) or 1
        return {k: ((p[0] - cx) / r, (p[1] - cy) / r) for k, p in P.items()}
    A, B = norm({k: g["pos"][k] for k in pos}), norm(pos)
    disp = sum(math.dist(A[k], B[k]) for k in pos) / len(pos)
    return {"nodes": len(pos), "edges": len(E), "non_octilinear_edges": non_oct, "crossings": crossings,
            "bend_units_45deg": bends, "mean_displacement_norm": round(disp, 3)}


def snap_baseline(g: dict) -> dict:
    """비교용 단순 기준선: 지리 좌표를 그대로 두고 엣지마다 가장 가까운 8방향으로 '보이게만' 한 것은 좌표가 안 맞으므로,
    대신 지리 좌표 자체(정규화)를 기준선으로 쓴다 (octilinear 아님)."""
    return dict(g["pos"])


def render_svg(g: dict, pos: dict, title: str, size=900, label=True) -> str:
    """도식 SVG (노선 색만 사용). 같은 엣지를 여러 노선이 지나면 평행 오프셋."""
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = max(maxx - minx, 1e-6)
    hgt = max(maxy - miny, 1e-6)
    pad = 60
    sc = (size - 2 * pad) / max(w, hgt)
    W, H = w * sc + 2 * pad, hgt * sc + 2 * pad

    def tr(p):
        return (pad + (p[0] - minx) * sc, pad + (maxy - p[1]) * sc)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" font-family="sans-serif">',
           f'<rect width="100%" height="100%" fill="#fff"/><text x="12" y="24" font-size="16" font-weight="700">{title}</text>']
    for (a, b), ls in g["edges"].items():
        if a not in pos or b not in pos:
            continue
        pa, pb = tr(pos[a]), tr(pos[b])
        n = len(ls)
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        for k, lid in enumerate(ls):
            off = (k - (n - 1) / 2) * 4.5
            col = g["lines"].get(lid, {}).get("color", "#888")
            out.append(f'<line x1="{pa[0] + nx * off:.1f}" y1="{pa[1] + ny * off:.1f}" x2="{pb[0] + nx * off:.1f}" y2="{pb[1] + ny * off:.1f}" '
                       f'stroke="{col}" stroke-width="4" stroke-linecap="round"/>')
    deg = defaultdict(int)
    nbr = defaultdict(list)
    for a, b in g["edges"]:
        if a in pos and b in pos:
            deg[a] += 1
            deg[b] += 1
            nbr[a].append(b)
            nbr[b].append(a)
    items = []
    for v, p in sorted(pos.items()):
        x, y = tr(p)
        big = deg[v] != 2
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 if big else 3}" fill="#fff" stroke="#222" stroke-width="{2 if big else 1.2}"/>')
        vx = vy = 0.0
        for o in nbr[v]:
            q = tr(pos[o])
            dx, dy = q[0] - x, q[1] - y
            L = math.hypot(dx, dy) or 1
            if dx < -1e-6 or (abs(dx) <= 1e-6 and dy < 0):
                dx, dy = -dx, -dy
            vx, vy = vx + dx / L, vy + dy / L
        L = math.hypot(vx, vy) or 1
        items.append({"p": (x, y), "dir": (vx / L, vy / L), "text": g["names"][v], "size": 11 if big else 9, "big": big})
    if label:
        for it, lp in zip(items, place_labels(items)):
            tf = f' transform="rotate({lp["rot"]} {lp["x"]:.1f} {lp["y"]:.1f})"' if lp["rot"] else ""
            out.append(f'<text x="{lp["x"]:.1f}" y="{lp["y"]:.1f}" font-size="{it["size"]}" fill="#333" text-anchor="{lp["anchor"]}"'
                       f' paint-order="stroke" stroke="#fff" stroke-width="2.5"{tf}>{it["text"]}</text>')
    out.append("</svg>")
    return "\n".join(out)


def solve_snap_lp(g: dict, cg: dict, cfg: dict, log=None, rounds: int = 6) -> dict:
    """큰 권역용 대비 엔진 (MIP가 시간 안에 해를 못 찾을 때): 방향을 고정한 LP를 반복한다.
    1) 엣지 방향 = 지리 방향에 가장 가까운 8방향. 2) LP: octilinear 잔차(직교 성분) |r| 최소 + 진행 성분 ≥ 최소 길이(어기면 큰 벌점)
       + 지리 위치 앵커(작은 가중치). 3) 잔차가 남은 엣지는 이웃 방향 중 잔차가 줄어드는 쪽으로 바꿔 다시 푼다.
    순환 순서·평면성은 보장하지 않는다 (지표로 보고)."""
    import highspy

    nodes = cg["nodes"]
    E = list(cg["edges"].keys())
    P = g["pos"]
    mean_len = sum(math.dist(P[a], P[b]) for a, b in E) / max(1, len(E))
    scale = cfg["grid_edge"] / mean_len if mean_len else 1.0
    G = {v: (P[v][0] * scale, P[v][1] * scale) for v in nodes}
    dirs = {e: sector(G[e[1]][0] - G[e[0]][0], G[e[1]][1] - G[e[0]][1]) for e in E}
    pos = {}
    for rd in range(rounds):
        h = highspy.Highs()
        h.setOptionValue("output_flag", False)
        h.setOptionValue("threads", 1)
        inf = highspy.kHighsInf

        def var(lb, ub, cost=0.0):
            h.addVar(lb, ub)
            j = h.getNumCol() - 1
            if cost:
                h.changeColCost(j, cost)
            return j

        def row(coefs, lo, hi):
            h.addRow(lo, hi, len(coefs), [j for j, _ in coefs], [c for _, c in coefs])
        X = {v: var(-inf, inf) for v in nodes}
        Y = {v: var(-inf, inf) for v in nodes}
        for v in nodes:   # 지리 앵커 |x - Gx| + |y - Gy|
            for C, gv in ((X[v], G[v][0]), (Y[v], G[v][1])):
                t = var(0, inf, cfg.get("w_geo", 0.02))
                row([(t, 1), (C, -1)], -gv, inf)
                row([(t, 1), (C, 1)], gv, inf)
        RES = {}
        SLK = {}
        for e in E:
            a, b = e
            dx, dy = DIRS[dirs[e]]
            n_orig = len(cg["edges"][e]["chain"]) - 1
            lmin = cfg["min_edge"] * (1 + cfg.get("chain_len_factor", 0.6) * (n_orig - 1))
            r = var(0, inf, 50.0)
            RES[e] = r
            if dy == 0:
                eq = [(Y[b], 1), (Y[a], -1)]
            elif dx == 0:
                eq = [(X[b], 1), (X[a], -1)]
            elif dx == dy:
                eq = [(X[b], 1), (X[a], -1), (Y[b], -1), (Y[a], 1)]
            else:
                eq = [(X[b], 1), (X[a], -1), (Y[b], 1), (Y[a], -1)]
            row(eq + [(r, 1)], 0, inf)
            row([(c, -k) for c, k in eq] + [(r, 1)], 0, inf)
            sl = var(0, inf, 200.0)   # 진행 부족 벌점
            SLK[e] = sl
            prog = [(X[b], dx), (X[a], -dx)] if dx != 0 else [(Y[b], dy), (Y[a], -dy)]
            row(prog + [(sl, 1)], lmin, inf)
            L = var(0, inf, cfg["w_len"])
            row([(L, 1)] + [(c, -k) for c, k in prog], 0, inf)
        row([(X[nodes[0]], 1)], G[nodes[0]][0], G[nodes[0]][0])
        row([(Y[nodes[0]], 1)], G[nodes[0]][1], G[nodes[0]][1])
        h.run()
        sol = h.getSolution().col_value
        pos = {v: (sol[X[v]], sol[Y[v]]) for v in nodes}
        bad = [e for e in E if sol[RES[e]] > 1e-6]
        if log:
            log(f"    snap-lp round {rd + 1}: 잔차 남은 엣지 {len(bad)}")
        if not bad:
            break
        for e in bad:   # 실제 배치 방향에 가장 가까운 8방향으로 다시 고정
            a, b = e
            dirs[e] = sector(pos[b][0] - pos[a][0], pos[b][1] - pos[a][1])
    # 남은 잔차는 그대로 (octilinear 아닌 엣지로 지표에 잡힌다)
    return {"pos": pos, "status": "snap-lp", "iterations": rounds, "crossing_constraints": 0, "objective": None, "scale": scale,
            "dirs": dict(dirs), "residual_edges": [e for e in E if sol[RES[e]] > 1e-6 or sol[SLK[e]] > 1e-6]}


def solve_lns(g: dict, cg: dict, cfg: dict, log=None) -> dict:
    """큰 권역용 fix-and-optimize (LNS). snap-lp 방향으로 대부분 엣지를 고정한 MIP로 첫 해를 얻고,
    교차·굴곡이 몰린 구역(씨앗 정점 주변 lns_radius 홉)의 엣지만 3방향으로 풀어 다시 푸는 것을 lns_rounds번 반복한다.
    목적값이 나빠지면 그 라운드 결과를 버린다. 순환 순서는 soft (벌점)."""
    import time as _t
    base = dict(cfg, order=cfg.get("order", "soft"))
    t0 = _t.time()
    snap = solve_snap_lp(g, cg, cfg)
    E = list(cg["edges"].keys())
    res = set(snap["residual_edges"])
    P = g["pos"]

    def around3(e):
        a, b = e
        s0 = sector(P[b][0] - P[a][0], P[b][1] - P[a][1])
        return [(s0 - 1) % 8, s0, (s0 + 1) % 8]
    # 잔차 엣지 끝점에서 lns_init_radius 홉 안의 엣지까지 풀어야 고정 방향 사이클의 닫힘 조건이 맞는다
    adj0 = defaultdict(set)
    for a, b in E:
        adj0[a].add(b)
        adj0[b].add(a)
    free_n = {v for e in res for v in e}
    fr = set(free_n)
    for _ in range(cfg.get("lns_init_radius", 2)):
        fr = {w for v in fr for w in adj0[v]} - free_n
        free_n |= fr
    free0 = {e for e in E if e in res or (e[0] in free_n and e[1] in free_n)}
    allowed = {e: ([snap["dirs"][e]] if e not in free0 else sorted(set(around3(e)) | {snap["dirs"][e]})) for e in E}
    if log:
        log(f"    LNS 시작: snap-lp 잔차·길이 부족 엣지 {len(res)}개와 주변까지 {len(free0)}개를 풀고 나머지 {len(E) - len(free0)}개 방향 고정")
    r = solve_octilinear(g, cg, dict(base, allowed=allowed, pos_window=None, time_limit_s=cfg.get("lns_time_s", 60)), log=log)
    if not r["pos"]:
        return {**snap, "status": "LNS 첫 해 실패 → snap-lp", "engine_detail": "snap-lp"}
    best = r
    adj = defaultdict(set)
    for a, b in E:
        adj[a].add(b)
        adj[b].add(a)
    rounds = cfg.get("lns_rounds", 6)
    radius = cfg.get("lns_radius", 3)
    tried = set()
    for k in range(rounds):
        if _t.time() - t0 > cfg.get("lns_total_s", 900):
            break
        pos = expand(g, cg, best["pos"])
        st = layout_stats(g, pos)
        # 씨앗: 교차하는 엣지 끝점 우선, 없으면 굴곡이 큰 정점
        seeds = []
        Ek = list(g["edges"].keys())
        for i in range(len(Ek)):
            a, b = Ek[i]
            for j in range(i + 1, len(Ek)):
                c, d = Ek[j]
                if len({a, b, c, d}) == 4 and segments_cross(pos[a], pos[b], pos[c], pos[d]) and not segments_cross(P[a], P[b], P[c], P[d]):
                    seeds += [a, c]
        if not seeds:
            bend_at = defaultdict(int)
            for sq in g["seqs"]:
                ks = sq["nodes"]
                for a, v, b in zip(ks, ks[1:], ks[2:]):
                    t1 = math.atan2(pos[a][1] - pos[v][1], pos[a][0] - pos[v][0])
                    t2 = math.atan2(pos[b][1] - pos[v][1], pos[b][0] - pos[v][0])
                    bend_at[v] += round(abs((math.degrees(t2 - t1) + 360) % 360 - 180) / 45.0)
            seeds = [v for v, _ in sorted(bend_at.items(), key=lambda kv: (-kv[1], kv[0]))]
        kept = set(cg["nodes"])
        seed = next((v for v in seeds if v in kept and v not in tried), None)
        if seed is None:
            break
        tried.add(seed)
        free_nodes = {seed}
        frontier = {seed}
        for _ in range(radius):
            frontier = {w for v in frontier for w in adj[v]} - free_nodes
            free_nodes |= frontier
        allowed_k = {e: (sorted(set(around3(e)) | {best["dirs"][e]}) if (e[0] in free_nodes or e[1] in free_nodes) else [best["dirs"][e]]) for e in E}
        rk = solve_octilinear(g, cg, dict(base, allowed=allowed_k, pos_window=None, time_limit_s=cfg.get("lns_time_s", 60)), log=None)
        ok = bool(rk["pos"]) and rk["objective"] is not None and rk["objective"] <= best["objective"] + 1e-6
        if log:
            log(f"    LNS {k + 1}: 씨앗 {seed}, 자유 엣지 {sum(1 for e in E if len(allowed_k[e]) > 1)}, "
                f"{rk['status']}, obj {rk['objective'] if rk['objective'] is not None else '-'} (최선 {best['objective']:.2f}) {'채택' if ok else '버림'}")
        if ok:
            best = rk
    best = dict(best)
    best["status"] = f"LNS: {best['status']}"
    best["engine_detail"] = "mip-lns"
    return best


def place_labels(stations: list[dict], cell: float = 40.0) -> list[dict]:
    """라벨 충돌 회피 (web/schematic_core.js placeLabels와 같은 규칙). 큰 역부터, 후보 중 겹침 넓이 최소."""
    grid = defaultdict(list)

    def cells(b):
        for i in range(int(math.floor(b[0] / cell)), int(math.floor(b[2] / cell)) + 1):
            for j in range(int(math.floor(b[1] / cell)), int(math.floor(b[3] / cell)) + 1):
                yield (i, j)

    def add(b):
        for c in cells(b):
            grid[c].append(b)

    def overlap(a, b):
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    for st in stations:
        r = 6 if st["big"] else 4
        add((st["p"][0] - r, st["p"][1] - r, st["p"][0] + r, st["p"][1] + r))
    order = sorted(range(len(stations)), key=lambda i: (not stations[i]["big"], i))
    out = [None] * len(stations)
    for i in order:
        st = stations[i]
        x0, y0 = st["p"]
        w, h = len(st["text"]) * st["size"] * 0.95, st["size"] * 1.2
        ux, uy = st["dir"]
        nx, ny = -uy, ux
        if nx < 0:
            nx, ny = -nx, -ny
        horiz = abs(uy) < 0.38
        d45 = w * math.sqrt(0.5)
        cand = []
        if horiz:
            cand.append({"x": x0 + 3, "y": y0 - 7, "rot": -45, "anchor": "start", "box": (x0 + 2, y0 - 7 - d45 - h * 0.5, x0 + 4 + d45, y0 - 5)})
            cand.append({"x": x0 - 3, "y": y0 + 12, "rot": -45, "anchor": "end", "box": (x0 - 4 - d45, y0 + 8, x0 - 2, y0 + 12 + d45 + h * 0.5)})
        for sg in (1, -1):
            x, y = x0 + sg * nx * 8, y0 + sg * ny * 8 + 3
            anchor = "start" if sg * nx >= 0 else "end"
            xa = x if anchor == "start" else x - w
            cand.append({"x": x, "y": y, "rot": 0, "anchor": anchor, "box": (xa, y - h * 0.85, xa + w, y + h * 0.15)})
        if not horiz:
            cand.append({"x": x0 - w / 2, "y": y0 - 9, "rot": 0, "anchor": "start", "box": (x0 - w / 2, y0 - 9 - h * 0.85, x0 + w / 2, y0 - 9 + h * 0.15)})
        best = None
        for k, c in enumerate(cand):
            near = {id(b): b for cc in cells(c["box"]) for b in grid[cc]}
            o = sum(overlap(c["box"], b) for b in near.values()) + k * 0.01
            if best is None or o < best[0]:
                best = (o, c)
            if o < 0.02 * (k + 1):
                break
        add(best[1]["box"])
        out[i] = best[1]
    return out
