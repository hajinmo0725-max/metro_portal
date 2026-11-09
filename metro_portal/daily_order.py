"""데일리 퍼즐 순서 (daily_order) 구성. 4차 Q2.

풀이 시그니처 = 최적 경로에 쓰인 포탈 순서 (예: ('중동', '동백')). 순서는 L일짜리 순환 일정이다 (웹은 날짜 차이 mod L로 고른다).
하드 제약 (전부 순환 기준, config/game.yaml daily_order):
  (i)   같은 시그니처는 signature_gap_days일 안에 다시 나오지 않는다
  (ii)  연속한 두 날의 포탈 집합 자카드 유사도 ≤ max_jaccard
  (iii) window_days일 창마다 포탈별 등장 횟수 ≤ max_portal_per_window
  (iv)  요일별 허용 난이도 (보정 난이도 = 직관 탐색 점수 기준 easy/normal/hard)
소프트 목표: 요일별 목표 난이도 지수(h = 1 - 직관 점수)와의 차이 최소, 퍼즐 흥미도 최대, 최근 쓴 포탈 회피.
풀이: (1) 탐욕 배치 — 날마다 하드 제약을 지키는 후보 중 소프트 비용 최소. 이미 배치된 날과의 거리는 순환 거리로 잰다.
      (2) 국소탐색 — 위반이 남은 날을 미사용 후보로 교체하거나 다른 날과 교환해서 (위반 수, 소프트 비용)을 사전식으로 줄인다.
결정적이다: 후보 정렬은 (비용, id), 국소탐색은 고정 순서로 돈다.
locked: 앞부분 고정 일정 (출시 후 append-only 규칙, game.yaml daily_release). 이 날들은 바꾸지 않는다.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def ranked(cnt: Counter, k: int | None = None) -> list:
    """Counter.most_common과 같지만 동률은 이름순 (5차: frozenset 순회 순서가 해시 시드에 따라 달라 출력이 흔들리던 문제)."""
    out = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
    return out[:k] if k is not None else out


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def hardness(p: dict) -> float:
    """보정 난이도 지수 h = 1 - 직관 점수 (0 = 직관대로 가면 최적, 1에 가까울수록 지리 감각과 반대)."""
    return round(1.0 - float(p.get("intuition_score", 0.0)), 4)


class Planner:
    def __init__(self, puzzles: list[dict], cfg: dict, epoch: date, locked: list[str] | None = None):
        self.cfg = cfg
        self.L = int(cfg["days"])
        self.epoch = epoch
        self.P = {p["id"]: p for p in puzzles}
        self.sig = {p["id"]: tuple(p["warp_portals"]) for p in puzzles}
        self.pset = {p["id"]: frozenset(p["warp_portals"]) for p in puzzles}
        self.h = {p["id"]: hardness(p) for p in puzzles}
        self.level = {p["id"]: p.get("difficulty_calibrated") or p["difficulty"] for p in puzzles}
        q = {}
        for kind in ("shortcut", "crosscity"):
            ps = [p for p in puzzles if p["kind"] == kind]
            if not ps:
                continue
            raw = {p["id"]: (p["savings"] if kind == "shortcut" else p["warps"] + p["cost_warp"] / 30) for p in ps}
            mx = max(raw.values()) or 1
            q.update({k: v / mx for k, v in raw.items()})
        self.quality = q
        self.locked = list(locked or [])
        wd = cfg["weekday"]
        self.allowed = [set(wd[WEEKDAYS[(epoch + timedelta(days=t)).weekday()]]["levels"]) for t in range(self.L)]
        # 5차 R1: 퍼즐 ruleset과 요일. 요일별 허용 ruleset(weekday.<요일>.rulesets, 없으면 전부)과
        # ruleset별 허용 요일(ruleset_weekdays.<ruleset>, 없으면 전부)을 (iv) 요일 제약에 함께 넣는다
        self.rs = {p["id"]: p.get("ruleset") for p in puzzles}
        rw = cfg.get("ruleset_weekdays") or {}
        self.day_rs = []
        for t in range(self.L):
            name = WEEKDAYS[(epoch + timedelta(days=t)).weekday()]
            allow = wd[name].get("rulesets")
            self.day_rs.append((set(allow) if allow else None, {r for r, days in rw.items() if name not in days}))
        self.target = [float(wd[WEEKDAYS[(epoch + timedelta(days=t)).weekday()]]["target_h"]) for t in range(self.L)]
        self.w = cfg["weights"]

    def day_ok(self, t: int, pid: str) -> bool:
        """(iv) 요일 제약: 보정 난이도 + ruleset."""
        if self.level[pid] not in self.allowed[t]:
            return False
        allow, deny = self.day_rs[t]
        r = self.rs.get(pid)
        return (allow is None or r in allow) and r not in deny

    # ---------- 제약 ----------
    def cdist(self, a: int, b: int) -> int:
        d = abs(a - b) % self.L
        return min(d, self.L - d)

    def occupancy(self, order: list) -> dict:
        """포탈 → 그 포탈을 쓰는 날짜 집합."""
        occ = defaultdict(set)
        for u, pid in enumerate(order):
            if pid is not None:
                for x in self.pset[pid]:
                    occ[x].add(u)
        return occ

    def place_ok(self, order: list, t: int, pid: str, occ: dict | None = None) -> tuple[int, int, int, int]:
        """order(None = 빈 날)에 t일 pid를 넣을 때 새로 생기는 위반 수 (i, ii, iii, iv). 순환 거리 기준.
        occ: occupancy(order) 캐시 (t일 자신은 세지 않는다)."""
        L, cfg = self.L, self.cfg
        sig, ps = self.sig[pid], self.pset[pid]
        v1 = sum(1 for d in range(1, cfg["signature_gap_days"]) for u in {(t - d) % L, (t + d) % L}
                 if order[u] is not None and order[u] != pid and self.sig[order[u]] == sig)
        v2 = 0
        for u in {(t - 1) % L, (t + 1) % L}:
            if order[u] is not None and u != t and jaccard(ps, self.pset[order[u]]) > cfg["max_jaccard"] + 1e-9:
                v2 += 1
        v3 = 0
        W, cap = cfg["window_days"], cfg["max_portal_per_window"]
        if occ is None:
            occ = self.occupancy(order)
        for x in ps:
            days = occ.get(x, ())
            # t를 포함하는 창 [s, s+W) (s = t-W+1 .. t) 마다 t 말고 x를 쓰는 날 수
            ind = [1 if ((t + k) % L) in days and ((t + k) % L) != t else 0 for k in range(-W + 1, W)]
            run = sum(ind[0:W])
            for s0 in range(W):
                if s0:
                    run += ind[s0 + W - 1] - ind[s0 - 1]
                if run + 1 > cap:
                    v3 += 1
        v4 = 0 if self.day_ok(t, pid) else 1
        return v1, v2, v3, v4

    def violations(self, order: list) -> dict:
        """전체 위반 (순환). 쌍·창 단위로 센다."""
        L, cfg = self.L, self.cfg
        out = {"signature": [], "jaccard": [], "window": [], "weekday": []}
        pos = defaultdict(list)
        for t, pid in enumerate(order):
            pos[self.sig[pid]].append(t)
        for s, ts in pos.items():
            for i, a in enumerate(ts):
                for b in ts[i + 1:]:
                    if self.cdist(a, b) < cfg["signature_gap_days"]:
                        out["signature"].append((a, b, "+".join(s)))
        for t in range(L):
            j = jaccard(self.pset[order[t - 1]], self.pset[order[t]])
            if j > cfg["max_jaccard"] + 1e-9:
                out["jaccard"].append((t, round(j, 3)))
        W, cap = cfg["window_days"], cfg["max_portal_per_window"]
        for s in range(L):
            cnt = Counter()
            for k in range(s, s + W):
                cnt.update(self.pset[order[k % L]])
            for x, c in sorted(cnt.items()):
                if c > cap:
                    out["window"].append((s, x, c))
        for t, pid in enumerate(order):
            if not self.day_ok(t, pid):
                out["weekday"].append((t, self.level[pid]))
        return out

    def soft(self, order: list, t: int, pid: str) -> float:
        """t일에 pid를 둘 때의 소프트 비용: 난이도 목표 차이 + 최근 같은 포탈 사용 - 흥미도."""
        w = self.w
        rec = 0.0
        for d in range(1, self.cfg["window_days"]):
            for u in ((t - d) % self.L, (t + d) % self.L):
                if order[u] is not None and order[u] != pid:
                    rec += len(self.pset[pid] & self.pset[order[u]]) / d
        return w["difficulty"] * abs(self.h[pid] - self.target[t]) + w["recency"] * rec - w["quality"] * self.quality[pid]

    # ---------- 풀이 ----------
    def greedy(self) -> list:
        L = self.L
        order = [None] * L
        for t, pid in enumerate(self.locked[:L]):
            order[t] = pid
        used = set(x for x in order if x)
        ids = sorted(self.P)
        occ = self.occupancy(order)
        for t in range(len(self.locked), L):
            best = None
            for pid in ids:
                if pid in used:
                    continue
                v = self.place_ok(order, t, pid, occ)
                key = (sum(v), round(self.soft(order, t, pid), 6), pid)
                if best is None or key < best[0]:
                    best = (key, pid)
            if best is None:
                raise ValueError("후보가 일정 길이보다 적다")
            order[t] = best[1]
            used.add(best[1])
            for x in self.pset[best[1]]:
                occ[x].add(t)
        return order

    def total(self, order: list) -> tuple[int, float]:
        v = self.violations(order)
        n = sum(len(x) for x in v.values())
        s = sum(self.soft(order, t, pid) for t, pid in enumerate(order))
        return n, round(s, 6)

    def local_search(self, order: list, max_rounds: int = 12, max_evals: int | None = None) -> list:
        """위반이 있는 날을 교체(미사용 후보) 또는 교환(다른 날)해서 (위반 수, 소프트) 사전식 감소. 잠긴 날은 건드리지 않는다.
        max_evals: 전체 평가(total) 횟수 상한 (5차: 풀이 부족해 위반이 많이 남는 설정에서 끝없이 도는 것 방지. 시간이 아니라 횟수라 결정적)."""
        order = list(order)
        fixed = len(self.locked)
        max_evals = max_evals if max_evals is not None else int(self.cfg.get("repair_max_evals", 20000))
        evals = [0]
        _total = self.total

        def total(o):
            evals[0] += 1
            if evals[0] > max_evals:
                raise StopIteration
            return _total(o)
        best = _total(order)
        try:
            return self._local_search(order, fixed, best, total, max_rounds)
        except StopIteration:
            self.last_search_capped = True
            return self._ls_best

    def _local_search(self, order, fixed, best, total, max_rounds):
        self.last_search_capped = False
        self._ls_best = list(order)
        for _ in range(max_rounds):
            improved = False
            v = self.violations(order)
            bad = sorted({t for a, b, _ in v["signature"] for t in (a, b)} | {t for t, _ in v["jaccard"]}
                         | {(t - 1) % self.L for t, _ in v["jaccard"]} | {t for t, _ in v["weekday"]}
                         | {(s + k) % self.L for s, x, _ in v["window"] for k in range(self.cfg["window_days"])
                            if x in self.pset[order[(s + k) % self.L]]})
            bad = [t for t in bad if t >= fixed]
            if not bad:
                break
            used = set(order)
            unused = sorted(pid for pid in self.P if pid not in used)
            for t in bad:
                cur = order[t]
                # 교체 후보: 그 날 단독 위반이 적은 순 상위 k개만 전체 평가
                trial = order[:]
                trial[t] = None
                occ = self.occupancy(trial)
                cands = sorted(unused, key=lambda pid: (sum(self.place_ok(trial, t, pid, occ)), round(self.soft(trial, t, pid), 6), pid))
                cands = cands[: self.cfg.get("repair_candidates", 25)]
                for pid in cands:
                    trial[t] = pid
                    tot = total(trial)
                    if tot < best:
                        best, order = tot, trial[:]
                        self._ls_best = list(order)
                        unused.remove(pid)
                        unused.append(cur)
                        unused.sort()
                        improved = True
                        break
                else:
                    trial[t] = cur
                    # 교환: 같은 요일 허용 등급을 만족하는 다른 날과
                    for u in range(fixed, self.L):
                        if u == t or not self.day_ok(t, order[u]) or not self.day_ok(u, cur):
                            continue
                        sw = order[:]
                        sw[t], sw[u] = sw[u], sw[t]
                        tot = total(sw)
                        if tot < best:
                            best, order = tot, sw
                            self._ls_best = list(order)
                            improved = True
                            break
            if not improved:
                break
        return order


def summarize(planner: Planner, order: list, horizon: int | None = None) -> dict:
    """제약별 충족 여부와 포탈 분포."""
    v = planner.violations(order)
    L = len(order)
    cnt = Counter(x for pid in order for x in planner.pset[pid])
    W = planner.cfg["window_days"]
    win_max = Counter()
    for s in range(L):
        c = Counter()
        for k in range(s, s + W):
            c.update(planner.pset[order[k % L]])
        for x, n in c.items():
            win_max[x] = max(win_max[x], n)
    sig_gap = []
    pos = defaultdict(list)
    for t, pid in enumerate(order):
        pos[planner.sig[pid]].append(t)
    for ts in pos.values():
        if len(ts) > 1:
            sig_gap.append(min(planner.cdist(a, b) for i, a in enumerate(ts) for b in ts[i + 1:]))
    jac = [jaccard(planner.pset[order[t - 1]], planner.pset[order[t]]) for t in range(L)]
    by_wd = defaultdict(list)
    for t, pid in enumerate(order):
        by_wd[WEEKDAYS[(planner.epoch + timedelta(days=t)).weekday()]].append(planner.h[pid])
    return {
        "days": L,
        "violations": {k: len(x) for k, x in v.items()},
        "violation_examples": {k: x[:5] for k, x in v.items()},
        "min_signature_gap": min(sig_gap) if sig_gap else None,
        "distinct_signatures": len(pos),
        "max_jaccard_consecutive": round(max(jac), 3),
        "mean_jaccard_consecutive": round(sum(jac) / L, 3),
        "portal_counts": dict(ranked(cnt)),
        "portal_max_in_window": dict(ranked(win_max)),
        "weekday_mean_h": {wd: round(sum(by_wd[wd]) / len(by_wd[wd]), 3) for wd in WEEKDAYS if by_wd[wd]},
        "weekday_levels": {wd: dict(Counter(planner.level[order[t]] for t in range(L)
                                            if WEEKDAYS[(planner.epoch + timedelta(days=t)).weekday()] == wd)) for wd in WEEKDAYS},
    }
