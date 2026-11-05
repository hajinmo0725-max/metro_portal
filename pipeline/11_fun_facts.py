#!/usr/bin/env python3
"""N7. 짤 소재 통계: 그래프 지름 경로, 포탈 허브 순위(차수·매개 중심성), 웃긴 워프 경로, 전국 중심역 등.

입력: data/processed/kr/{stations,ride_edges,lines}.json, data/processed/n_stops_max.json, ruleset(기본 strict)
출력: data/processed/fun_facts.json, docs/reports/fun_facts.md
클러스터(물리적 역) 수준, 환승 비용 0 ruleset 전제 (metro_portal/game.py).
"""
from __future__ import annotations

import argparse
import heapq
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.game import INF, ClusterGraph, describe_path  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base  # noqa: E402


def brandes(g):
    """가중 Brandes 매개 중심성. 출발·도착은 클러스터만 센다 (포탈 노드는 경유만). 순서쌍 기준 합.
    3차 A2부터 유향 엣지가 있어 순서쌍 그대로 쓴다 (2차까지는 /2 해서 무순서쌍 기준으로 보고했다)."""
    n = g.C + g.P
    bc = [0.0] * n
    for s in range(g.C):
        dist = [INF] * n
        sigma = [0.0] * n
        preds = [[] for _ in range(n)]
        dist[s], sigma[s] = 0, 1.0
        order = []
        pq = [(0, 1, s)]
        done = [False] * n
        while pq:
            d, _, u = heapq.heappop(pq)
            if done[u]:
                continue
            done[u] = True
            order.append(u)
            for v, c in g.adj[u]:
                nd = d + c
                if nd < dist[v]:
                    dist[v], sigma[v], preds[v] = nd, sigma[u], [u]
                    heapq.heappush(pq, (nd, 0 if v >= g.C else 1, v))
                elif nd == dist[v]:
                    sigma[v] += sigma[u]
                    preds[v].append(u)
        delta = [0.0] * n
        for w in reversed(order):
            coeff = ((1.0 if w < g.C else 0.0) + delta[w]) / sigma[w]
            for v in preds[w]:
                delta[v] += sigma[v] * coeff
            if w != s:
                bc[w] += delta[w]
    return bc


def city_of(c):
    return "/".join(c["cities"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruleset", default="strict")
    a = ap.parse_args()
    rs = load_ruleset(a.ruleset)
    if rs["costs"]["transfer"] != 0:
        raise SystemExit("[11] 환승 비용 0 ruleset만 지원")
    w = build_world(*load_base(), rs)
    g = ClusterGraph(w)
    C = g.C
    lab = g.name

    # 전쌍 최단 비용 (워프 有/無), 최적 경로 개수, 워프 수
    D = []
    DN = []
    CNT = []
    WP = []
    for s in range(C):
        d, cnt = g.sssp_count(s)
        D.append(d[:C])
        CNT.append(cnt[:C])
        WP.append(g.last_warps[:C])
        DN.append(g.bfs_ride(s))
    facts = {"ruleset": rs["name"]}

    # 1. 지름 (워프 있음) + 경로
    best = max(((D[s][t], s, t) for s in range(C) for t in range(C) if t != s and D[s][t] != INF), key=lambda x: (x[0], -x[1], -x[2]))
    dia, s0, t0 = best
    d0, _ = g.sssp_count(s0)
    p0 = g.unique_path(s0, t0, d0)
    facts["diameter"] = {"cost": dia, "from": lab(s0), "to": lab(t0), "optimal_paths": CNT[s0][t0],
                         "steps": describe_path(g, p0), "cost_no_warp": DN[s0][t0]}
    # 도시가 다른 쌍 중 가장 먼 쌍
    xc = max(((D[s][t], s, t) for s in range(C) for t in range(C)
              if t != s and D[s][t] != INF and set(g.cl[s]["cities"]).isdisjoint(g.cl[t]["cities"])), key=lambda x: (x[0], -x[1], -x[2]))
    d1, _ = g.sssp_count(xc[1])
    facts["farthest_cross_city"] = {"cost": xc[0], "from": lab(xc[1]), "to": lab(xc[2]), "optimal_paths": CNT[xc[1]][xc[2]],
                                    "steps": describe_path(g, g.unique_path(xc[1], xc[2], d1))}

    # 2. 포탈 허브: 차수, 매개 중심성(이 포탈을 지나는 최단 경로 비중), 거리
    bc = brandes(g)
    pairs_total = sum(1 for s in range(C) for t in range(C) if t != s and D[s][t] != INF)
    hubs = []
    for j, p in enumerate(g.portals):
        cl = [g.cl[g.ix[c]] for c in p["cluster_ids"]]
        far = max(haversine_m(x["lat"], x["lon"], y["lat"], y["lon"]) for x in cl for y in cl if x is not y)
        hubs.append({"portal": p["name"], "degree": p["degree"], "betweenness_pairs": round(bc[C + j], 1),
                     "betweenness_share": round(bc[C + j] / pairs_total, 4),
                     "cities": [city_of(x) for x in cl], "max_span_km": round(far / 1000, 1)})
    hubs.sort(key=lambda h: (-h["betweenness_pairs"], h["portal"]))
    facts["portal_hubs"] = hubs
    facts["pairs_total"] = pairs_total
    st_bc = sorted(((bc[i], i) for i in range(C)), key=lambda x: (-x[0], x[1]))[:10]
    facts["station_hubs"] = [{"station": lab(i), "betweenness_pairs": round(v, 1), "share": round(v / pairs_total, 4)} for v, i in st_bc]

    # 3. 웃긴 워프 경로
    # 3a. 같은 도시 안 이동인데 최적해(유일)가 다른 도시를 경유 — 단축 폭 큰 순, 경유 도시 조합별 1개
    detour = []
    for s in range(C):
        for t in range(C):
            if t == s or CNT[s][t] != 1 or DN[s][t] == INF or D[s][t] >= DN[s][t] or WP[s][t] < 2:
                continue
            if g.cl[s]["cities"] != g.cl[t]["cities"] or g.cl[s]["name"] == g.cl[t]["name"]:
                continue
            detour.append((DN[s][t] - D[s][t], s, t))
    detour.sort(key=lambda x: (-x[0], x[1], x[2]))
    seen_via, funny_detour = set(), []
    for sav, s, t in detour:
        ds, _ = g.sssp_count(s)
        steps = describe_path(g, g.unique_path(s, t, ds))
        via = tuple(sorted({city_of(g.cl[g.ix[x["to"]]]) for x in steps} - set(g.cl[s]["cities"])))
        if not via or via in seen_via:
            continue
        seen_via.add(via)
        funny_detour.append({"from": lab(s), "to": lab(t), "cost": D[s][t], "cost_no_warp": DN[s][t], "savings": sav,
                             "via_cities": list(via), "steps": steps})
        if len(funny_detour) >= 6:
            break
    facts["same_city_via_other_city"] = funny_detour
    # 3b. 최적해(유일)에 워프가 가장 많은 쌍
    mw = max(WP[s][t] for s in range(C) for t in range(C) if t != s and CNT[s][t] == 1 and D[s][t] != INF)
    mwp = sorted((D[s][t], s, t) for s in range(C) for t in range(C) if t != s and CNT[s][t] == 1 and WP[s][t] == mw)
    ds, _ = g.sssp_count(mwp[0][1])
    facts["most_warps"] = {"warps": mw, "pairs": len(mwp), "example": {"from": lab(mwp[0][1]), "to": lab(mwp[0][2]), "cost": mwp[0][0],
                                                                      "steps": describe_path(g, g.unique_path(mwp[0][1], mwp[0][2], ds))}}
    # 3c. 워프 단축 폭 최대 (같은 권역, 최적해 개수 무관)
    sv = max(((DN[s][t] - D[s][t], s, t) for s in range(C) for t in range(C) if t != s and DN[s][t] != INF), key=lambda x: (x[0], -x[1], -x[2]))
    ds, _ = g.sssp_count(sv[1])
    facts["max_savings"] = {"savings": sv[0], "from": lab(sv[1]), "to": lab(sv[2]), "cost": D[sv[1]][sv[2]], "cost_no_warp": DN[sv[1]][sv[2]],
                            "optimal_paths": CNT[sv[1]][sv[2]], "steps": describe_path(g, g.unique_path(sv[1], sv[2], ds))}

    # 4. 전국 중심역 (평균 최단 비용 최소, 워프 있음)과 워프 없을 때 수도권 중심역
    clo = sorted(((sum(D[s][t] for t in range(C) if t != s) / (C - 1), s) for s in range(C)), key=lambda x: (x[0], x[1]))
    facts["center_with_warp"] = [{"station": lab(s), "mean_cost": round(v, 2)} for v, s in clo[:5]]
    facts["edge_with_warp"] = [{"station": lab(s), "mean_cost": round(v, 2)} for v, s in clo[-3:][::-1]]
    big = [s for s in range(C) if DN[0][s] != INF] if DN[0][0] == 0 else []
    comp = max((set(t for t in range(C) if DN[s][t] != INF) for s in range(C)), key=len)
    clo_n = sorted(((sum(DN[s][t] for t in comp if t != s) / (len(comp) - 1), s) for s in sorted(comp)), key=lambda x: (x[0], x[1]))
    facts["center_without_warp"] = [{"station": lab(s), "mean_cost": round(v, 2)} for v, s in clo_n[:5]]
    del big

    # 5. 도시 간 평균 최단 비용 (워프 있음)
    cities = sorted({city_of(c) for c in g.cl})
    mat = defaultdict(list)
    for s in range(C):
        for t in range(C):
            if s != t and D[s][t] != INF:
                mat[(city_of(g.cl[s]), city_of(g.cl[t]))].append(D[s][t])
    facts["city_matrix"] = {"cities": cities, "mean": {f"{a}->{b}": round(sum(v) / len(v), 1) for (a, b), v in sorted(mat.items())},
                            "min": {f"{a}->{b}": min(v) for (a, b), v in sorted(mat.items())}}
    # 6. 포탈 거리 극단
    facts["portal_span"] = {"farthest": sorted(hubs, key=lambda h: (-h["max_span_km"], h["portal"]))[:3],
                            "nearest": sorted(hubs, key=lambda h: (h["max_span_km"], h["portal"]))[:3]}
    # 7. 13정류장
    ns = json.loads((ROOT / "data" / "processed" / "n_stops_max.json").read_text(encoding="utf-8"))
    facts["n_stops"] = {"N": ns["N"], "great_circle_top": ns["with_warp"]["great_circle"][0], "track_top": ns["with_warp"]["track"][0],
                        "great_circle_no_warp_top": ns["without_warp"]["great_circle"][0]}
    facts["optimal_count_max"] = max((CNT[s][t], lab(s), lab(t)) for s in range(C) for t in range(C) if t != s and D[s][t] != INF)
    hist = Counter()
    for s in range(C):
        for t in range(C):
            if t != s and D[s][t] != INF:
                hist[WP[s][t] if CNT[s][t] == 1 else -1] += 1
    facts["unique_pairs_by_warps"] = {str(k): v for k, v in sorted(hist.items()) if k >= 0}
    (ROOT / "data" / "processed" / "fun_facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_md(facts, g)
    print(f"[11] diameter={dia} hubs_top={hubs[0]['portal']} most_warps={mw}")
    return 0


def route_txt(steps, start_label):
    out = [start_label]
    for x in steps:
        name = x["to"].split("#")[0]
        if x["type"] == "warp":
            out.append(f"⇢[{x['portal']}]⇢ {name}")
        else:
            out.append(f"→ {name}")
    return " ".join(out)


def write_md(f, g):
    def lab_id(cid):
        return g.name(g.ix[cid])
    L = ["# 지하철 워프 fun facts (짤 소재)", "",
         f"생성: `python3 pipeline/11_fun_facts.py` (ruleset `{f['ruleset']}`: T1 포탈, 환승 판정 500m, 승차 1·워프 1·환승 0). "
         "숫자는 전부 '수'(승차 1역 = 1수, 워프 1번 = 1수) 단위. 데이터: 레일포털 표준데이터 + 보정, 노선 순서 일부는 검증 중.", ""]
    d = f["diameter"]
    via = sorted({city_of(g.cl[g.ix[x["to"]]]) for x in d["steps"]} - {d["from"].split(" ")[0]})
    nw = sum(1 for x in d["steps"] if x["type"] == "warp")
    if nw:
        cap = (f"전국을 워프로 이어 놔도 제일 먼 두 역은 같은 수도권의 끝과 끝이다. 그런데 그 최단 경로가 **{'·'.join(via)} 찍고 온다** "
               f"(워프 {nw}번). 워프 없이 가면 {d['cost_no_warp']}수라 줄인 건 고작 {d['cost_no_warp'] - d['cost']}수.")
    else:
        cap = f"워프 없이도 {d['cost_no_warp']}수. 이 구간은 워프가 아무 도움이 안 된다."
    L += ["## 1. 전국에서 가장 먼 두 역 (그래프 지름)", "",
          f"**{d['from']} → {d['to']} = {d['cost']}수.** {cap}", "",
          f"> {route_txt(d['steps'], d['from'])}", "",
          f"같은 수로 가는 최단 경로: {d['optimal_paths']}개."]
    x = f["farthest_cross_city"]
    L += ["", f"도시가 다른 두 역 중 가장 먼 쌍: **{x['from']} → {x['to']} = {x['cost']}수** (최적 경로 {x['optimal_paths']}개)", "",
          f"> {route_txt(x['steps'], x['from'])}", ""]
    L += ["## 2. 포탈 허브 순위", "",
          f"매개 중심성 = 전국 연결된 역 순서쌍(출발 → 도착) {f['pairs_total']:,}개의 최단 경로 중 이 포탈을 지나는 비중 (최단 경로가 여럿이면 나눠서 셈). "
          "응암순환이 단방향이라 3차부터 순서쌍 기준이다 (2차는 무순서쌍).", "",
          "| 순위 | 포탈 | 차수 | 지나는 쌍(기대값) | 비중 | 연결 도시 | 최대 거리(km) |", "| -: | :- | -: | -: | -: | :- | -: |"]
    for i, h in enumerate(f["portal_hubs"][:15], 1):
        L.append(f"| {i} | {h['portal']} | {h['degree']} | {h['betweenness_pairs']:,.0f} | {h['betweenness_share']:.1%} | {', '.join(h['cities'])} | {h['max_span_km']} |")
    top = f["portal_hubs"][0]
    low = ", ".join("{}({:.2%})".format(h["portal"], h["betweenness_share"]) for h in f["portal_hubs"][-3:])
    L += ["", f"한 줄 요약: **전국 최단 경로의 {top['betweenness_share']:.0%}가 '{top['portal']}' 포탈을 지난다.** "
          f"꼴찌권: {low}.", "",
          "역(클러스터) 매개 중심성 상위 10 — 전국 최단 경로가 가장 많이 지나는 역:", "",
          "| 순위 | 역 | 지나는 쌍(기대값) | 비중 |", "| -: | :- | -: | -: |"]
    L += [f"| {i} | {s['station']} | {s['betweenness_pairs']:,.0f} | {s['share']:.1%} |" for i, s in enumerate(f["station_hubs"], 1)]
    L += ["", "## 3. 웃긴 워프 경로", "", "### 3-1. 같은 도시 안에서 이동하는데 다른 도시를 찍고 오는 게 최단 (최적해 유일)", ""]
    for r in f["same_city_via_other_city"]:
        L += [f"- **{r['from']} → {r['to']}**: {r['cost']}수 (워프 없으면 {r['cost_no_warp']}수, {r['savings']}수 단축) · 경유 {', '.join(r['via_cities'])}",
              f"  > {route_txt(r['steps'], r['from'])}"]
    m = f["max_savings"]
    L += ["", "### 3-2. 워프 단축 폭 최대", "",
          f"**{m['from']} → {m['to']}**: 워프 없으면 {m['cost_no_warp']}수, 워프로 {m['cost']}수. **{m['savings']}수 절약.** (최적 경로 {m['optimal_paths']}개)", "",
          f"> {route_txt(m['steps'], m['from'])}", ""]
    mw = f["most_warps"]
    L += ["### 3-3. 워프를 가장 많이 타야 하는 최단 경로 (최적해 유일)", "",
          f"워프 **{mw['warps']}번**이 필요한 쌍이 {mw['pairs']}개. 예: **{mw['example']['from']} → {mw['example']['to']}** ({mw['example']['cost']}수)", "",
          f"> {route_txt(mw['example']['steps'], mw['example']['from'])}", "",
          "최적해가 유일한 쌍의 워프 수 분포: " + ", ".join(f"{k}번 {v:,}쌍" for k, v in f["unique_pairs_by_warps"].items()), ""]
    L += ["### 3-4. 밈 원조", "",
          "- 강남 → 교대 ⇢ 부산 교대 → 동래 = **3수** (워프 없으면 불가)",
          "- '시청'은 서울·대전·부산 세 도시를 잇는 차수 3 포탈. '교대'는 서울·대구·부산.",
          "- 같은 도시 포탈: 양평(5호선 ↔ 경의중앙선, 53.6km), 좌천(부산 1호선 ↔ 동해선, 26.3km), 신촌(2호선 ↔ 경의중앙선, 0.7km), 동래(1·4호선 ↔ 동해선, 1.4km)", ""]
    ps = f["portal_span"]
    L += ["## 4. 같은 이름, 다른 세상", "",
          "가장 먼 동명역 포탈: " + "; ".join(f"**{h['portal']}** {h['max_span_km']}km ({', '.join(h['cities'])})" for h in ps["farthest"]),
          "", "가장 가까운 동명역 포탈 (걸어가도 되는 워프): " + "; ".join(f"**{h['portal']}** {h['max_span_km']}km" for h in ps["nearest"]), ""]
    L += ["## 5. 전국 중심역", "",
          "워프 있음, 다른 모든 역까지 평균 수가 가장 적은 역:", ""]
    L += [f"{i}. {c['station']} — 평균 {c['mean_cost']}수" for i, c in enumerate(f["center_with_warp"], 1)]
    L += ["", "가장 외진 역 (평균 수 최대): " + ", ".join(f"{c['station']}({c['mean_cost']})" for c in f["edge_with_warp"]), "",
          "워프 없을 때 수도권 중심역: " + ", ".join(f"{c['station']}({c['mean_cost']})" for c in f["center_without_warp"][:3]), ""]
    cm = f["city_matrix"]
    L += ["## 6. 도시 간 평균 수 (워프 있음)", "", "| 출발 \\ 도착 | " + " | ".join(cm["cities"]) + " |",
          "| :- | " + " | ".join("-:" for _ in cm["cities"]) + " |"]
    for a in cm["cities"]:
        L.append(f"| {a} | " + " | ".join(str(cm["mean"].get(f"{a}->{b}", "-")) for b in cm["cities"]) + " |")
    ns = f["n_stops"]
    gc, tr = ns["great_circle_top"], ns["track_top"]
    L += ["", f"## 7. {ns['N']}정류장 챌린지 기록", "",
          f"- 시작-끝 직선거리 최대: **{gc['value_m'] / 1000:.1f}km** ({gc['start_label']} → {gc['end_label']}, 워프 {gc['warps']}번). "
          f"워프 없으면 최대 {ns['great_circle_no_warp_top']['value_m'] / 1000:.1f}km",
          "  > " + " ".join(("⇢" if p["via"] == "warp" else ("" if p["via"] == "start" else "→ ")) + p["label"].split(" ", 1)[1].split("#")[0] for p in gc["path"]),
          f"- 탄 구간 거리 합 최대: **{tr['value_m'] / 1000:.1f}km** ({tr['start_label']} → {tr['end_label']}, 워프 {tr['warps']}번)", ""]
    oc = f["optimal_count_max"]
    L += ["## 8. 기타", "", f"- 최단 경로가 가장 많은 쌍: {oc[1]} → {oc[2]}, 최단 경로 {oc[0]:,}개 (같은 수로 가는 길이 이만큼)",
          f"- 연결된 역 순서쌍 {f['pairs_total']:,}개 중 최적해가 유일한 쌍 {sum(f['unique_pairs_by_warps'].values()):,}개", ""]
    (ROOT / "docs" / "reports" / "fun_facts.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    del lab_id


if __name__ == "__main__":
    sys.exit(main())
