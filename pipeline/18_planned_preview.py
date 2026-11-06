#!/usr/bin/env python3
"""4차 Q0-5. 개통 예정 노선(config/kr_planned.yaml)을 켰을 때 새로 생기는 클러스터·포탈 미리보기.

enabled 값과 무관하게 계획 노선 전부를 메모리에서만 더해 ruleset별로 그래프를 만들고, 지금 그래프와 비교한다.
산출물(stations.json 등)은 바꾸지 않는다. 실제로 켜려면 kr_planned.yaml의 enabled를 true로 바꾸고 02부터 다시 돌린다.

입력: data/processed/{kr,tw}/..., config/kr_planned.yaml, ruleset
출력: data/processed/kr/planned_preview.json, docs/reports/q0_planned_preview.md
사용: python3 pipeline/18_planned_preview.py [--rulesets strict,tw_t123]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.normalize import normalize_name  # noqa: E402
from metro_portal.planned import load_planned, station_records  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base, load_multi  # noqa: E402

OUT = ROOT / "data" / "processed" / "kr" / "planned_preview.json"
REPORT = ROOT / "docs" / "reports" / "q0_planned_preview.md"


def add_planned(stations, edges, lines, planned, norm):
    """메모리에서 계획 노선을 더한다. 정차역 이름은 (새 노선) 자기 역 그룹, (연장) 연장 대상 노선 pool + 자기 역 그룹에서 찾는다."""
    S = stations + station_records(planned)
    E = list(edges)
    L = copy.deepcopy(lines)
    lby = {ln["id"]: ln for ln in L}
    sid = {s["id"]: s for s in S}
    for pl in planned:
        own = f"{pl['line_no']}:{pl['line_name']}"
        if pl["kind"] == "new_line":
            ln = {"id": pl["id"], "name": pl["name"], "city": pl["city"], "color": pl["color"], "pools": [own],
                  "sequences": [], "planned": pl["id"], "country": "KR"}
            L.append(ln)
        else:
            ln = lby[pl["extends"]]
        pools = set(ln["pools"]) | {own}
        for q in pl["sequences"]:
            ids = []
            for stop in q["stops"]:
                key = normalize_name(stop, norm)
                cand = sorted(s["id"] for s in S if s["line_group"] in pools and normalize_name(s["name_ko"], norm) == key)
                if len(cand) != 1:
                    raise SystemExit(f"[18] 정차역 해석 실패 {pl['id']} {stop}: {cand}")
                ids.append(cand[0])
            ln["sequences"].append({"id": q["id"], "station_ids": ids, "circular": False, "directed": False, "planned": pl["id"]})
            for a, b in zip(ids, ids[1:]):
                a, b = sorted((a, b))
                E.append({"line": ln["id"], "sequence": q["id"], "a": a, "b": b,
                          "distance_m": round(haversine_m(sid[a]["lat"], sid[a]["lon"], sid[b]["lat"], sid[b]["lon"]), 1)})
    return S, E, L


def summarize(w):
    return {"clusters": len(w["clusters"]), "portals": len(w["portals"]),
            "portal_set": {p["id"]: sorted(p["cluster_ids"]) for p in w["portals"]}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rulesets", default="strict,tw_t123")
    a = ap.parse_args()
    planned = load_planned(include_disabled=True)
    result = {"planned_lines": [{"id": p["id"], "enabled": bool(p.get("enabled")), "kind": p["kind"],
                                 "expected_open": p.get("expected_open", ""),
                                 "new_stations": [s["name"] for s in p["stations"]]} for p in planned],
              "rulesets": {}}
    for rsn in a.rulesets.split(","):
        rs = load_ruleset(rsn)
        # 한국+타이베이 ruleset(tw_*)은 두 나라 데이터로, 나머지는 한국만
        base = load_multi(("KR", "TW")) if rsn.startswith("tw_") else load_base()
        before = build_world(*copy.deepcopy(base), rs)
        S, E, L = add_planned(*copy.deepcopy(base), planned, rs["normalize"])
        after = build_world(S, E, L, rs)
        b, f = summarize(before), summarize(after)
        new_ids = {s["id"] for s in station_records(planned)}
        cl_new = [c for c in after["clusters"] if set(c["station_ids"]) & new_ids]
        merged = [{"cluster": c["id"], "stations": c["station_ids"], "names": c["names"]}
                  for c in cl_new if len(c["station_ids"]) > 1]
        added = [{"id": pid, "tier": next(p["tier"] for p in after["portals"] if p["id"] == pid),
                  "clusters": cids,
                  "labels": [next(f"{'/'.join(c['cities'])} {c['name']} [{', '.join(sorted({x.split(':')[1] for x in c['station_ids']}))}]"
                                  for c in after["clusters"] if c["id"] == cid) for cid in cids]}
                 for pid, cids in sorted(f["portal_set"].items()) if pid not in b["portal_set"]]
        changed = [{"id": pid, "before": b["portal_set"][pid], "after": cids}
                   for pid, cids in sorted(f["portal_set"].items()) if pid in b["portal_set"] and b["portal_set"][pid] != cids]
        removed = sorted(pid for pid in b["portal_set"] if pid not in f["portal_set"])
        result["rulesets"][rsn] = {
            "before": {"clusters": b["clusters"], "portals": b["portals"]},
            "after": {"clusters": f["clusters"], "portals": f["portals"]},
            "new_station_clusters": [{"id": c["id"], "stations": c["station_ids"]} for c in cl_new],
            "merged_with_existing": merged, "portals_added": added, "portals_changed": changed, "portals_removed": removed}
        print(f"[18] {rsn}: clusters {b['clusters']}→{f['clusters']}, portals {b['portals']}→{f['portals']}, "
              f"added {[x['id'] for x in added]}, changed {[x['id'] for x in changed]}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(result)
    return 0


def write_report(r):
    L = ["# Q0 개통 예정 노선 미리보기", "", "생성: `python3 pipeline/18_planned_preview.py` (입력 `config/kr_planned.yaml`)", "",
         "계획 노선을 메모리에서만 더해 그래프를 다시 만들고 지금 그래프와 비교했다. 산출물은 바꾸지 않는다.", "",
         "| 노선 | 종류 | 활성 | 개통 예정 | 역 |", "| :- | :- | :- | :- | :- |"]
    for p in r["planned_lines"]:
        L.append(f"| {p['id']} | {p['kind']} | {'예' if p['enabled'] else '아니오'} | {p['expected_open']} | {', '.join(p['new_stations'])} |")
    for rsn, x in r["rulesets"].items():
        L += ["", f"## ruleset `{rsn}`", "",
              f"- 클러스터 {x['before']['clusters']} → {x['after']['clusters']}, 포탈 {x['before']['portals']} → {x['after']['portals']}",
              "- 기존 역과 같은 클러스터로 묶이는 계획 역 (환승):"]
        L += [f"  - {m['cluster']}: {', '.join(m['stations'])}" for m in x["merged_with_existing"]] or ["  - 없음"]
        L += ["- 새로 생기는 포탈:"]
        L += [f"  - {p['tier']} `{p['id']}`: " + " ↔ ".join(p["labels"]) for p in x["portals_added"]] or ["  - 없음"]
        L += ["- 연결 클러스터가 바뀌는 기존 포탈:"]
        L += [f"  - `{c['id']}`: {c['before']} → {c['after']}" for c in x["portals_changed"]] or ["  - 없음"]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
