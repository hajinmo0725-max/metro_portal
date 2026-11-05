"""노선 순서·좌표 검증 (N2·N3). OSM 없이 좌표 기하와 외부 인접 정보(Wikidata P197)로 의심 구간을 찾는다.

여기 함수들은 '의심'만 낸다. 실제 보정(config/kr_lines.yaml)은 독립된 근거 2개 이상이 일치할 때만 사람이(또는
보고서 판단으로) 한다. 임계값은 config/validation.yaml에서 받는다.
"""
from __future__ import annotations

import math

from .geo import haversine_m


def dist_matrix(pts):
    n = len(pts)
    return [[haversine_m(pts[i][0], pts[i][1], pts[j][0], pts[j][1]) for j in range(n)] for i in range(n)]


def path_length(order, D, closed=False):
    s = sum(D[a][b] for a, b in zip(order, order[1:]))
    if closed and len(order) > 2:
        s += D[order[-1]][order[0]]
    return s


def _two_opt(order, D, closed):
    """2-opt 지역 최적화. open이면 양 끝이 자유로운 해밀턴 경로, closed면 순환."""
    p = list(order)
    n = len(p)
    if n < 4:
        return p
    improved = True
    while improved:
        improved = False
        for i in range(0, n - 1):
            for j in range(i + 1, n):
                if i == 0 and j == n - 1:
                    continue
                a = p[i - 1] if i > 0 else (p[-1] if closed else None)
                b, c = p[i], p[j]
                d = p[j + 1] if j + 1 < n else (p[0] if closed else None)
                before = (D[a][b] if a is not None else 0) + (D[c][d] if d is not None else 0)
                after = (D[a][c] if a is not None else 0) + (D[b][d] if d is not None else 0)
                if after + 1e-6 < before:
                    p[i:j + 1] = reversed(p[i:j + 1])
                    improved = True
    return p


def _or_opt(p, D, closed):
    """구간(1~3개) 이동. 2-opt만으로는 못 빠져나오는 지역해를 줄인다."""
    p = list(p)
    n = len(p)
    best = path_length(p, D, closed)
    improved = True
    while improved:
        improved = False
        for seg in (1, 2, 3):
            for i in range(0, n - seg + 1):
                block = p[i:i + seg]
                rest = p[:i] + p[i + seg:]
                for k in range(0, len(rest) + 1):
                    if k == i:
                        continue
                    for blk in (block, block[::-1]):
                        cand = rest[:k] + blk + rest[k:]
                        L = path_length(cand, D, closed)
                        if L + 1e-6 < best:
                            p, best, improved = cand, L, True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    return p


def optimize_order(pts, current=None, closed=False):
    """좌표 기반 경로 최적화. 시작해: 현재 순서 + 각 점에서 시작한 최근접 이웃. 2-opt → or-opt 반복.
    반환: (최적 순서(인덱스), 길이). 결정적이다 (시작해 순서 고정, 같은 길이면 먼저 찾은 해)."""
    n = len(pts)
    D = dist_matrix(pts)
    if n <= 2:
        order = list(range(n))
        return order, path_length(order, D, closed)
    starts = []
    if current is not None:
        starts.append(list(current))
    for s in range(n):
        seen, cur, order = {s}, s, [s]
        while len(order) < n:
            nxt = min((j for j in range(n) if j not in seen), key=lambda j: (D[cur][j], j))
            seen.add(nxt)
            order.append(nxt)
            cur = nxt
        starts.append(order)
    best, bestL = None, float("inf")
    for st in starts:
        p = st
        for _ in range(5):
            q = _or_opt(_two_opt(p, D, closed), D, closed)
            if q == p:
                break
            p = q
        L = path_length(p, D, closed)
        if L + 1e-6 < bestL:
            best, bestL = p, L
    return best, bestL


def _bearing_vec(a, b):
    """a→b 방향 벡터 (경도에 cos(위도) 보정한 평면 근사)."""
    lat0 = math.radians((a[0] + b[0]) / 2)
    return ((b[1] - a[1]) * math.cos(lat0), b[0] - a[0])


def interior_angle_deg(a, b, c):
    """b에서 b→a와 b→c 사이 각도. 180이면 직진, 0에 가까우면 왔던 방향으로 되돌아감."""
    v1, v2 = _bearing_vec(b, a), _bearing_vec(b, c)
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 180.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def geometry_flags(pts, cfg, closed=False):
    """연속 3점 급반전(되돌아감)과 연속 4점 국소 스왑 이득을 찾는다. pts: [(lat, lon)] 현재 순서.
    반환: [{kind, i(위치), ...}]"""
    n = len(pts)
    out = []
    idx = list(range(n))
    ring = closed and n > 3

    def P(i):
        return pts[i % n]

    rng = range(n) if ring else range(1, n - 1)
    for i in rng:
        a, b, c = P(i - 1), P(i), P(i + 1)
        ang = interior_angle_deg(a, b, c)
        dab = haversine_m(*a, *b)
        dbc = haversine_m(*b, *c)
        dac = haversine_m(*a, *c)
        if ang < cfg["backtrack_angle_deg"] and min(dab, dbc) >= cfg["backtrack_min_segment_m"]:
            out.append({"kind": "backtrack", "i": i % n, "angle_deg": round(ang, 1),
                        "detour_ratio": round((dab + dbc) / dac, 2) if dac > 0 else None,
                        "seg_m": [round(dab), round(dbc)]})
    # 국소 스왑: (a, b, c, d) → (a, c, b, d). 양 끝은 한쪽만 있음
    rng4 = range(n) if ring else range(-1, n - 2)
    for i in rng4:
        ia, ib, ic, id_ = i, i + 1, i + 2, i + 3
        if not ring:
            if ib < 0 or ic >= n:
                continue
        a = P(ia) if (ring or ia >= 0) else None
        d = P(id_) if (ring or id_ < n) else None
        b, c = P(ib), P(ic)
        before = (haversine_m(*a, *b) if a else 0) + haversine_m(*b, *c) + (haversine_m(*c, *d) if d else 0)
        after = (haversine_m(*a, *c) if a else 0) + haversine_m(*c, *b) + (haversine_m(*b, *d) if d else 0)
        gain = before - after
        if gain >= cfg["swap_gain_min_m"] and gain >= cfg["swap_gain_min_ratio"] * before:
            out.append({"kind": "swap", "i": ib % n, "j": ic % n, "gain_m": round(gain), "before_m": round(before)})
    del idx
    return out


def edges_of(order, closed=False):
    e = {tuple(sorted(p)) for p in zip(order, order[1:])}
    if closed and len(order) > 2:
        e.add(tuple(sorted((order[-1], order[0]))))
    return e


def spike_flags(pts, cfg, closed=False):
    """좌표 스파이크: b가 양쪽 이웃과 모두 멀고, 이웃끼리는 가까우면 b 좌표가 다른 곳(동명역 등)일 가능성.
    양원 사례(영동선 양원 좌표가 섞여 190km). 반환: [{i, d_prev, d_next, d_skip}]"""
    n = len(pts)
    out = []
    if n < 3:
        return out
    rng = range(n) if (closed and n > 3) else range(1, n - 1)
    for i in rng:
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        dab, dbc, dac = haversine_m(*a, *b), haversine_m(*b, *c), haversine_m(*a, *c)
        if min(dab, dbc) >= cfg["spike_min_m"] and min(dab, dbc) >= cfg["spike_ratio"] * max(dac, 1.0):
            out.append({"i": i, "d_prev": round(dab), "d_next": round(dbc), "d_skip": round(dac)})
    # 끝점: 바로 옆 이웃과의 거리가 그 다음 구간보다 훨씬 길면 끝점 좌표 의심
    if not closed and n >= 3:
        for i, j, k in ((0, 1, 2), (n - 1, n - 2, n - 3)):
            dij, djk = haversine_m(*pts[i], *pts[j]), haversine_m(*pts[j], *pts[k])
            if dij >= cfg["spike_min_m"] and dij >= cfg["spike_end_ratio"] * max(djk, 1.0):
                out.append({"i": i, "d_prev": round(dij), "d_next": None, "d_skip": round(djk), "end": True})
    return out
