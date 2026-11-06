#!/usr/bin/env python3
"""3차 B3. 한국 + 타이베이 통합 그래프를 ruleset별(T1 / T1+T2 / T1+T2+T3, 참고용 라벨 변형)로 빌드하고
등급별 국가 간 포탈 목록, DESIGN 6장 지표, 허브 폭발 여부를 비교한다.

입력: data/processed/{kr,tw}/*.json, config/world_compare.yaml, config/rulesets/tw_*.yaml, data/raw/unihan (T2)
출력: data/processed/world/<ruleset>/{clusters,portals,metrics}.json, data/processed/world/compare.json,
      docs/reports/b3_world_rulesets.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.metrics import compute_metrics  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_multi  # noqa: E402

OUT = ROOT / "data" / "processed" / "world"


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def label(s):
    return f"{s.get('country', 'KR')}:{s['name_ko']}[{s['line_name']}]"


def unfolded_keys(p, rs):
    """포탈 원문을 등급 정규화만 하고(이체자 접기 전) 모은 집합. 2개 이상이면 이체자 접기 덕에 맞은 포탈."""
    from metro_portal.graph import tier_normalize
    from metro_portal.normalize import normalize_name
    t = rs["portals"][p["tier"]]
    tn = tier_normalize(t, rs["normalize"])
    return sorted({normalize_name(x, tn) for x in p.get("texts", [])})


def kr_dist(w, rs):
    """한국 클러스터 → 한국 클러스터 최단 비용 (클러스터 수준, 환승 0 접힘). 국가 간 포탈의 국내 우회 효과 측정용."""
    from metro_portal.metrics import cluster_graph, sssp
    g = cluster_graph(w["clusters"], w["edges"], w["portals"], rs, True)
    kr = sorted(c["id"] for c in w["clusters"] if c["countries"] == ["KR"])
    return kr, {s: {t: d for t, d in sssp(g, s).items() if t in set(kr)} for s in kr}, g


def path_of(g, s, t):
    import heapq
    dist, prev, pq = {s: 0}, {s: None}, [(0, s)]
    while pq:
        d, x = heapq.heappop(pq)
        if d > dist[x]:
            continue
        if x == t:
            break
        for y, c in g.get(x, ()):
            if d + c < dist.get(y, float("inf")):
                dist[y], prev[y] = d + c, x
                heapq.heappush(pq, (d + c, y))
    out = [t]
    while prev[out[-1]] is not None:
        out.append(prev[out[-1]])
    return out[::-1]


def run(rs_name, countries):
    rs = load_ruleset(rs_name)
    st, ed, ln = load_multi(countries)
    w = build_world(st, ed, ln, rs)
    m = compute_metrics(st, ed, ln, w["clusters"], w["portals"], w["adj"], rs)
    cm = {c["id"]: c for c in w["clusters"]}
    sm = {s["id"]: s for s in st}
    plist = []
    for p in w["portals"]:
        ctry = sorted({c for cid in p["cluster_ids"] for c in cm[cid]["countries"]})
        uk = unfolded_keys(p, rs)
        plist.append({"tier": p["tier"], "name": p["name"], "texts": p.get("texts", []), "degree": p["degree"], "cost": p["cost"],
                      "countries": ctry, "cross_country": len(ctry) > 1,
                      "stations": sorted({label(sm[x]) for x in p["station_ids"]}),
                      "unfolded_keys": uk, "variant_only": p["tier"] == "T2" and len(uk) > 1})
    # 국가 간 연결: 워프 有 그래프에서 KR 클러스터와 TW 클러스터가 같은 약연결 컴포넌트에 있나
    comp_countries = []
    from metro_portal.metrics import cluster_graph, components
    g = cluster_graph(w["clusters"], ed, w["portals"], rs, True)
    for comp in components(g, set(g)):
        cs = sorted({c for n in comp if n in cm for c in cm[n]["countries"]})
        if cs:
            comp_countries.append(cs)
    dump(OUT / rs_name / "clusters.json", {"ruleset": rs_name, "clusters": w["clusters"]})
    dump(OUT / rs_name / "portals.json", {"ruleset": rs_name, "portals": w["portals"], "capped": w["capped"]})
    dump(OUT / rs_name / "metrics.json", m)
    kr, dkr, g = kr_dist(w, rs)
    return {"ruleset": rs_name, "description": rs.get("description", ""), "metrics": m, "portals": plist, "_kr": (kr, dkr, g, cm),
            "subsumed": [{"tier": p["tier"], "name": p["name"], "texts": p.get("texts", []), "degree": p["degree"]}
                         for p in w["capped"] if p.get("subsumed")],
            "countries_connected": any(len(c) > 1 for c in comp_countries),
            "components_by_country": [c for c in comp_countries][:10]}


def shortened(base, r):
    """기준(tw_t1, 사실상 한국만)보다 한국 내 순서쌍 최단 비용이 줄어든 쌍 수와 최대 단축 예시 경로."""
    kr, db, _, _ = base["_kr"]
    _, dr, g, cm = r["_kr"]
    n, best = 0, None
    pairs = 0
    for s in kr:
        for t in kr:
            if s == t or t not in db[s]:
                continue
            pairs += 1
            if dr[s].get(t, float("inf")) < db[s][t]:
                n += 1
                gain = db[s][t] - dr[s][t]
                if best is None or (gain, -dr[s][t]) > (best[0], -best[3]) or ((gain, -dr[s][t]) == (best[0], -best[3]) and (s, t) < (best[1], best[2])):
                    best = (gain, s, t, dr[s][t])
    ex = None
    if best:
        gain, s, t, d = best
        nodes = path_of(g, s, t)
        steps = []
        for x in nodes:
            if x.startswith("P:"):
                steps.append(f"⇢[{x.split(':', 2)[2]}]")
            else:
                c = cm[x]
                steps.append(f"{'/'.join(c['countries'])}:{c['name']}")
        ex = {"from": s, "to": t, "before": db[s][t], "after": d, "gain": gain, "path": " → ".join(steps)}
    return {"pairs": pairs, "shortened": n, "example": ex}


def judge(r, base, cfg):
    hx = cfg["hub_explosion"]
    reasons = []
    hi = [p for p in r["portals"] if p["tier"] in ("T2", "T3") and p["degree"] >= hx["degree_alert"]]
    if hi:
        reasons.append(f"T2·T3 포탈 차수 ≥ {hx['degree_alert']}: " + ", ".join(f"{p['name']}({p['degree']})" for p in hi))
    if base:
        nb, nr = base["metrics"]["counts"]["portals_total"], r["metrics"]["counts"]["portals_total"]
        if nb and nr / nb >= hx["portal_growth_ratio"]:
            reasons.append(f"포탈 수 {nb} → {nr} (×{nr / nb:.2f})")
        db, dr = base["metrics"]["with_warp"]["diameter"], r["metrics"]["with_warp"]["diameter"]
        same_scope = base["metrics"]["with_warp"]["largest_component_size"] == r["metrics"]["with_warp"]["largest_component_size"]
        if same_scope and db["value"] and (db["value"] - dr["value"]) / db["value"] >= hx["diameter_drop_ratio"]:
            reasons.append(f"지름 {db['value']} → {dr['value']}")
    return {"explosion": bool(reasons), "reasons": reasons}


def main() -> int:
    cfg = yaml.safe_load(open(ROOT / "config" / "world_compare.yaml", encoding="utf-8"))
    res = {}
    for name in cfg["rulesets"] + cfg["reference_rulesets"]:
        res[name] = run(name, cfg["countries"])
        print(f"[17] {name}: portals={res[name]['metrics']['counts']['portals_by_tier']} "
              f"cross={sum(p['cross_country'] for p in res[name]['portals'])} connected={res[name]['countries_connected']}")
    base0 = res[cfg["rulesets"][0]]
    for group in (cfg["rulesets"], cfg["reference_rulesets"]):
        base = res[group[0]]
        for name in group:
            res[name]["judge"] = judge(res[name], base if name != group[0] else None, cfg)
            res[name]["kr_shortened"] = shortened(base0, res[name])
    for v in res.values():
        v.pop("_kr")
    slim = {k: {kk: vv for kk, vv in v.items() if kk not in ("metrics",)} | {"metrics_summary": summary(v["metrics"])} for k, v in res.items()}
    dump(OUT / "compare.json", {"config": cfg, "results": slim})
    write_report(cfg, res)
    return 0


def summary(m):
    c, w, n = m["counts"], m["with_warp"], m["without_warp"]
    return {"stations": c["stations"], "clusters": c["clusters"], "ride_edges": c["ride_edges"], "portals_total": c["portals_total"],
            "portals_by_tier": c["portals_by_tier"], "portal_links": c["portal_links"],
            "components_warp": w["components"], "largest_warp": w["largest_component_size"], "ratio_warp": w["largest_component_ratio"],
            "diameter_warp": w["diameter"]["value"], "diameter_warp_ends": f"{w['diameter']['from']} → {w['diameter']['to']}",
            "mean_warp": w["diameter"]["mean_cost"], "components_nowarp": n["components"], "diameter_nowarp": n["diameter"]["value"],
            "top_portals": m["top_portals"][:5]}


def write_report(cfg, res):
    names = cfg["rulesets"] + cfg["reference_rulesets"]
    L = ["# B3 한국 + 타이베이 통합 그래프 — ruleset 비교", "",
         "생성: `python3 pipeline/17_compare_world_rulesets.py` (설정 `config/world_compare.yaml`, 룰 `config/rulesets/tw_*.yaml`)", "",
         "- 기본 3종(`tw_t1`, `tw_t12`, `tw_t123`)은 **공식명만** 쓴다 (사용자 지시). 타이베이는 공식명 소스가 막혀(Wikidata P1448 0건) 매칭 이름이 없다.",
         "- 참고 3종(`*_label`)은 타이베이 이름으로 Wikidata 라벨(커뮤니티 표기)을 허용한 실험이다. **공식명이 아니다.**",
         "- 비용: 승차 1, 환승 0, 워프 T1 1·T2 2·T3 3. 환승 판정은 3차 공식 우선 규칙(타이베이는 공식 환승 정보가 없어 거리 D=500).",
         "- 한국 쪽 T2 = 표준데이터 한자역사명, T3 = 표준데이터 영문역사명. 같은 클러스터 집합을 더 싼 등급이 이미 잇고 있으면 비싼 등급 포탈은 만들지 않는다(dedupe).", "",
         "## 지표 (DESIGN 6장)", "",
         "| ruleset | 역 | 클러스터 | 승차 엣지 | 포탈 (등급별) | 포탈 연결 | 워프 有 컴포넌트 | 최대 컴포넌트 | 지름 (양 끝) | 평균 비용 | 워프 無 컴포넌트 | 워프 無 지름 | 국가 간 연결 | 중복으로 생략 |",
         "| :- | -: | -: | -: | :- | -: | -: | :- | :- | -: | -: | -: | :- | -: |"]
    for n in names:
        s = summary(res[n]["metrics"])
        L.append(f"| `{n}` | {s['stations']} | {s['clusters']} | {s['ride_edges']} | {', '.join(f'{k} {v}' for k, v in s['portals_by_tier'].items())} | "
                 f"{s['portal_links']} | {s['components_warp']} | {s['largest_warp']} ({s['ratio_warp']:.1%}) | {s['diameter_warp']} ({s['diameter_warp_ends']}) | "
                 f"{s['mean_warp']} | {s['components_nowarp']} | {s['diameter_nowarp']} | {'예' if res[n]['countries_connected'] else '아니오'} | {len(res[n]['subsumed'])} |")
    L += ["", "지름·평균은 워프 有 그래프의 최대 컴포넌트 기준이다. 국가 간 포탈이 없으면 최대 컴포넌트는 한국이라 지름이 한국 값과 같다.", "",
          "## 허브 폭발 판정", "",
          f"기준 (`config/world_compare.yaml`): T2·T3 포탈 차수 ≥ {cfg['hub_explosion']['degree_alert']}, 포탈 수 ×{cfg['hub_explosion']['portal_growth_ratio']} 이상, "
          f"같은 연결 범위에서 지름 {cfg['hub_explosion']['diameter_drop_ratio']:.0%} 이상 감소 중 하나라도 해당하면 의심. 각 그룹의 첫 ruleset(T1만)이 기준.", "",
          "| ruleset | 판정 | 근거 | 등급별 최대 차수 |", "| :- | :- | :- | :- |"]
    for n in names:
        j = res[n]["judge"]
        mx = {}
        for p in res[n]["portals"]:
            mx[p["tier"]] = max(mx.get(p["tier"], 0), p["degree"])
        L.append(f"| `{n}` | {'**폭발 의심**' if j['explosion'] else '정상'} | {'; '.join(j['reasons']) or '-'} | {', '.join(f'{k} {v}' for k, v in sorted(mx.items()))} |")
    L += ["", "## 국내 우회 효과 — 한국 내 순서쌍 중 `tw_t1`보다 최단 비용이 줄어든 쌍", "",
          "국가 간 포탈이 생기면 한국 두 역 사이 최단 경로가 타이베이를 거쳐 짧아질 수 있다. 같은 나라 T2·T3 포탈(대치↔대티, 성남↔석남)도 국내 단축을 만든다.", "",
          "| ruleset | 단축된 쌍 / 한국 내 쌍 | 최대 단축 예시 |", "| :- | :- | :- |"]
    for n in names:
        k = res[n]["kr_shortened"]
        ex = k["example"]
        L.append(f"| `{n}` | {k['shortened']:,} / {k['pairs']:,} ({k['shortened'] / k['pairs']:.2%}) | "
                 + (f"{ex['from']} → {ex['to']}: {ex['before']} → {ex['after']} ({ex['path']})" if ex else "-") + " |")
    L += ["", "## 등급별 국가 간 포탈", ""]
    for n in names:
        cross = [p for p in res[n]["portals"] if p["cross_country"]]
        L += [f"### `{n}` — {len(cross)}개", ""]
        if cross:
            L += ["| 등급 | 접힌 키 | 원문 | 차수 | 연결 역 |", "| :- | :- | :- | -: | :- |"]
            L += [f"| {p['tier']} | {p['name']} | {' / '.join(p['texts'])} | {p['degree']} | {'; '.join(p['stations'])} |" for p in sorted(cross, key=lambda p: (p["tier"], p["name"]))]
        else:
            L.append("없음.")
        L.append("")
    L += ["## 국가 내부 T2·T3 포탈 (참고)", "", "| ruleset | 등급 | 키 | 원문 | 차수 | 연결 역 |", "| :- | :- | :- | :- | -: | :- |"]
    for n in names:
        for p in res[n]["portals"]:
            if p["tier"] != "T1" and not p["cross_country"]:
                L.append(f"| `{n}` | {p['tier']} | {p['name']} | {' / '.join(p['texts'])} | {p['degree']} | {'; '.join(p['stations'])} |")
    L += ["", "## 이체자 접기로만 맞은 T2 포탈 (원문이 서로 다름 — 과병합 검토용)", ""]
    vo = sorted({(p["name"], " / ".join(p["unfolded_keys"]), " / ".join(p["texts"])) for n in names for p in res[n]["portals"] if p["variant_only"]})
    L += [f"- 접힌 키 {k}: 정규화 후 원문 {u} (원문 {t})" for k, u, t in vo] or ["없음."]
    L += ["", "## 더 싼 등급과 겹쳐 생략된 포탈 수 (dedupe)", ""]
    for n in names:
        c = Counter(p["tier"] for p in res[n]["subsumed"])
        L.append(f"- `{n}`: " + (", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "없음"))
    (ROOT / "docs" / "reports" / "b3_world_rulesets.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
