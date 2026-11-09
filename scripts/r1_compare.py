#!/usr/bin/env python3
"""5차 R1: 데일리 1년 일정 — 풀 확대 방법 비교 → docs/reports/r1_daily_year.md, data/processed/daily_year_compare.json

같은 그래프(strict, 주말 풀은 tw_t12)에서 풀 설정만 바꿔 일정을 짜고, 같은 하드 제약(config/game.yaml daily_order:
시그니처 간격 14일, 연속일 자카드 ≤ 1/3, 30일 창 포탈당 ≤ 4, 요일별 보정 난이도)으로 위반·다양성을 잰다.
변형은 누적이다 (앞 변형 + 한 가지 변경). 4차 기준은 182일, 나머지는 371일(53주).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.daily_order import WEEKDAYS, Planner, ranked, summarize  # noqa: E402
from metro_portal.game import ClusterGraph  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base, load_multi  # noqa: E402

spec = importlib.util.spec_from_file_location("g10", ROOT / "pipeline" / "10_build_game_data.py")
g10 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g10)

V4_POOL = {"quotas": {"shortcut": 90, "crosscity": 70}, "max_per_signature": 2, "max_per_endpoint": 3, "max_optimal_paths": 1, "min_savings": 3}
OFF = {"enabled": False}


def variants(oc):
    wk = oc["weekend_pool"]
    big = {**V4_POOL, "quotas": {"shortcut": 200, "crosscity": 150}}
    sig = {"easy": 6, "normal": 2, "hard": 2}
    return [
        ("V0 4차 설정 (182일)", {"days": 182, "pool": V4_POOL, "weekend_pool": OFF}),
        ("V0y 4차 풀로 371일", {"days": 371, "pool": V4_POOL, "weekend_pool": OFF}),
        ("V1 할당 확대 (200/150)", {"days": 371, "pool": big, "weekend_pool": OFF}),
        ("V2 + 유일성 완화 (최적 경로 수 제한 없음)", {"days": 371, "pool": {**big, "max_optimal_paths": None}, "weekend_pool": OFF}),
        ("V3 + 단축 하한 3 → 2", {"days": 371, "pool": {**big, "max_optimal_paths": None, "min_savings": 2}, "weekend_pool": OFF}),
        ("V4 + easy 시그니처 상한 2 → 6", {"days": 371, "pool": {**big, "max_optimal_paths": None, "min_savings": 2, "max_per_signature": sig}, "weekend_pool": OFF}),
        ("V5 + 주말 한국+타이베이 풀 (주말에 섞어 편성)", {"days": 371, "pool": {**big, "max_optimal_paths": None, "min_savings": 2, "max_per_signature": sig},
                                               "weekend_pool": {**wk, "enabled": True}}),
        ("V6 = V5, 주말은 한국+타이베이만", {"days": 371, "pool": {**big, "max_optimal_paths": None, "min_savings": 2, "max_per_signature": sig},
                                       "weekend_pool": {**wk, "enabled": True}, "weekday_rulesets": {"sat": [wk["ruleset"]], "sun": [wk["ruleset"]]}}),
        ("V8 = V6 + 주말 풀 확대 (할당 150/150, 시그니처 상한 6)", {"days": 371, "pool": {**big, "max_optimal_paths": None, "min_savings": 2, "max_per_signature": sig},
                                       "weekend_pool": {**wk, "enabled": True, "quotas": {"shortcut": 150, "crosscity": 150},
                                                        "max_per_signature": {"easy": 6, "normal": 6, "hard": 6}},
                                       "weekday_rulesets": {"sat": [wk["ruleset"]], "sun": [wk["ruleset"]]}}),
        ("V7 = V5에서 유일성 유지 (유일성 완화 효과 분리)", {"days": 371, "pool": {**big, "min_savings": 2, "max_per_signature": sig},
                                                  "weekend_pool": {**wk, "enabled": True, "max_optimal_paths": 1}}),
    ]


def run_variant(name, ov, cfg, g, rows, g2):
    oc = copy.deepcopy(cfg["daily_order"])
    for k in ("days", "pool", "weekend_pool"):
        oc[k] = ov[k]
    for wd, rs in (ov.get("weekday_rulesets") or {}).items():
        oc["weekday"][wd]["rulesets"] = rs
    t = time.time()
    pool, stats, _ = g10.make_pools(g, cfg, oc, "strict", rows, {oc["weekend_pool"].get("ruleset", "tw_t12"): g2})
    pl = Planner(pool, oc, date.fromisoformat(cfg["daily_epoch"]))
    order = pl.local_search(pl.greedy(), max_rounds=oc.get("max_rounds", 12))
    sm = summarize(pl, order)
    by = {p["id"]: p for p in pool}
    sched = [by[i] for i in order]
    L = len(order)
    share = Counter(x for p in sched for x in set(p["warp_portals"]))
    lv = Counter(p["difficulty_calibrated"] for p in pool)
    sav = [p["savings"] for p in sched if p["savings"] is not None]
    row = {"name": name, "days": L, "pool": len(pool), "pool_levels": dict(sorted(lv.items())),
           "pool_weekend": sum(1 for p in pool if p.get("pool") == "weekend"),
           "violations": sm["violations"], "violation_total": sum(sm["violations"].values()),
           "distinct_signatures": sm["distinct_signatures"], "min_signature_gap": sm["min_signature_gap"],
           "mean_jaccard": sm["mean_jaccard_consecutive"], "max_jaccard": sm["max_jaccard_consecutive"],
           "top_portals": [[k, v, round(100 * v / L, 1)] for k, v in ranked(share, 5)],
           "portal_max_in_window": ranked(Counter(sm["portal_max_in_window"]), 1)[0] if sm["portal_max_in_window"] else None,
           "weekday_mean_h": sm["weekday_mean_h"],
           "unique_share": round(sum(1 for p in sched if p["optimal_paths"] == 1) / L, 3),
           "mean_optimal_paths": round(sum(min(p["optimal_paths"], 50) for p in sched) / L, 2),
           "shortcut_mean_savings": round(sum(sav) / len(sav), 2) if sav else None,
           "scheduled_weekend_pool": sum(1 for p in sched if p.get("pool") == "weekend"),
           "search_capped": bool(getattr(pl, "last_search_capped", False)),
           "seconds": round(time.time() - t, 1)}
    print(json.dumps({k: row[k] for k in ("name", "pool", "pool_levels", "violations", "distinct_signatures", "top_portals", "search_capped", "seconds")},
                     ensure_ascii=False), flush=True)
    return row


def main() -> int:
    cfg = yaml.safe_load(open(ROOT / "config" / "game.yaml", encoding="utf-8"))["puzzles"]
    g = ClusterGraph(build_world(*load_base(), load_ruleset("strict")))
    rows = g10.candidate_rows(g)
    g2 = ClusterGraph(build_world(*load_multi(("KR", "TW")), load_ruleset(cfg["daily_order"]["weekend_pool"]["ruleset"])))
    only = sys.argv[1:] or None
    out = []
    for name, ov in variants(cfg["daily_order"]):
        if only and not any(name.startswith(x + " ") for x in only):
            continue
        out.append(run_variant(name, ov, cfg, g, rows, g2))
    path = ROOT / "data" / "processed" / "daily_year_compare.json"
    if only and path.exists():   # 일부 변형만 다시 돌리면 기존 결과에 합친다 (변형 순서 유지)
        old = {r["name"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
        old.update({r["name"]: r for r in out})
        names = [n for n, _ in variants(cfg["daily_order"])]
        out = [old[n] for n in names if n in old]
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(out)
    return 0


def write_report(out):
    L = ["# R1 데일리 1년 일정 — 풀 확대 방법 비교", "",
         "생성: `python3 scripts/r1_compare.py`. 그래프는 strict(한국 T1), 주말 풀은 tw_t12(한국+타이베이 T1+T2)에서 국가 간 워프를 쓰는 대표 경로만.",
         "하드 제약은 4차와 같다: (i) 같은 시그니처 간격 ≥ 14일, (ii) 연속일 포탈 집합 자카드 ≤ 1/3, (iii) 30일 창 포탈당 ≤ 4회, (iv) 요일별 보정 난이도 "
         "(월 easy · 화 easy/normal · 수목 normal · 금 normal/hard · 토일 hard) + ruleset 요일. 위반 수는 쌍·날·(창, 포탈) 단위.",
         "변형은 누적이다 (앞 변형 + 한 가지). 4차 기준만 182일, 나머지는 371일(53주: 어느 365일 구간에서도 반복 없음, 요일 순환 유지).", "",
         "| 변형 | 일정 | 풀 (easy/normal/hard) | 주말 풀 | 위반 (i/ii/iii/iv) | 서로 다른 시그니처 | 연속일 자카드 평균/최대 | 최다 포탈 (일정 비율) | 유일해 비율 | 평균 최적 경로 수 | 단축 평균 | 시간 |",
         "| :- | -: | :- | -: | :- | -: | :- | :- | -: | -: | -: | -: |"]
    for r in out:
        v = r["violations"]
        lv = r["pool_levels"]
        tp = ", ".join(f"{k} {p}%" for k, _, p in r["top_portals"][:3])
        L.append(f"| {r['name']} | {r['days']} | {r['pool']} ({lv.get('easy', 0)}/{lv.get('normal', 0)}/{lv.get('hard', 0)}) | "
                 f"{r['pool_weekend']} (일정 {r['scheduled_weekend_pool']}) | {v['signature']}/{v['jaccard']}/{v['window']}/{v['weekday']} | "
                 f"{r['distinct_signatures']} | {r['mean_jaccard']}/{r['max_jaccard']} | {tp} | {r['unique_share']} | {r['mean_optimal_paths']} | "
                 f"{r['shortcut_mean_savings']} | {r['seconds']}s |")
    L += ["", "### 요일별 평균 난이도 지수 h (= 1 − 직관 점수)", "", "| 변형 | " + " | ".join(WEEKDAYS) + " |", "| :- |" + " -: |" * 7]
    for r in out:
        L.append(f"| {r['name']} | " + " | ".join(str(r["weekday_mean_h"].get(d, "-")) for d in WEEKDAYS) + " |")
    (ROOT / "docs" / "reports" / "r1_daily_year.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
