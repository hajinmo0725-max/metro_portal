#!/usr/bin/env python3
"""3차 A5. OSM(Geofabrik 한국 추출본) route relation으로 노선 정차 순서·좌표 교차검증.

수정은 근거 2개 이상(OSM + Wikidata P197, 또는 OSM + 좌표 기하)이 같은 결론일 때만 하고, 나머지는 의심 목록으로 둔다.
이 단계는 판정 표만 만들고 보정 파일(config/kr_lines.yaml 등)은 손대지 않는다.

입력: data/raw/osm/south-korea-latest.osm.pbf (--fetch면 config/sources.yaml geofabrik.korea에서 받음, 캐시)
      data/processed/kr/{stations,ride_edges}.json, data/processed/kr/lines_check.json (08 결과: Wikidata·기하 판정)
출력: data/processed/kr/osm_check.json, docs/reports/a5_osm_check.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.normalize import normalize_name  # noqa: E402
from metro_portal.osm import read_routes, stop_names  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402

PROC = ROOT / "data" / "processed" / "kr"
RAW = ROOT / "data" / "raw" / "osm"


def fetch(url: str, dest: Path, ua: str) -> None:
    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with requests.get(url, headers={"User-Agent": ua}, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)


def match_stops(routes, stations, norm, max_m):
    """OSM 정차 노드 → 우리 역 id (정규화 이름 일치 + 거리). 이름 키: name:ko, name."""
    by = defaultdict(list)
    for s in stations:
        by[normalize_name(s["name_ko"], norm)].append(s)
    for r in routes:
        for n in r["stops"]:
            best = None
            for nm in stop_names(n, ["name:ko", "name"]):
                for s in by.get(normalize_name(nm, norm), []):
                    d = haversine_m(n["lat"], n["lon"], s["lat"], s["lon"])
                    if d <= max_m and (best is None or d < best[1]):
                        best = (s["id"], d)
            n["match"] = best[0] if best else None
            n["match_m"] = round(best[1], 1) if best else None
    return routes


def compare(routes, stations, edges, chk, wd_items, cfg):
    """우리 승차 엣지·좌표를 OSM 정차 순서와 대조하고, Wikidata(P197·P625)·좌표 기하(08 단계 판정)와 묶어 판정한다.
    판정은 물리적 역(정규화 이름) 단위: 같은 이름의 다른 노선 레코드는 OSM 노선 매칭이 갈릴 수 있어서다."""
    sid = {s["id"]: s for s in stations}
    nm = lambda x: sid[x]["name_ko"]  # noqa: E731
    # OSM 노선별 정차 순서 (매칭된 역만, 연속 중복 제거)
    osm_seqs = []
    for r in routes:
        seq = [n["match"] for n in r["stops"] if n["match"]]
        seq = [x for i, x in enumerate(seq) if i == 0 or nm(x) != nm(seq[i - 1])]
        if len(seq) >= 2:
            osm_seqs.append((r["id"], r["tags"].get("name", ""), seq))
    osm_adj, together = set(), defaultdict(set)
    for rid, _, seq in osm_seqs:
        names = [nm(x) for x in seq]
        for a, b in zip(names, names[1:]):
            osm_adj.add(frozenset((a, b)))
        for x in set(names):
            together[x].add(rid)
    edge_wd = {}
    for r in chk["sequences"]:
        for e in r["edges"]:
            edge_wd[frozenset((e["a"], e["b"]))] = (e["wikidata"], bool(e["geometry"]))
    rows = []
    ours = set()
    for e in edges:
        a, b = nm(e["a"]), nm(e["b"])
        ours.add(frozenset((a, b)))
        w, geo_flag = edge_wd.get(frozenset((e["a"], e["b"])), ("?", False))
        if frozenset((a, b)) in osm_adj:
            osm = "adjacent"
        elif together[a] & together[b]:
            osm = "not_adjacent"      # 같은 OSM 노선에 둘 다 있는데 이웃이 아님 → 순서 오류 근거
        else:
            osm = "no_info"           # OSM 공백 (노선 없음, 역 이름 매칭 실패)
        verdict = "ok"
        if osm == "not_adjacent":
            others = (w == "not_adjacent") + geo_flag
            verdict = "fix_candidate" if others else "suspect"
        rows.append({"line": e["line"], "a": a, "b": b, "osm": osm, "wikidata": w, "geometry_flag": geo_flag, "verdict": verdict})
    # OSM에만 있는 인접 (우리 그래프에 없는 엣지). 우리 그래프에서 같은 노선 2역 이상 떨어져 있으면 급행 정차 패턴으로 본다
    adj_line = defaultdict(set)
    for e in edges:
        adj_line[nm(e["a"])].add(nm(e["b"]))
        adj_line[nm(e["b"])].add(nm(e["a"]))

    def hops(a, b, limit=6):
        seen, frontier = {a}, {a}
        for d in range(1, limit + 1):
            frontier = {y for x in frontier for y in adj_line[x]} - seen
            if b in frontier:
                return d
            seen |= frontier
        return None
    qid = {k: v["qid"] for k, v in chk.get("match", {}).items() if v.get("qid")}
    wd_adj = {it["qid"]: {x["qid"] for x in it.get("adjacent", [])} for it in wd_items}
    name_q = defaultdict(set)
    for k, q in qid.items():
        name_q[nm(k)].add(q)
    extra = []
    for pair in sorted(osm_adj - ours, key=lambda p: sorted(p)):
        a, b = sorted(pair)
        h = hops(a, b)
        wdp = any(qb in wd_adj.get(qa, ()) or qa in wd_adj.get(qb, ()) for qa in name_q[a] for qb in name_q[b])
        kind = "express_pattern" if h and h >= 2 else ("missing_edge_two_sources" if wdp else "missing_edge_osm_only")
        extra.append({"a": a, "b": b, "our_hops": h, "wikidata_adjacent": wdp, "kind": kind})
    # 좌표: 역별 OSM 정차 노드 거리 중앙값. Wikidata 좌표와도 크게 다르면 근거 2개
    wd_far = {x["id"] for x in chk.get("coords_vs_wikidata", [])}
    coords = defaultdict(list)
    for r in routes:
        for n in r["stops"]:
            if n["match"]:
                coords[n["match"]].append(n["match_m"])
    coord_flags = []
    for k, v in sorted(coords.items()):
        med = sorted(v)[len(v) // 2]
        if med > cfg["coord_flag_m"]:
            coord_flags.append({"id": k, "station": nm(k), "line": sid[k]["line_name"], "osm_median_m": med,
                                "wikidata_far": k in wd_far, "verdict": "fix_candidate" if k in wd_far else "suspect"})
    stats = {"osm_routes": len(routes), "osm_routes_matched": len(osm_seqs),
             "stops": sum(len(r["stops"]) for r in routes), "stops_matched": sum(1 for r in routes for n in r["stops"] if n["match"]),
             "edges": len(rows), **{f"edges_osm_{k}": sum(1 for r in rows if r["osm"] == k) for k in ("adjacent", "not_adjacent", "no_info")},
             "stations_with_osm_coord": len(coords)}
    return rows, extra, coord_flags, stats


def write_report(out, pbf_meta):
    s = out["stats"]
    L = ["# A5 OSM 교차검증 (Geofabrik 한국 추출본)", "", "생성: `python3 pipeline/13_validate_osm.py --fetch`", "",
         f"- 원본: {pbf_meta}", "- 판정 규칙: 수정 후보는 OSM과 다른 근거(Wikidata P197 비인접 또는 08 단계 좌표 기하 플래그, 좌표는 Wikidata P625 1km 초과)가 같은 결론일 때만. "
         "이 단계는 보정 파일(config/kr_lines.yaml, kr_station_fixes.yaml)을 바꾸지 않는다.", "",
         "## 요약", "", "| 항목 | 값 |", "| :- | -: |"]
    L += [f"| {k} | {v} |" for k, v in s.items()]
    for title, key, cols in (("수정 후보 — 승차 엣지 (근거 2개)", "edge_fix_candidates", ("line", "a", "b", "osm", "wikidata", "geometry_flag")),
                             ("의심 — 승차 엣지 (OSM만)", "edge_suspects", ("line", "a", "b", "osm", "wikidata", "geometry_flag")),
                             ("OSM에만 있는 인접 — 근거 2개 (OSM + Wikidata)", "missing_two", ("a", "b", "our_hops", "wikidata_adjacent")),
                             ("OSM에만 있는 인접 — OSM만", "missing_osm_only", ("a", "b", "our_hops", "wikidata_adjacent")),
                             ("좌표 — 수정 후보 (OSM + Wikidata)", "coord_fix", ("station", "line", "osm_median_m", "wikidata_far")),
                             ("좌표 — 의심 (OSM만)", "coord_suspect", ("station", "line", "osm_median_m", "wikidata_far"))):
        rows = out[key]
        L += ["", f"## {title} ({len(rows)})", ""]
        if rows:
            L += ["| " + " | ".join(cols) + " |", "| " + " | ".join(":-" for _ in cols) + " |"]
            L += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
        else:
            L.append("없음.")
    L += ["", f"급행 정차 패턴으로 본 OSM 인접 (우리 그래프에서 같은 노선 2역 이상): {out['express_patterns']}개"]
    (ROOT / "docs" / "reports" / "a5_osm_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--pbf", default=str(RAW / "south-korea-latest.osm.pbf"))
    a = ap.parse_args()
    src = yaml.safe_load(open(ROOT / "config" / "sources.yaml", encoding="utf-8"))
    cfg = yaml.safe_load(open(ROOT / "config" / "validation.yaml", encoding="utf-8"))["osm"]
    pbf = Path(a.pbf)
    if not pbf.exists():
        if not a.fetch:
            print(f"[13] {pbf} 없음. --fetch로 받거나 수동으로 넣어야 한다 (Geofabrik 차단 시 우회 금지)")
            return 2
        t0 = time.time()
        fetch(src["geofabrik"]["korea"], pbf, src["user_agent"])
        print(f"[13] downloaded {pbf} in {time.time() - t0:.0f}s")
    norm = load_ruleset("strict")["normalize"]
    stations = json.loads((PROC / "stations.json").read_text(encoding="utf-8"))["stations"]
    edges = json.loads((PROC / "ride_edges.json").read_text(encoding="utf-8"))["edges"]
    chk = json.loads((PROC / "lines_check.json").read_text(encoding="utf-8"))
    wd_items = json.loads((PROC / "wikidata_stations.json").read_text(encoding="utf-8"))["items"]
    routes = match_stops(read_routes(pbf, cfg["route_types"], cfg["stop_roles"]), stations, norm, cfg["match_max_m"])
    rows, extra, coord_flags, stats = compare(routes, stations, edges, chk, wd_items, cfg)
    out = {"stats": stats,
           "edge_fix_candidates": [r for r in rows if r["verdict"] == "fix_candidate"],
           "edge_suspects": [r for r in rows if r["verdict"] == "suspect"],
           "missing_two": [x for x in extra if x["kind"] == "missing_edge_two_sources"],
           "missing_osm_only": [x for x in extra if x["kind"] == "missing_edge_osm_only"],
           "express_patterns": sum(1 for x in extra if x["kind"] == "express_pattern"),
           "coord_fix": [c for c in coord_flags if c["verdict"] == "fix_candidate"],
           "coord_suspect": [c for c in coord_flags if c["verdict"] == "suspect"],
           "edges": rows}
    (PROC / "osm_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    st = pbf.stat()
    write_report(out, f"`{pbf.name}` ({st.st_size / 1e6:.1f} MB, 수정 시각 {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(st.st_mtime))})")
    print(json.dumps(stats, ensure_ascii=False))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in out.items() if k not in ("stats", "edges")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
