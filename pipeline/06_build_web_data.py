#!/usr/bin/env python3
"""M6. 웹 MVP용 데이터 번들.

입력: data/processed/kr/{stations,lines,ride_edges}.json + ruleset (그래프는 04와 같은 함수로 재빌드)
출력: web/data/kr_<ruleset>.json  (지도 표시 + 라우팅 그래프)
      web/data/expected_routes_<ruleset>.json  (node 테스트용: Python 길찾기 결과)

라우팅 그래프는 Python이 만든 인접 리스트를 순서까지 그대로 내보낸다.
JS는 알고리즘만 구현하므로 Python과 같은 경로가 나와야 한다 (web/test에서 대조).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.route import shortest_path, without_warps  # noqa: E402

KIND = {"ride": 0, "transfer": 1, "warp_in": 2, "warp_out": 3}


def load_route_cli():
    spec = importlib.util.spec_from_file_location("route_cli", ROOT / "pipeline" / "05_route.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruleset", default="strict")
    ap.add_argument("--random-pairs", type=int, default=40)
    a = ap.parse_args()
    cli = load_route_cli()
    world = cli.load_world(a.ruleset)
    rs, idx, adj, lines_by_id, portals_by_id = world
    stations = sorted(idx.st.values(), key=lambda s: s["id"])
    clusters = sorted(idx.clusters, key=lambda c: c["id"])

    nodes = sorted(adj)                    # Python graph.json과 같은 순서
    nix = {n: i for i, n in enumerate(nodes)}
    cix = {c["id"]: i for i, c in enumerate(clusters)}
    line_ids = sorted(lines_by_id)
    lix = {l: i for i, l in enumerate(line_ids)}
    cluster_of = {sid: c["id"] for c in clusters for sid in c["station_ids"]}

    line_names = {}
    for lid in line_ids:
        for sq in lines_by_id[lid]["sequences"]:
            for x in sq["station_ids"]:
                line_names.setdefault(x, lines_by_id[lid]["name"])
    st_out = {}
    for s in stations:
        st_out[s["id"]] = {"n": s["name_ko"], "la": s["lat"], "lo": s["lon"], "g": line_names.get(s["id"], s["line_name"]),
                           "c": cix[cluster_of[s["id"]]], "ct": s.get("city", "")}
    node_out = []
    for n in nodes:
        if n.startswith("P:"):
            p = portals_by_id[n]
            node_out.append({"id": n, "portal": True, "n": p["name"], "tier": p["tier"]})
        else:
            node_out.append({"id": n, **st_out[n]})
    edges = []
    for n in nodes:
        for (b, c, kind, meta) in adj[n]:
            m = lix[meta] if kind == "ride" else (cix[meta] if kind == "transfer" else meta)
            edges.append([nix[n], nix[b], c, KIND[kind], m])

    lines_out = []
    for lid in line_ids:
        ln = lines_by_id[lid]
        lines_out.append({"id": lid, "name": ln["name"], "color": ln.get("color") or "#888888", "city": ln.get("city", ""),
                          "seqs": [{"id": sq["id"], "circular": sq["circular"], "nodes": [nix[x] for x in sq["station_ids"]]}
                                   for sq in ln["sequences"]]})
    clusters_out = [{"id": c["id"], "n": c["name"], "la": c["lat"], "lo": c["lon"], "city": "/".join(c.get("cities", [])),
                     "s": [nix[x] for x in c["station_ids"]],
                     "lines": sorted({line_names[x] for x in c["station_ids"] if x in line_names})}
                    for c in clusters]
    portals_out = [{"id": p["id"], "n": p["name"], "tier": p["tier"], "cost": p["cost"], "node": nix[p["id"]],
                    "c": [cix[x] for x in p["cluster_ids"]]} for p in sorted(portals_by_id.values(), key=lambda p: p["id"])]

    doc = {
        "meta": {"ruleset": rs["name"], "costs": rs["costs"], "kinds": list(KIND),
                 "attribution": "역·노선: 레일포털(data.kric.go.kr) 표준데이터, 이용허락범위 제한 없음. 지도: © OpenStreetMap contributors"},
        "lines": lines_out, "nodes": node_out, "edges": edges, "clusters": clusters_out, "portals": portals_out,
    }
    out = ROOT / "web" / "data" / f"kr_{rs['name']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    # 기대 결과: 예시 + 시드 고정 랜덤 쌍 (워프 유무 각각)
    import yaml
    ex = yaml.safe_load(open(ROOT / "config" / "report.yaml", encoding="utf-8"))["route_examples"]
    rnd = random.Random(rs.get("metrics", {}).get("random_seed", 42))
    # 예시는 질의 해석 결과 전체(도시 접두어 + 같은 도시 동명역이면 여러 클러스터)를 쓴다
    pairs = [(tuple(c["id"] for c in idx.resolve(s)), tuple(c["id"] for c in idx.resolve(d))) for s, d in ex]
    cl_ids = [c["id"] for c in clusters]
    pairs += [tuple((x,) for x in rnd.sample(cl_ids, 2)) for _ in range(a.random_pairs)]
    cmap = {c["id"]: c for c in clusters}
    nowarp = without_warps(adj)
    exp = []
    for s, d in pairs:
        for warp in (True, False):
            r = shortest_path(adj if warp else nowarp, [x for c in s for x in cmap[c]["station_ids"]],
                              [x for c in d for x in cmap[c]["station_ids"]])
            fr = cix[s[0]] if len(s) == 1 else [cix[c] for c in s]
            to = cix[d[0]] if len(d) == 1 else [cix[c] for c in d]
            exp.append({"from": fr, "to": to, "warp": warp,
                        "cost": r[0] if r else None, "path": [nix[x[0]] for x in r[1]] if r else None})
    (ROOT / "web" / "data" / f"expected_routes_{rs['name']}.json").write_text(json.dumps(exp, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[06] wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB): nodes={len(nodes)} edges={len(edges)} "
          f"lines={len(lines_out)} clusters={len(clusters_out)} portals={len(portals_out)}; expected routes={len(exp)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
