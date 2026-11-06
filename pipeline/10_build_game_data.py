#!/usr/bin/env python3
"""N5. 게임 데이터 사전 계산.

(a) 최단 루트 퍼즐 후보: 모든 출발·도착 클러스터 쌍에 대해 워프 포함/제외 최단 비용과 워프 포함 최적 경로 개수를
    계산하고, 최적해가 유일하면서 워프 단축 폭이 큰 쌍(같은 권역) + 워프 없이는 못 가는 도시 횡단 쌍을 난이도별로 고른다.
(b) N정류장 최대 거리: 정확히 N턴(승차 1역 = 1턴, 워프 1회 = 1턴, 환승은 턴 아님) 동안 같은 물리적 역을 두 번 밟지 않는
    경로 중 (1) 시작-끝 대권거리 최대, (2) 탑승 구간 거리 합 최대를 각각 상위 K개 (출발·도착 쌍 중복 없이).

쌍은 순서쌍 (출발 → 도착)이다. 6호선 응암순환이 단방향(유향 엣지)이라 d(s,t) ≠ d(t,s)일 수 있다 (3차 A2).
같은 두 역의 정·역방향 퍼즐은 하나만 고른다.
경로 단위는 클러스터(물리적 역) 수준이다. 환승은 클러스터 안에서 비용 0으로 접히므로 '최적 경로 개수'는
물리적 역 순서(+워프)가 다른 경로의 개수다. 같은 두 역 사이를 다른 노선으로 가는 것은 같은 경로로 센다.
환승 비용이 0이 아닌 ruleset이면 이 단계는 거부한다 (클러스터 접힘이 성립하지 않음).

입력: data/processed/kr/{stations,ride_edges,lines}.json, config/game.yaml, ruleset
출력: data/processed/puzzles.json, data/processed/n_stops_max.json, web/data/puzzles.json(웹용 축약본),
      docs/reports/n5_game_data.md
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.game import INF, ClusterGraph, describe_path, intuition_search, n_stops  # noqa: E402,F401
from metro_portal.world import build_world, load_base  # noqa: E402


def difficulty(cfg, cost, warps):
    for level in ("easy", "normal"):
        lim = cfg["difficulty"][level]
        if warps <= lim["max_warps"] and cost <= lim["max_cost"]:
            return level
    return "hard"


def candidate_rows(g):
    """모든 순서쌍 (s, t, 워프 有 비용, 워프 無 비용, 최적 경로 수, 최적 경로 워프 수). 순서쌍이다 (응암순환 유향 엣지, 3차 A2)."""
    rows = []
    for s in range(g.C):
        dw, cw = g.sssp_count(s)
        wp = g.last_warps
        dn = g.bfs_ride(s)
        for t in range(g.C):
            if t == s or dw[t] == INF:
                continue
            rows.append((s, t, dw[t], dn[t], cw[t], wp[t]))
    return rows


def pair_stats(rows, g, cfg, max_optimal=1):
    stats = {"pairs": len(rows),
             "pairs_reachable_without_warp": sum(1 for r in rows if r[3] != INF),
             "pairs_warp_shortens": sum(1 for r in rows if r[3] != INF and r[2] < r[3]),
             "pairs_cross_component": sum(1 for r in rows if r[3] == INF),
             "pairs_unique_optimum": sum(1 for r in rows if r[4] == 1),
             "optimal_count_hist": dict(sorted(Counter(min(r[4], 10) for r in rows).items())),
             }
    # 출발·도착 이름이 같으면(양평→양평) 워프 한 번이 답이라 퍼즐에서 뺀다. 최소 비용도 둔다
    ok = [r for r in rows if r[4] <= max_optimal and cfg["min_cost"] <= r[2] <= cfg["max_cost"] and g.cl[r[0]]["name"] != g.cl[r[1]]["name"]]
    shortcut = [r for r in ok if r[3] != INF and r[2] < r[3] and r[3] - r[2] >= cfg["min_savings"]]
    cross = [r for r in ok if r[3] == INF]
    stats["candidates_shortcut"] = len(shortcut)
    stats["candidates_crosscity"] = len(cross)
    return stats, shortcut, cross


def select(g, cfg, shortcut, cross, quotas, max_sig, max_end, stats=None, rs_name="strict"):
    """등급(난이도)·종류별 흥미도 순 선정. 같은 시그니처는 등급마다 max_sig개, 같은 출발/도착 역은 전체에서 max_end번까지.
    최적해가 여럿인 쌍(완화판)은 역추적 첫 경로를 대표 경로로 쓴다."""
    dist_cache = {}

    def path_of(s, t):
        if s not in dist_cache:
            dist_cache[s] = g.sssp_count(s)[0]
        return g.unique_path(s, t, dist_cache[s])

    out, used_pairs = [], set()
    for kind, rows_k in (("shortcut", shortcut), ("crosscity", cross)):
        by_lvl = {"easy": [], "normal": [], "hard": []}
        for s, t, cw, cn, cnt, warps in rows_k:
            sav = (cn - cw) if cn != INF else None
            # 정렬 키: 단축 폭(같은 권역) 또는 워프 수·비용(도시 횡단)이 클수록 흥미롭다
            key = (-(sav or 0), -(sav / cn if sav else 0), s, t) if kind == "shortcut" else (-warps, -cw, s, t)
            by_lvl[difficulty(cfg, cw, warps)].append((key, s, t, cw, cn, cnt))
        for lvl in ("easy", "normal", "hard"):
            if stats is not None:
                stats[f"pool_{kind}_{lvl}"] = len(by_lvl[lvl])
            used_sig, used_end, picked = Counter(), Counter(), 0
            for _, s, t, cw, cn, cnt in sorted(by_lvl[lvl]):
                if used_end[s] >= max_end or used_end[t] >= max_end:
                    continue
                if (min(s, t), max(s, t)) in used_pairs:  # 같은 두 역의 역방향 퍼즐은 하나만
                    continue
                steps = describe_path(g, path_of(s, t))
                sig = tuple(x["portal"] for x in steps if x["type"] == "warp")
                if used_sig[sig] >= max_sig:
                    continue
                used_sig[sig] += 1
                used_pairs.add((min(s, t), max(s, t)))
                used_end[s] += 1
                used_end[t] += 1
                out.append({"kind": kind, "difficulty": lvl, "from": g.cl[s]["id"], "to": g.cl[t]["id"],
                            "from_label": g.name(s), "to_label": g.name(t),
                            "cost_warp": cw, "cost_no_warp": None if cn == INF else cn,
                            "savings": None if cn == INF else cn - cw, "optimal_paths": cnt, "warps": len(sig),
                            "rides": sum(1 for x in steps if x["type"] == "ride"), "warp_portals": list(sig),
                            # 4차 Q6-5: 퍼즐마다 ruleset을 하나로 고정하고 기록한다
                            "ruleset": rs_name, "optimal": steps})
                picked += 1
                if picked >= quotas[kind]:
                    break
    for i, p in enumerate(out):
        p["id"] = f"P{i + 1:03d}"
    return out


def calibrate(g, cfg, puzzles):
    """3차 난이도 보정 (직관 탐색). 4차부터 데일리 순서의 요일별 난이도(Q2 iv)에 쓴다."""
    cal = cfg["calibration"]
    for p in puzzles:
        ic, ex = intuition_search(g, g.ix[p["from"]], g.ix[p["to"]])
        sc = round(p["cost_warp"] / ic, 3) if ic else 0.0
        p["intuition_cost"], p["intuition_expanded"], p["intuition_score"] = ic, ex, sc
        p["difficulty_calibrated"] = "easy" if sc >= cal["easy_min_score"] else ("normal" if sc >= cal["normal_min_score"] else "hard")


def calibration_stats(puzzles):
    import statistics
    cal = {f"{a}->{b}": sum(1 for p in puzzles if p["difficulty"] == a and p["difficulty_calibrated"] == b)
           for a in ("easy", "normal", "hard") for b in ("easy", "normal", "hard")}
    med = {a: statistics.median([p["intuition_expanded"] for p in puzzles if p["difficulty"] == a] or [0]) for a in ("easy", "normal", "hard")}
    return cal, med


def legacy_order(cfg, puzzles):
    """3차까지의 순서: 시드 고정 셔플 (비교용)."""
    rnd = random.Random(cfg["daily_seed"])
    order = [p["id"] for p in puzzles]
    rnd.shuffle(order)
    return order


def build_puzzles(g, cfg, rs_name="strict", rows=None, locked=None):
    """4차 Q2: 후보 풀 → 보정 난이도 → 제약 기반 데일리 순서. 반환 (풀 퍼즐, 순서, 통계, 비교 자료)."""
    from datetime import date

    from metro_portal.daily_order import Planner, summarize
    rows = rows if rows is not None else candidate_rows(g)
    oc = cfg["daily_order"]
    stats, shortcut, cross = pair_stats(rows, g, cfg)
    pool = select(g, cfg, shortcut, cross, oc["pool_per_kind_per_difficulty"], oc["pool_max_per_warp_signature"],
                  oc["pool_max_per_endpoint"], stats, rs_name)
    calibrate(g, cfg, pool)
    stats["calibration"], stats["calibration_expanded_median"] = calibration_stats(pool)
    epoch = date.fromisoformat(cfg["daily_epoch"])
    if locked:
        key = {(p["from"], p["to"], p["ruleset"]): p["id"] for p in pool}
        missing = [x for x in locked if (x[1], x[2], x[3]) not in key]
        if missing:
            raise SystemExit(f"[10] 고정(append-only) 퍼즐이 새 풀에 없다 — 사람이 확인: {missing[:5]}")
        locked = [key[(x[1], x[2], x[3])] for x in locked]
    pl = Planner(pool, oc, epoch, locked=locked)
    order = pl.local_search(pl.greedy())
    stats["daily_order"] = summarize(pl, order)
    stats["pool_size"] = len(pool)
    # 비교 1: 같은 그래프에서 3차 방식 (작은 선정 + 시드 셔플)
    legacy = select(g, cfg, shortcut, cross, cfg["per_kind_per_difficulty"], cfg["max_per_warp_signature"], cfg["max_per_endpoint"], None, rs_name)
    calibrate(g, cfg, legacy)
    lo = legacy_order(cfg, legacy)
    pl_legacy = Planner(legacy, {**oc, "days": len(lo)}, epoch)
    cmp_ = {"legacy_same_graph": {"pool": len(legacy), **summarize(pl_legacy, lo),
                                  "first_days": [[x for x in next(p for p in legacy if p["id"] == pid)["warp_portals"]] for pid in lo[:7]]}}
    # 비교 2 (Q2-5): 최적해 유일성 완화판 (최적 경로 ≤ relaxed_max_optimal_paths)
    st2, sc2, cr2 = pair_stats(rows, g, cfg, oc["relaxed_max_optimal_paths"])
    pool2 = select(g, cfg, sc2, cr2, oc["pool_per_kind_per_difficulty"], oc["pool_max_per_warp_signature"], oc["pool_max_per_endpoint"], None, rs_name)
    calibrate(g, cfg, pool2)
    pl2 = Planner(pool2, oc, epoch)
    o2 = pl2.local_search(pl2.greedy())
    cmp_["relaxed_unique"] = {"pool": len(pool2), "candidates_shortcut": st2["candidates_shortcut"],
                              "candidates_crosscity": st2["candidates_crosscity"], **summarize(pl2, o2)}
    cmp_["pool_portal_share"] = {
        "unique": dict(Counter(x for p in pool for x in set(p["warp_portals"])).most_common(12)),
        "relaxed": dict(Counter(x for p in pool2 for x in set(p["warp_portals"])).most_common(12))}
    return pool, order, stats, cmp_


def release_lock(pcfg, today=None):
    """4차 Q6-8: 출시(launch_date) 후에는 epoch부터 오늘 + freeze_future_days까지의 퍼즐을 이전 배포본에서 그대로 고정한다.
    퍼즐 id는 빌드마다 다시 매기므로, 이전 배포본의 (출발, 도착, ruleset)으로 새 풀에서 찾는다 (없으면 오류: 사람이 확인)."""
    rel = pcfg.get("daily_release") or {}
    if not rel.get("launch_date"):
        return None
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo
    today = date.fromisoformat(today) if today else datetime.now(ZoneInfo(rel.get("timezone", "Asia/Seoul"))).date()
    if today < date.fromisoformat(rel["launch_date"]):
        return None
    prev = json.loads((ROOT / "web" / "data" / "puzzles.json").read_text(encoding="utf-8"))
    n = (today + timedelta(days=rel["freeze_future_days"]) - date.fromisoformat(prev["daily_epoch"])).days + 1
    byid = {p["id"]: p for p in prev["puzzles"]}
    return [("LOCK", byid[pid]["from"], byid[pid]["to"], byid[pid].get("ruleset", prev["ruleset"]))
            for pid in prev["daily_order"][:max(0, n)]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruleset", default="strict")
    ap.add_argument("--today", default=None, help="append-only 고정 기준 날짜 (기본: 서울 기준 오늘). launch_date 전이면 무시")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "config" / "game.yaml", encoding="utf-8"))
    rs = load_ruleset(a.ruleset)
    if rs["costs"]["transfer"] != 0:
        raise SystemExit("[10] 환승 비용 0인 ruleset만 지원 (클러스터 접힘 전제)")
    w = build_world(*load_base(), rs)
    g = ClusterGraph(w)
    locked = release_lock(cfg["puzzles"], a.today)
    puzzles, order, stats, compare = build_puzzles(g, cfg["puzzles"], rs["name"], locked=locked)
    scheduled = set(order)
    for p in puzzles:
        p["scheduled"] = p["id"] in scheduled
    pz = {"ruleset": rs["name"], "definition": {
        "unit": "클러스터(물리적 역). 환승 비용 0으로 클러스터 안에서 접힘",
        "cost": f"승차 1역 = {rs['costs']['ride']}, 워프 = 포탈 비용(T1 {rs['portals']['T1']['cost']})",
        "optimal_paths": "물리적 역 순서(+워프)가 다른 최단 경로 개수. 같은 구간의 다른 노선은 같은 경로",
        "kinds": {"shortcut": "워프 없이도 갈 수 있지만 워프로 크게 단축되는 쌍 (단축 폭 큰 순)",
                  "crosscity": "워프 없이는 못 가는 쌍 (워프 수·비용 큰 순)"},
        "difficulty": cfg["puzzles"]["difficulty"],
        "epoch": cfg["puzzles"]["daily_epoch"],
        "signature": "최적 경로에 쓰인 포탈 순서 (warp_portals)",
        "difficulty_calibrated": "직관 탐색 점수 = 최적 비용 / 지리 감각 최선 우선 탐색이 찾은 비용. 1.0 = easy, 0.4 이상 = normal, 그 밖 = hard",
        "daily_order": cfg["puzzles"]["daily_order"]},
        "stats": stats, "compare": compare, "daily_order": order, "puzzles": puzzles}
    out = ROOT / "data" / "processed" / "puzzles.json"
    out.write_text(json.dumps(pz, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # 웹용: 일정에 든 퍼즐만. difficulty = 보정 난이도 (요일 곡선 기준), ruleset은 퍼즐마다 기록 (Q6-5)
    web = {"ruleset": rs["name"], "daily_epoch": cfg["puzzles"]["daily_epoch"], "daily_order": order,
           "launch_date": cfg["puzzles"]["daily_release"]["launch_date"],
           "puzzles": [{"id": p["id"], "kind": p["kind"], "difficulty": p["difficulty_calibrated"], "difficulty_rule": p["difficulty"],
                        "from": p["from"], "to": p["to"], "cost_warp": p["cost_warp"], "cost_no_warp": p["cost_no_warp"],
                        "savings": p["savings"], "warps": p["warps"], "ruleset": p["ruleset"]}
                       for p in puzzles if p["scheduled"]]}
    (ROOT / "web" / "data" / "puzzles.json").write_text(json.dumps(web, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[10] puzzles={len(puzzles)} stats={json.dumps(stats, ensure_ascii=False)}")

    ncfg = cfg["n_stops"]
    ns = {"ruleset": rs["name"], "N": ncfg["N"], "definition": {
        "turn": "승차 1역 = 1턴, 워프 1회 = 1턴, 환승은 턴이 아님",
        "path": "정확히 N턴, 같은 물리적 역(클러스터) 재방문 금지",
        "great_circle": "시작·끝 클러스터 좌표의 대권거리",
        "track": "탑승한 인접역 구간 직선거리 합 (실제 선로 길이가 아니라 역 좌표 간 직선거리 근사). 워프 구간은 0"},
        "with_warp": n_stops(g, ncfg["N"], ncfg["top_k"], True),
        "without_warp": n_stops(g, ncfg["N"], ncfg["top_k_no_warp"], False)}
    (ROOT / "data" / "processed" / "n_stops_max.json").write_text(json.dumps(ns, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(pz, ns, g)
    print(f"[10] n_stops N={ncfg['N']}: gc top={ns['with_warp']['great_circle'][0]['value_m']}m "
          f"track top={ns['with_warp']['track'][0]['value_m']}m")
    return 0


def fmt_steps(steps):
    out = []
    for x in steps:
        if x["type"] == "ride":
            out.append(f"{x['from'].split('#')[0]}→{x['to'].split('#')[0]}")
        else:
            out.append(f"⇢[{x['portal']}]⇢")
    # 연속 승차 압축: A→B, B→C → A→B→C
    txt = []
    for s in out:
        if txt and "→" in s and "→" in txt[-1] and not txt[-1].startswith("⇢") and txt[-1].split("→")[-1] == s.split("→")[0]:
            txt[-1] = txt[-1] + "→" + s.split("→")[1]
        else:
            txt.append(s)
    return " ".join(txt)


def write_report(pz, ns, g):
    st = pz["stats"]
    L = ["# N5 게임 데이터 사전 계산", "", "생성: `python3 pipeline/10_build_game_data.py` (설정: `config/game.yaml`)", "",
         "## (a) 최단 루트 퍼즐 후보", "",
         f"- 정의: {pz['definition']['unit']}. 비용 {pz['definition']['cost']}. 최적 경로 개수 = {pz['definition']['optimal_paths']}.",
         "", "| 항목 | 값 |", "| :- | -: |"]
    L += [f"| {k} | {v} |" for k, v in st.items()]
    L += ["", "optimal_count_hist: 워프 포함 최적 경로 개수 분포 (10 = 10개 이상).", "",
          f"선정 결과: {len(pz['puzzles'])}개 → `data/processed/puzzles.json` (웹용 축약본 `web/data/puzzles.json`)", ""]
    cal = st.get("calibration")
    if cal:
        L += ["### 난이도 보정 (3차, 직관 탐색)", "",
              "지리 감각만 가진 플레이어를 흉내 낸 최선 우선 탐색(역의 가치 = 그 역 또는 그 역의 워프 도착지에서 목적지까지 대권거리의 최솟값)으로 풀어 본다.",
              "점수 = 최적 비용 / 직관 탐색이 찾은 비용. 보정 등급: 점수 1.0 = easy, 0.4 이상 = normal, 그 밖 = hard (`config/game.yaml` calibration). 선정·데일리 순서에는 쓰지 않는다.",
              f"규칙 등급별 목적지까지 펼친 역 수 중앙값: " + ", ".join(f"{k} {v}" for k, v in st.get("calibration_expanded_median", {}).items()), "",
              "| 규칙 등급 \\ 보정 등급 | easy | normal | hard |", "| :- | -: | -: | -: |"]
        for a in ("easy", "normal", "hard"):
            L.append(f"| {a} | " + " | ".join(str(cal[f"{a}->{b}"]) for b in ("easy", "normal", "hard")) + " |")
        agree = sum(cal[f"{a}->{a}"] for a in ("easy", "normal", "hard"))
        L += ["", f"일치 {agree}/{sum(cal.values())}. 규칙상 easy인데 직관 탐색이 최적을 못 찾는 퍼즐 (지리 감각과 반대로 가야 하는 워프):", ""]
        tricky = [p for p in pz["puzzles"] if p["difficulty"] == "easy" and p["difficulty_calibrated"] != "easy"]
        L += [f"- {p['id']} {p['from_label']} → {p['to_label']}: 최적 {p['cost_warp']}, 직관 {p['intuition_cost']} (점수 {p['intuition_score']}, 펼친 역 {p['intuition_expanded']})" for p in tricky] or ["없음."]
        L.append("")
    for kind in ("shortcut", "crosscity"):
        L += [f"### {kind} — {pz['definition']['kinds'][kind]}", "",
              "| id | 난이도 | 출발 | 도착 | 워프 有 | 워프 無 | 단축 | 워프 | 최적 경로 |", "| :- | :- | :- | :- | -: | -: | -: | -: | :- |"]
        for p in pz["puzzles"]:
            if p["kind"] != kind:
                continue
            L.append(f"| {p['id']} | {p['difficulty']} | {p['from_label']} | {p['to_label']} | {p['cost_warp']} | "
                     f"{p['cost_no_warp'] if p['cost_no_warp'] is not None else '불가'} | {p['savings'] if p['savings'] is not None else '-'} | "
                     f"{p['warps']} | {fmt_steps(p['optimal'])} |")
        L.append("")
    L += [f"## (b) N정류장 최대 거리 (N={ns['N']})", "",
          f"- 턴: {ns['definition']['turn']}. 경로: {ns['definition']['path']}.",
          f"- 대권거리: {ns['definition']['great_circle']}. 구간 거리 합: {ns['definition']['track']}.", ""]
    for key, title in (("great_circle", "시작-끝 대권거리 최대"), ("track", "탑승 구간 거리 합 최대")):
        L += [f"### {title} — 워프 허용 상위 {len(ns['with_warp'][key])}", "",
              "| 순위 | 값(km) | 시작 | 끝 | 워프 | 대권(km) | 구간 합(km) | 경로 |", "| -: | -: | :- | :- | -: | -: | -: | :- |"]
        for i, r in enumerate(ns["with_warp"][key], 1):
            route = " ".join(("⇢" if x["via"] == "warp" else ("" if x["via"] == "start" else "→")) + x["label"].split(" ", 1)[1].split("#")[0]
                             for x in r["path"])
            L.append(f"| {i} | {r['value_m'] / 1000:.1f} | {r['start_label']} | {r['end_label']} | {r['warps']} | "
                     f"{r['great_circle_m'] / 1000:.1f} | {r['track_m'] / 1000:.1f} | {route} |")
        L += ["", f"워프 금지 상위 {len(ns['without_warp'][key])} (비교):", "",
              "| 순위 | 값(km) | 시작 | 끝 |", "| -: | -: | :- | :- |"]
        L += [f"| {i} | {r['value_m'] / 1000:.1f} | {r['start_label']} | {r['end_label']} |" for i, r in enumerate(ns["without_warp"][key], 1)]
        L.append("")
    (ROOT / "docs" / "reports" / "n5_game_data.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
