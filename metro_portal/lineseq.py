"""인접 관계(무향 그래프)에서 노선 정차 시퀀스를 만든다. Phase 1 타이베이 (Wikidata P197) 용. 3차 B1.

역번호(운영사 번호)를 같이 써서 (1) 한정자 없는 인접 진술은 역번호가 이어질 때만 채택하고 (2) 순환이 생기면
역번호가 안 이어지는 엣지를 끊고 (3) 시퀀스 방향을 역번호 오름차순으로 맞춘다.
"""
from __future__ import annotations

import re
from collections import defaultdict

_CODE = re.compile(r"^([A-Z]+)(\d+)([A-Za-z]?)$")


def parse_code(code: str):
    m = _CODE.match(code or "")
    if not m:
        return None
    return m.group(1), int(m.group(2)), m.group(3).lower()


def code_key(code: str):
    p = parse_code(code)
    return (p[1], p[2]) if p else (10 ** 9, code or "")


def code_consecutive(a: str, b: str, line_codes: set | None = None) -> bool:
    """역번호가 이어지는가: 같은 접두어에서 번호 차 1, 또는 번호가 같고 접미 문자만 다름 (R22 ↔ R22A).
    접미 문자가 붙은 번호는 같은 노선에 기본 번호 역이 있으면 지선 역(R22A, G03A)이라 기본 번호와만 이어지고,
    기본 번호 역이 없으면 본선 역(A14a: A14 미개통)이라 앞뒤 번호와 이어진다."""
    pa, pb = parse_code(a), parse_code(b)
    if not pa or not pb or pa[0] != pb[0]:
        return False
    if pa[1] == pb[1]:
        return pa[2] != pb[2]
    if abs(pa[1] - pb[1]) != 1:
        return False
    for code, p in ((a, pa), (b, pb)):
        if p[2] and line_codes is not None and code[:-1] in line_codes:
            return False
    return True


def _components(nodes, edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, comps = set(), []
    for n in sorted(nodes):
        if n in seen:
            continue
        st, comp = [n], []
        seen.add(n)
        while st:
            x = st.pop()
            comp.append(x)
            for y in sorted(adj[x]):
                if y not in seen:
                    seen.add(y)
                    st.append(y)
        comps.append(sorted(comp))
    return comps, adj


def break_cycles(nodes, edges, code):
    """순환을 만드는 엣지를 제거해 숲(forest)으로 만든다. 역번호가 이어지는 엣지를 먼저 넣는 크루스칼 방식.
    반환: (남긴 엣지, 뺀 엣지)"""
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    line_codes = set(code.values())
    order = sorted(edges, key=lambda e: (0 if code_consecutive(code[e[0]], code[e[1]], line_codes) else 1, sorted(e)))
    kept, dropped = [], []
    for a, b in order:
        ra, rb = find(a), find(b)
        if ra == rb:
            dropped.append((a, b))
            continue
        parent[ra] = rb
        kept.append((a, b))
    return sorted(tuple(sorted(e)) for e in kept), sorted(tuple(sorted(e)) for e in dropped)


def _end_rank(n, code):
    """같은 거리일 때 끝점 우선순위: 접미 문자 없는 역번호(본선) 먼저, 그다음 역번호 순."""
    p = parse_code(code.get(n, ""))
    return (0 if (p and not p[2]) else 1, code_key(code.get(n, "")), n)


def _farthest(start, adj, allowed, code=None):
    """트리에서 start로부터 가장 먼(역 수) 노드와 경로. 동률이면 _end_rank가 작은 쪽."""
    code = code or {}
    best = (0, start, [start])
    st = [(start, None, [start])]
    while st:
        x, par, path = st.pop()
        d = len(path) - 1
        if d > best[0] or (d == best[0] and _end_rank(x, code) < _end_rank(best[1], code)):
            best = (d, x, path)
        for y in sorted(adj[x]):
            if y != par and frozenset((x, y)) in allowed:
                st.append((y, x, path + [y]))
    return best


def decompose(nodes, edges, code):
    """숲을 시퀀스(경로) 목록으로. 각 컴포넌트에서 가장 긴 경로를 본선으로, 남은 엣지는 본선에 붙은 지선 경로로 뗀다.
    시퀀스 방향: 첫 역의 역번호 < 끝 역의 역번호. 지선은 분기역에서 시작한다."""
    comps, adj = _components(nodes, edges)
    comps.sort(key=lambda c: min(code_key(code[n]) for n in c))
    remaining = {frozenset(e) for e in edges}
    seqs = []
    for comp in comps:
        if len(comp) == 1:
            seqs.append([comp[0]])
            continue
        # 본선: 트리 지름 (two-sweep). 시작점은 역번호가 가장 작은 노드
        s0 = min(comp, key=lambda n: code_key(code[n]))
        _, a, _ = _farthest(s0, adj, remaining, code)
        _, b, path = _farthest(a, adj, remaining, code)
        if code_key(code[path[0]]) > code_key(code[path[-1]]):
            path = path[::-1]
        seqs.append(path)
        for x, y in zip(path, path[1:]):
            remaining.discard(frozenset((x, y)))
        covered = set(path)
        # 지선: 이미 덮인 노드에서 남은 엣지로 뻗는 가장 긴 경로를 반복해서 뗀다
        while True:
            starts = sorted({n for n in covered for y in adj[n] if frozenset((n, y)) in remaining}, key=lambda n: code_key(code[n]))
            if not starts:
                break
            cands = []
            for s in starts:
                d, end, p = _farthest(s, adj, remaining, code)
                cands.append((-d, code_key(code[s]), p))
            cands.sort()
            p = cands[0][2]
            seqs.append(p)
            for x, y in zip(p, p[1:]):
                remaining.discard(frozenset((x, y)))
            covered |= set(p)
    return seqs
