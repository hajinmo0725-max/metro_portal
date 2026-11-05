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


def compare(routes, stations, edges, chk, cfg):
    sid = {s["id"]: s for s in stations}
    osm_adj = set()
    for r in routes:
        seq = [n["match"] for n in r["stops"] if n["match"]]
        seq = [x for i, x in enumerate(seq) if i == 0 or x != seq[i - 1]]
        for a, b in zip(seq, seq[1:]):
            osm_adj.add(frozenset((sid[a]["name_ko"], sid[b]["name_ko"])))
    wd = {}
    for r in chk["sequences"]:
        for e in r["edges"]:
            wd[(e["a"], e["b"])] = (e["wikidata"], e["geometry"])
    rows = []
    for e in edges:
        key = frozenset((sid[e["a"]]["name_ko"], sid[e["b"]]["name_ko"]))
        w, g = wd.get((e["a"], e["b"])) or wd.get((e["b"], e["a"])) or ("?", "?")
        rows.append({"line": e["line"], "a": sid[e["a"]]["name_ko"], "b": sid[e["b"]]["name_ko"], "osm": key in osm_adj,
                     "wikidata": w, "geometry": g})
    coords = defaultdict(list)
    for r in routes:
        for n in r["stops"]:
            if n["match"]:
                coords[n["match"]].append(n["match_m"])
    coord_flags = [{"id": k, "station": sid[k]["name_ko"], "osm_median_m": sorted(v)[len(v) // 2]}
                   for k, v in sorted(coords.items()) if sorted(v)[len(v) // 2] > cfg["coord_flag_m"]]
    return rows, coord_flags


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
    routes = match_stops(read_routes(pbf, cfg["route_types"], cfg["stop_roles"]), stations, norm, cfg["match_max_m"])
    rows, coord_flags = compare(routes, stations, edges, chk, cfg)
    both_bad = [r for r in rows if not r["osm"] and (r["wikidata"] == "not_adjacent" or r["geometry"] not in ("ok", "?", None, ""))]
    out = {"routes": len(routes), "edges": len(rows), "osm_adjacent": sum(r["osm"] for r in rows),
           "fix_candidates_two_sources": both_bad, "osm_only_not_adjacent": [r for r in rows if not r["osm"] and r not in both_bad],
           "coord_flags": coord_flags}
    (PROC / "osm_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in out.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
