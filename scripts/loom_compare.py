#!/usr/bin/env python3
"""5차 R4: LOOM(octi) 도식과 자체 MIP 도식 비교 → docs/reports/schematic/loom_compare.md, docs/reports/schematic/<권역>_loom.svg

LOOM(github.com/ad-freiburg/loom, GPL-3.0)은 레포에 코드를 넣지 않고 외부 CLI로만 쓴다. 이 세션에서는 환경 설정 스크립트가 빌드해 둔
실행 파일(기본 /tmp/loom/build, 커밋 1e47578)을 그대로 쓴다 (내가 받거나 빌드하지 않는다). 없으면 '실행 안 함'으로 기록하고 끝난다.

입력 변환: 우리 권역 그래프(클러스터 = 역, 승차 엣지 = 노선 집합) → LOOM GeoJSON 노선 그래프 (Point: 역 id·라벨, LineString: from·to·lines).
파이프: loom(노선 순서) | octi(8방향 배치, 휴리스틱 기본) | transitmap(SVG). 지표는 octi 출력의 역 좌표·엣지 폴리라인으로 다시 잰다:
  8방향 아닌 선분, 비인접 선분 교차, 노선 굴곡(노선 시퀀스를 따라 이은 폴리라인의 꺾임, 45° 단위 합), 지리 대비 변위(역 좌표).
사용: python3 scripts/loom_compare.py [--regions seoul,busan] [--bin /tmp/loom/build] [--geo-pen 0]
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal import schematic as S  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base, load_multi  # noqa: E402

REP = ROOT / "docs" / "reports" / "schematic"


def to_loom(w, g):
    """권역 그래프 → LOOM 입력 GeoJSON (WGS84 경위도)."""
    cl = {c["id"]: c for c in w["clusters"]}
    feats = []
    for v in g["nodes"]:
        c = cl[v]
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                      "properties": {"id": v, "station_id": v, "station_label": g["names"][v]}})
    for i, ((a, b), ls) in enumerate(sorted(g["edges"].items())):
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[cl[a]["lon"], cl[a]["lat"]], [cl[b]["lon"], cl[b]["lat"]]]},
                      "properties": {"id": f"e{i}", "from": a, "to": b,
                                     "lines": [{"id": lid, "label": g["lines"][lid]["name"], "color": g["lines"][lid]["color"].lstrip("#")} for lid in ls]}})
    return {"type": "FeatureCollection", "features": feats}


def run(cmd, inp, timeout):
    p = subprocess.run(cmd, input=inp, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {p.stderr.decode(errors='replace')[-500:]}")
    return p.stdout


def seg_dir_ok(p, q, tol=math.radians(2.0)):
    """가로·세로·45° 선분인가 (각도 오차 2° 이내 — 둥근 모서리 단순화가 남긴 0.1~2° 어긋남 허용, 근사 지표)."""
    a = math.atan2(q[1] - p[1], q[0] - p[0])
    k = round(a / (math.pi / 4))
    return abs(a - k * math.pi / 4) < tol


def merc(c):
    """WGS84 경위도 → 웹 메르카토르 (octi는 이 평면의 8방향 격자에 배치하고 경위도로 내보낸다)."""
    R = 6378137.0
    return (math.radians(c[0]) * R, math.log(math.tan(math.pi / 4 + math.radians(c[1]) / 2)) * R)


def simplify(cs, eps):
    """더글러스–포이커. octi는 꺾이는 곳을 짧은 선분 여러 개로 둥글게 그려서(모서리 처리), 그대로 재면 8방향 위반·굴곡이 부풀려진다."""
    if len(cs) < 3:
        return cs
    a, b = cs[0], cs[-1]
    L = math.dist(a, b) or 1e-12
    dmax, k = -1.0, 0
    for i in range(1, len(cs) - 1):
        p = cs[i]
        d = abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / L
        if d > dmax:
            dmax, k = d, i
    if dmax <= eps:
        return [a, b]
    return simplify(cs[: k + 1], eps)[:-1] + simplify(cs[k:], eps)


def loom_stats(g, out, eps=40.0):
    """octi 출력 → 지표. 역 좌표는 station_id가 있는 Point, 엣지는 LineString 폴리라인 (웹 메르카토르로 투영해서 잰다)."""
    for f in out["features"]:
        gm = f["geometry"]
        if gm["type"] == "Point":
            gm["coordinates"] = list(merc(gm["coordinates"]))
        elif gm["type"] == "LineString":
            gm["coordinates"] = [list(merc(c)) for c in gm["coordinates"]]
    pos, polys = {}, {}
    for f in out["features"]:
        pr = f.get("properties", {})
        if f["geometry"]["type"] == "Point" and pr.get("station_id") in g["pos"]:
            pos[pr["station_id"]] = tuple(f["geometry"]["coordinates"])
    for f in out["features"]:
        pr = f.get("properties", {})
        if f["geometry"]["type"] != "LineString":
            continue
        cs = simplify([tuple(x) for x in f["geometry"]["coordinates"]], eps)   # 모서리 둥글림 제거 (40m, 메르카토르)
        polys.setdefault((pr.get("from"), pr.get("to")), []).append(cs)
    # 출력 엣지는 축약 정점(deg-2)을 거치므로 from/to가 우리 역 id가 아닐 수 있다 → 선분 단위로 센다
    segs = [(cs[i], cs[i + 1]) for ps in polys.values() for cs in ps for i in range(len(cs) - 1) if cs[i] != cs[i + 1]]
    non_oct = sum(1 for p, q in segs if not seg_dir_ok(p, q))
    # 정점 공유 없는 선분 쌍의 교차 (격자 해시)
    cell = max(1e-9, sum(math.dist(p, q) for p, q in segs) / max(1, len(segs)) * 2)
    grid = {}
    for i, (p, q) in enumerate(segs):
        for gx in range(int(min(p[0], q[0]) // cell), int(max(p[0], q[0]) // cell) + 1):
            for gy in range(int(min(p[1], q[1]) // cell), int(max(p[1], q[1]) // cell) + 1):
                grid.setdefault((gx, gy), []).append(i)
    seen, cross = set(), 0
    for idx in grid.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                (p1, q1), (p2, q2) = segs[i], segs[j]
                if len({p1, q1, p2, q2}) == 4 and S.segments_cross(p1, q1, p2, q2):
                    cross += 1
    # 굴곡: 노선마다 역 시퀀스를 따라 역 좌표만으로 (우리 지표와 같은 정의). 엣지 안쪽 꺾임은 따로 센다
    bends = 0
    for sq in g["seqs"]:
        ks = [k for k in sq["nodes"] if k in pos]
        for a, v, b in zip(ks, ks[1:], ks[2:]):
            t1 = math.atan2(pos[a][1] - pos[v][1], pos[a][0] - pos[v][0])
            t2 = math.atan2(pos[b][1] - pos[v][1], pos[b][0] - pos[v][0])
            bends += round(abs((math.degrees(t2 - t1) + 360) % 360 - 180) / 45.0)
    inner = 0
    for ps in polys.values():
        for cs in ps:
            for a, v, b in zip(cs, cs[1:], cs[2:]):
                t1 = math.atan2(a[1] - v[1], a[0] - v[0])
                t2 = math.atan2(b[1] - v[1], b[0] - v[0])
                inner += round(abs((math.degrees(t2 - t1) + 360) % 360 - 180) / 45.0)
    disp = None
    if len(pos) == len(g["pos"]):
        st = S.layout_stats(g, pos)
        disp = st["mean_displacement_norm"]
    return {"stations_placed": len(pos), "segments": len(segs), "non_octilinear_segments": non_oct, "segment_crossings": cross,
            "bend_units_45deg_at_stations": bends, "bend_units_45deg_inside_edges": inner, "mean_displacement_norm": disp}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default="seoul,busan,daegu,daejeon,gwangju,taipei")
    ap.add_argument("--bin", default="/tmp/loom/build")
    ap.add_argument("--geo-pen", default="0")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    b = Path(a.bin)
    if not (b / "octi").exists():
        print(f"[loom] {b}/octi 없음 — 실행 안 함 (환경 설정 스크립트가 LOOM을 빌드하지 않았다)")
        return 0
    cfg = yaml.safe_load(open(ROOT / "config" / "schematic.yaml", encoding="utf-8"))
    w_kr = build_world(*load_base(), load_ruleset(cfg["ruleset"]))
    w_tw = None
    rows = []
    for reg in cfg["regions"]:
        if reg["id"] not in a.regions.split(","):
            continue
        if reg["country"] == "TW":
            w_tw = w_tw or build_world(*load_multi(("KR", "TW")), load_ruleset("tw_t12"))
        w = w_tw if reg["country"] == "TW" else w_kr
        g = S.region_graph(w, reg["city"])
        inp = json.dumps(to_loom(w, g), ensure_ascii=False).encode()
        t = time.time()
        row = {"region": reg["id"], "city": reg["city"], "geo_pen": a.geo_pen}
        try:
            lo = run([str(b / "loom")], inp, a.timeout)
            oc = run([str(b / "octi"), "--geo-pen", a.geo_pen], lo, a.timeout)
            row["seconds"] = round(time.time() - t, 1)
            row.update(loom_stats(g, json.loads(oc)))
            # 그림용: 권역이 넓어 기본 굵기(20)로는 축소하면 선이 안 보인다 → 굵게, 차수 2 역 라벨 생략
            svg = run([str(b / "transitmap"), "-l", "--line-width", "90", "--line-spacing", "40", "--no-deg2-labels",
                       "--station-label-textsize", "220"], oc, a.timeout)
            (REP / f"{reg['id']}_loom.svg").write_bytes(svg)
        except Exception as ex:  # noqa: BLE001
            row["error"] = str(ex)[:300]
            row["seconds"] = round(time.time() - t, 1)
        # 자체 MIP 결과 (캐시)
        doc = json.loads((ROOT / "data" / "processed" / "schematic" / f"{reg['id']}.json").read_text(encoding="utf-8"))
        row["mip"] = doc["stats"]
        row["geo"] = doc["stats_geo"]
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    ver = subprocess.run(["git", "-C", str(b.parent), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "?"
    out = {"loom_commit": ver, "bin": str(b), "rows": rows}
    (ROOT / "data" / "processed" / "schematic" / "loom_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    L = ["# R4 LOOM(octi) vs 자체 MIP 도식 비교", "",
         f"생성: `python3 scripts/loom_compare.py` · LOOM 커밋 `{ver}` (환경 설정 스크립트가 빌드한 `{b}`의 실행 파일을 외부 CLI로만 사용, GPL-3.0, 코드 미복사) · "
         f"파이프 `loom | octi --geo-pen {a.geo_pen} | transitmap -l` (octi 기본: 휴리스틱, 8방향 격자, 차수 2 축약)", "",
         "- octi 출력은 경위도라 웹 메르카토르로 투영하고, 꺾이는 곳의 둥근 모서리(짧은 선분 여러 개)는 더글러스–포이커 40m로 단순화한 뒤 잰다. "
         "'8방향'은 각도 오차 2° 이내 (단순화가 남긴 어긋남 허용) — LOOM 쪽 8방향·엣지 안 꺾임 수치는 근사다.",
         "- LOOM은 엣지를 격자 위 폴리라인으로 그리므로 '8방향 아님'은 선분 단위, 교차는 정점을 공유하지 않는 선분 쌍. "
         "굴곡은 우리 지표와 같은 정의(노선 시퀀스의 역 좌표에서 꺾인 각도, 45° 단위 합) + 엣지 안쪽 꺾임을 따로 센다.",
         "- 자체 MIP는 역 사이를 직선으로 잇는다 (엣지 안쪽 꺾임 0). 교차는 엣지 쌍 기준(지리 좌표에도 있는 입체 교차 포함).", "",
         "| 권역 | LOOM 시간 | LOOM 8방향 아님 | LOOM 교차 | LOOM 굴곡 (역 + 엣지 안) | LOOM 변위 | MIP 8방향 아님 | MIP 교차 | MIP 굴곡 | MIP 변위 | 지리 교차 | 지리 굴곡 |",
         "| :- | -: | -: | -: | :- | -: | -: | -: | -: | -: | -: | -: |"]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['city']} | {r['seconds']}s | 실패: {r['error'][:80]} | | | | {r['mip']['non_octilinear_edges']} | {r['mip']['crossings']} | "
                     f"{r['mip']['bend_units_45deg']} | {r['mip']['mean_displacement_norm']} | {r['geo']['crossings']} | {r['geo']['bend_units_45deg']} |")
            continue
        L.append(f"| {r['city']} | {r['seconds']}s | {r['non_octilinear_segments']} / {r['segments']} | {r['segment_crossings']} | "
                 f"{r['bend_units_45deg_at_stations']} + {r['bend_units_45deg_inside_edges']} | {r['mean_displacement_norm']} | "
                 f"{r['mip']['non_octilinear_edges']} | {r['mip']['crossings']} | {r['mip']['bend_units_45deg']} | {r['mip']['mean_displacement_norm']} | "
                 f"{r['geo']['crossings']} | {r['geo']['bend_units_45deg']} |")
    (REP / "loom_compare.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
