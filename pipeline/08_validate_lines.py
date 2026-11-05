#!/usr/bin/env python3
"""N2·N3. 노선 순서·좌표 검증 (OSM 없이).

근거 1 (기하): 시퀀스별 현재 순서 길이 vs 좌표 기반 경로 최적화(2-opt + or-opt) 길이, 급반전(되돌아감)·국소 스왑 이득,
               최적해에 없는 현재 엣지
근거 2 (Wikidata): 역 아이템 인접관계(P197)로 현재 엣지가 인접인지, 같은 시퀀스 안의 비연속 역이 인접으로 기록됐는지
좌표 (N3): 노선 내 좌표 스파이크(이웃과 모두 멀고 이웃끼리는 가까움), 끝점 이탈, Wikidata 좌표(P625)와의 거리,
           다른 이름 역끼리 좌표가 거의 같은 경우(복사 의심)

입력: data/processed/kr/{stations,lines}.json, data/processed/kr/wikidata_stations.json, config/validation.yaml
출력: data/processed/kr/lines_check.json, docs/reports/n2_lines_check.md, docs/reports/n3_coords_check.md,
      docs/reports/lines/<line>__<sequence>.png (--no-plots로 생략)

Wikidata 매칭은 좌표 검증에도 쓰므로 좌표에 기대지 않는다: 이름(정규화) 후보 중 시퀀스 이웃 역의 후보와
P197로 인접한 아이템을 우선하고, 동률일 때만 거리로 고른다.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.lineval import (dist_matrix, edges_of, geometry_flags, optimize_order,  # noqa: E402
                                  path_length, spike_flags)
from metro_portal.normalize import normalize_name  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402

PROC = ROOT / "data" / "processed" / "kr"
REP = ROOT / "docs" / "reports"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


class WikidataMatcher:
    def __init__(self, wd_items, norm):
        self.items = {it["qid"]: it for it in wd_items if it["lat"] is not None}
        self.adj = defaultdict(set)
        for it in wd_items:
            for a in it["adjacent"]:
                self.adj[it["qid"]].add(a["qid"])
                self.adj[a["qid"]].add(it["qid"])
        self.by_name = defaultdict(list)
        for it in self.items.values():
            if it["label_ko"]:
                self.by_name[normalize_name(it["label_ko"], norm)].append(it["qid"])
        for k in self.by_name:
            self.by_name[k].sort(key=lambda q: (len(q), q))
        self.norm = norm

    def candidates(self, st):
        return self.by_name.get(normalize_name(st["name_ko"], self.norm), [])

    def adjacent(self, a, b):
        return b in self.adj.get(a, ())


def match_stations(stations, lines, wm, fallback_m=None):
    """역 레코드 → Wikidata 아이템. 반환: {sid: {qid, method, n_cands, adj_score}}
    같은 이름 아이템이 없으면(Wikidata 라벨이 다름: 건대입구 ↔ 건국대역) fallback_m 이내 가장 가까운 아이템을
    'coord_fallback'으로 붙인다. 이 매칭은 좌표에 기대므로 좌표 검사에는 쓰지 않고 인접 검사에만 쓴다."""
    neigh = defaultdict(set)
    for ln in lines:
        for sq in ln["sequences"]:
            ids = sq["station_ids"]
            pairs = list(zip(ids, ids[1:])) + ([(ids[-1], ids[0])] if sq["circular"] and len(ids) > 2 else [])
            for a, b in pairs:
                neigh[a].add(b)
                neigh[b].add(a)
    sid = {s["id"]: s for s in stations}
    out = {}
    for s in sorted(stations, key=lambda s: s["id"]):
        cands = wm.candidates(s)
        if not cands:
            near = None
            if fallback_m:
                near = min(((haversine_m(s["lat"], s["lon"], it["lat"], it["lon"]), q) for q, it in wm.items.items()), default=None)
            if near and near[0] <= fallback_m:
                out[s["id"]] = {"qid": near[1], "method": "coord_fallback", "n_cands": 0, "adj_score": 0,
                                "wd_label": wm.items[near[1]]["label_ko"], "distance_m": round(near[0])}
            else:
                out[s["id"]] = {"qid": None, "method": "no_candidate", "n_cands": 0, "adj_score": 0}
            continue
        ncands = {n: set(wm.candidates(sid[n])) for n in sorted(neigh[s["id"]])}

        def score(q):
            return sum(1 for cs in ncands.values() if any(wm.adjacent(q, c) for c in cs))
        scored = sorted(cands, key=lambda q: (-score(q), haversine_m(s["lat"], s["lon"], wm.items[q]["lat"], wm.items[q]["lon"]), q))
        best = scored[0]
        sc = score(best)
        if len(cands) == 1:
            method = "unique+adj" if sc else "unique"
        else:
            tie = [q for q in cands if score(q) == sc]
            method = "adj" if sc and len(tie) == 1 else ("adj+nearest" if sc else "nearest")
        out[s["id"]] = {"qid": best, "method": method, "n_cands": len(cands), "adj_score": sc}
    return out


def check_sequences(stations, lines, wm, match, gcfg, ccfg):
    sid = {s["id"]: s for s in stations}
    # 우리 그래프 전체(모든 노선)의 인접 쌍: Wikidata '추가 인접'이 다른 노선 엣지로 설명되는지 확인용
    ours = set()
    for ln in lines:
        for sq in ln["sequences"]:
            ids = sq["station_ids"]
            pairs = list(zip(ids, ids[1:])) + ([(ids[-1], ids[0])] if sq["circular"] and len(ids) > 2 else [])
            for a, b in pairs:
                qa, qb = match[a]["qid"], match[b]["qid"]
                if qa and qb:
                    ours.add(frozenset((qa, qb)))
    results = []
    for ln in lines:
        for sq in ln["sequences"]:
            ids = sq["station_ids"]
            closed = sq["circular"]
            pts = [(sid[x]["lat"], sid[x]["lon"]) for x in ids]
            D = dist_matrix(pts)
            cur = list(range(len(ids)))
            Lc = path_length(cur, D, closed)
            opt, Lo = optimize_order(pts, cur, closed)
            cur_only = sorted(edges_of(cur, closed) - edges_of(opt, closed))
            gflags = geometry_flags(pts, gcfg, closed)
            sflags = spike_flags(pts, ccfg, closed)
            pairs = list(zip(range(len(ids)), range(1, len(ids)))) + ([(len(ids) - 1, 0)] if closed and len(ids) > 2 else [])
            edges = []
            for i, j in pairs:
                a, b = ids[i], ids[j]
                qa, qb = match[a]["qid"], match[b]["qid"]
                if not qa or not qb:
                    wd = "unmatched"
                elif qa == qb:
                    wd = "same_item"
                elif wm.adjacent(qa, qb):
                    wd = "adjacent"
                elif match[a]["adj_score"] <= 0 or match[b]["adj_score"] <= 0:
                    # 한쪽 아이템이 시퀀스 이웃 누구와도 P197 인접이 아니다: 그 노선용 아이템이 Wikidata에 없을 가능성
                    # (예: 부산 1호선 교대 → 동해선 교대 아이템만 있음). 순서 오류일 수도 있어 따로 표시한다
                    wd = "not_adjacent_weak"
                else:
                    wd = "not_adjacent"
                g = []
                if tuple(sorted((i, j))) in cur_only:
                    g.append("not_in_optimal")
                for f in gflags:
                    if f["kind"] == "backtrack" and f["i"] in (i, j):
                        g.append(f"backtrack@{sid[ids[f['i']]]['name_ko']}")
                    if f["kind"] == "swap" and {f["i"], f["j"]} & {i, j}:
                        g.append(f"swap({sid[ids[f['i']]]['name_ko']}↔{sid[ids[f['j']]]['name_ko']})")
                edges.append({"i": i, "j": j, "a": a, "b": b, "a_name": sid[a]["name_ko"], "b_name": sid[b]["name_ko"],
                              "distance_m": round(D[i][j]), "wikidata": wd, "geometry": g,
                              "both": bool(g) and wd.startswith("not_adjacent")})
            # Wikidata에는 인접인데 이 시퀀스에서 비연속이고, 우리 그래프 어디에도 없는 쌍
            pos = {match[x]["qid"]: k for k, x in enumerate(ids) if match[x]["qid"]}
            extra = []
            for qa, ka in sorted(pos.items(), key=lambda kv: kv[1]):
                for qb in sorted(wm.adj.get(qa, ())):
                    kb = pos.get(qb)
                    if kb is None or kb <= ka:
                        continue
                    consecutive = kb - ka == 1 or (closed and {ka, kb} == {0, len(ids) - 1})
                    if not consecutive and frozenset((qa, qb)) not in ours:
                        extra.append({"a": ids[ka], "b": ids[kb], "a_name": sid[ids[ka]]["name_ko"], "b_name": sid[ids[kb]]["name_ko"],
                                      "pos": [ka, kb], "distance_m": round(D[ka][kb])})
            results.append({
                "line": ln["id"], "line_name": ln["name"], "sequence": sq["id"], "circular": closed, "n": len(ids),
                "color": ln.get("color") or "#555555",
                "length_current_m": round(Lc), "length_optimal_m": round(Lo), "ratio": round(Lc / Lo, 4) if Lo else 1.0,
                "optimal_order": opt, "cur_only_edges": [list(e) for e in cur_only],
                "geometry_flags": gflags, "spike_flags": sflags, "edges": edges, "wikidata_extra_adjacent": extra,
                "station_ids": ids,
            })
    return results


def coord_checks(stations, clusters_by_sid, match, wm, ccfg):
    out = []
    for s in sorted(stations, key=lambda s: s["id"]):
        m = match[s["id"]]
        if not m["qid"] or m["method"] == "coord_fallback":
            continue
        it = wm.items[m["qid"]]
        d = haversine_m(s["lat"], s["lon"], it["lat"], it["lon"])
        if d > ccfg["wikidata_mismatch_m"]:
            out.append({"id": s["id"], "name": s["name_ko"], "line": s["line_name"], "qid": m["qid"], "wd_label": it["label_ko"],
                        "method": m["method"], "adj_score": m["adj_score"], "distance_m": round(d),
                        "ours": [s["lat"], s["lon"]], "wikidata": [it["lat"], it["lon"]], "wd_n_coords": it["n_coords"]})
    near = []
    st = sorted(stations, key=lambda s: s["id"])
    for i, a in enumerate(st):
        for b in st[i + 1:]:
            if abs(a["lat"] - b["lat"]) > 0.001:
                continue
            d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            if d < ccfg["near_duplicate_m"] and clusters_by_sid[a["id"]] != clusters_by_sid[b["id"]]:
                near.append({"a": a["id"], "a_name": a["name_ko"], "b": b["id"], "b_name": b["name_ko"], "distance_m": round(d, 1)})
    return out, near


def regression_on_original_coords(stations, lines, ccfg, cof=None, match=None, wm=None):
    """이미 보정한 좌표(config/kr_station_fixes.yaml)를 원래 값으로 되돌려도 스파이크·근접 중복 검사가 잡는지 (검출력 확인)."""
    fixed = {s["id"]: s for s in stations if s.get("coord_fix")}
    res = []
    near_hit = {}
    for sid_, s in fixed.items():
        lat, lon = s["coord_fix"]["from"]
        best = min(((haversine_m(lat, lon, o["lat"], o["lon"]), o["name_ko"]) for o in stations
                    if o["id"] != sid_ and (cof is None or cof[o["id"]] != cof[sid_])), default=(None, None))
        near_hit[sid_] = {"nearest_other_m": round(best[0], 1) if best[0] is not None else None, "nearest_other": best[1],
                          "detected_by_near_dup": best[0] is not None and best[0] < ccfg["near_duplicate_m"]}
        if match is not None and match[sid_]["qid"]:
            it = wm.items[match[sid_]["qid"]]
            dwd = haversine_m(lat, lon, it["lat"], it["lon"])
            near_hit[sid_].update(wikidata_m=round(dwd), detected_by_wikidata=dwd > ccfg["wikidata_mismatch_m"])
        else:
            near_hit[sid_].update(wikidata_m=None, detected_by_wikidata=False)
    for sid_, s in sorted(fixed.items()):
        for ln in lines:
            for sq in ln["sequences"]:
                if sid_ not in sq["station_ids"]:
                    continue
                byid = {x["id"]: x for x in stations}
                pts = []
                for x in sq["station_ids"]:
                    if x == sid_:
                        pts.append(tuple(s["coord_fix"]["from"]))
                    else:
                        pts.append((byid[x]["lat"], byid[x]["lon"]))
                k = sq["station_ids"].index(sid_)
                hit = [f for f in spike_flags(pts, ccfg, sq["circular"]) if f["i"] == k]
                res.append({"id": sid_, "name": s["name_ko"], "line": ln["id"], "detected_by_spike": bool(hit), "flag": hit[0] if hit else None,
                            **near_hit[sid_]})
    return res


def plot_sequence(r, sid, outdir, font_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import math
    if font_path:
        font_manager.fontManager.addfont(font_path)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font_path).get_name()
    ids = r["station_ids"]
    lat0 = sum(sid[x]["lat"] for x in ids) / len(ids)
    k = math.cos(math.radians(lat0))
    xs = [sid[x]["lon"] * k for x in ids]
    ys = [sid[x]["lat"] for x in ids]
    w = (max(xs) - min(xs)) or 1e-3
    h = (max(ys) - min(ys)) or 1e-3
    side = 9.0
    fw, fh = (side, max(4.5, side * h / w)) if w >= h else (max(5.5, side * w / h), side)
    fig, ax = plt.subplots(figsize=(fw, fh + 0.6), dpi=110)
    order = list(range(len(ids))) + ([0] if r["circular"] else [])
    opt = r["optimal_order"] + ([r["optimal_order"][0]] if r["circular"] else [])
    if r["ratio"] > 1.0005:
        ax.plot([xs[i] for i in opt], [ys[i] for i in opt], color="#999999", lw=1, ls=":", zorder=1, label="좌표 최적 경로(2-opt)")
    ax.plot([xs[i] for i in order], [ys[i] for i in order], color=r["color"], lw=2.2, zorder=2, label="현재 순서")
    for e in r["edges"]:
        if e["geometry"] or e["wikidata"].startswith("not_adjacent"):
            col = "#D7263D" if e["both"] else ("#F49D37" if e["geometry"] else "#3F88C5")
            ax.plot([xs[e["i"]], xs[e["j"]]], [ys[e["i"]], ys[e["j"]]], color=col, lw=4, alpha=0.75, zorder=3)
    ax.scatter(xs, ys, s=14, color="white", edgecolor="black", zorder=4)
    for n, x in enumerate(ids):
        ax.annotate(f"{n}.{sid[x]['name_ko'].split('(')[0]}", (xs[n], ys[n]), fontsize=6.5, xytext=(3, 2),
                    textcoords="offset points", zorder=5)
    ax.scatter([xs[0]], [ys[0]], s=50, marker="s", color="black", zorder=6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    nflag = sum(1 for e in r["edges"] if e["geometry"] or e["wikidata"].startswith("not_adjacent"))
    ax.set_title(f"{r['line_name']} [{r['sequence']}] {'순환' if r['circular'] else ''}  역 {r['n']}\n"
                 f"현재 {r['length_current_m'] / 1000:.1f}km / 최적 {r['length_optimal_m'] / 1000:.1f}km (×{r['ratio']:.3f})  "
                 f"의심 엣지 {nflag}", fontsize=9)
    from matplotlib.lines import Line2D
    handles, labels = ax.get_legend_handles_labels()
    handles += [Line2D([0], [0], color="#D7263D", lw=4), Line2D([0], [0], color="#F49D37", lw=4), Line2D([0], [0], color="#3F88C5", lw=4)]
    labels += ["기하+Wikidata 둘 다 의심", "기하만 의심", "Wikidata 비인접만"]
    # 범례는 축 아래에 둔다 (역 라벨을 가리지 않게)
    ax.legend(handles, labels, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.045), ncol=2, frameon=False)
    ax.text(0.0, -0.005, "■ = 시퀀스 0번 역. 출처: 레일포털 표준데이터 좌표, Wikidata P197(CC0)", fontsize=6,
            transform=ax.transAxes, va="top")
    path = outdir / f"{r['line']}__{r['sequence']}.png"
    fig.savefig(path, metadata={"Software": None}, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return path


def find_font():
    try:
        import koreanize_matplotlib  # noqa: F401
        p = Path(koreanize_matplotlib.__file__).parent / "fonts" / "NanumGothic.ttf"
        return str(p) if p.exists() else None
    except ImportError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-plots", action="store_true")
    a = ap.parse_args()
    vcfg = yaml.safe_load(open(ROOT / "config" / "validation.yaml", encoding="utf-8"))
    gcfg, ccfg = vcfg["line_geometry"], vcfg["coords"]
    rs = load_ruleset("strict")
    stations = load(PROC / "stations.json")["stations"]
    lines = load(PROC / "lines.json")["lines"]
    wd = load(PROC / "wikidata_stations.json")
    wm = WikidataMatcher(wd["items"], rs["normalize"])
    match = match_stations(stations, lines, wm, ccfg.get("wikidata_fallback_match_m"))
    # coord_fallback 매칭의 adj_score: 이웃 후보와의 인접 수 (참고용)
    for sid_, m in match.items():
        if m["method"] == "coord_fallback":
            m["adj_score"] = -1
    from metro_portal.graph import build_clusters
    cl = build_clusters(stations, rs)
    cof = {x: c["id"] for c in cl for x in c["station_ids"]}

    seq = check_sequences(stations, lines, wm, match, gcfg, ccfg)
    coord_wd, near = coord_checks(stations, cof, match, wm, ccfg)
    regress = regression_on_original_coords(stations, lines, ccfg, cof, match, wm)
    mstats = defaultdict(int)
    for m in match.values():
        mstats[m["method"]] += 1
    doc = {"thresholds": {"line_geometry": gcfg, "coords": ccfg}, "wikidata_meta": wd["meta"]["counts"],
           "match_stats": dict(sorted(mstats.items())), "match": match, "sequences": seq,
           "coords_vs_wikidata": coord_wd, "near_duplicate_coords": near, "spike_regression": regress}
    (PROC / "lines_check.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    sid = {s["id"]: s for s in stations}
    if not a.no_plots:
        outdir = REP / "lines"
        outdir.mkdir(parents=True, exist_ok=True)
        for old in outdir.glob("*.png"):
            old.unlink()
        font = find_font()
        for r in seq:
            plot_sequence(r, sid, outdir, font)
        print(f"[08] plots: {len(seq)} → {outdir.relative_to(ROOT)} (font={'NanumGothic' if font else 'default'})")
    write_reports(doc, sid, wm)
    tot = {"sequences": len(seq), "ratio_flagged": sum(r["ratio"] > gcfg["opt_ratio_flag"] for r in seq),
           "edges": sum(len(r["edges"]) for r in seq),
           "edges_wd_adjacent": sum(e["wikidata"] == "adjacent" for r in seq for e in r["edges"]),
           "edges_wd_not_adjacent": sum(e["wikidata"] == "not_adjacent" for r in seq for e in r["edges"]),
           "edges_wd_not_adjacent_weak": sum(e["wikidata"] == "not_adjacent_weak" for r in seq for e in r["edges"]),
           "edges_geometry_flag": sum(bool(e["geometry"]) for r in seq for e in r["edges"]),
           "edges_both": sum(e["both"] for r in seq for e in r["edges"]),
           "wd_extra_adjacent": sum(len(r["wikidata_extra_adjacent"]) for r in seq),
           "coords_vs_wikidata_flagged": len(coord_wd), "near_duplicate_coords": len(near),
           "spike_flags": sum(len(r["spike_flags"]) for r in seq)}
    print(json.dumps({"match": doc["match_stats"], "totals": tot}, ensure_ascii=False))
    return 0


def write_reports(doc, sid, wm):
    seq = doc["sequences"]
    g = doc["thresholds"]["line_geometry"]
    L = ["# N2 노선 순서 검증 (OSM 없이)", "", "생성: `python3 pipeline/08_validate_lines.py`. 임계값: `config/validation.yaml`", "",
         "근거 1 = 좌표 기하 (2-opt 최적 경로 비교, 급반전, 국소 스왑). 근거 2 = Wikidata P197 인접역. "
         "`config/kr_lines.yaml` 수정은 두 근거가 같은 결론일 때만 한다.", "",
         "## Wikidata 매칭", "", "| 방법 | 역 레코드 수 |", "| :- | -: |"]
    L += [f"| {k} | {v} |" for k, v in doc["match_stats"].items()]
    L += ["", "unique = 이름 후보 1개, adj = 이웃 역과 P197 인접인 후보, nearest = 동률이라 거리로 고름, "
          "coord_fallback = 같은 이름 아이템이 없어 가까운 아이템을 붙임(라벨 차이, 좌표 검사 제외), no_candidate = 매칭 없음", "",
          "| 우리 역 | Wikidata 라벨 (coord_fallback) | 거리(m) |", "| :- | :- | -: |"]
    L += [f"| {sid[k]['name_ko']} ({sid[k]['line_name']}) | {m['wd_label']} | {m['distance_m']} |"
          for k, m in sorted(doc["match"].items()) if m["method"] == "coord_fallback"]
    L += ["",
          "## 시퀀스별 요약", "",
          f"ratio = 현재 길이 / 좌표 최적 경로 길이. {g['opt_ratio_flag']} 초과면 순서 의심.", "",
          "| 노선 | 시퀀스 | 역 | 현재 km | 최적 km | ratio | 기하 의심 엣지 | WD 비인접 | WD 매칭 안 됨 | 둘 다 | WD 추가 인접 | PNG |",
          "| :- | :- | -: | -: | -: | -: | -: | -: | -: | -: | -: | :- |"]
    for r in seq:
        e = r["edges"]
        L.append(f"| {r['line_name']} | {r['sequence']} | {r['n']} | {r['length_current_m'] / 1000:.1f} | {r['length_optimal_m'] / 1000:.1f} | "
                 f"{'**' if r['ratio'] > g['opt_ratio_flag'] else ''}{r['ratio']:.3f}{'**' if r['ratio'] > g['opt_ratio_flag'] else ''} | "
                 f"{sum(bool(x['geometry']) for x in e)} | {sum(x['wikidata'].startswith('not_adjacent') for x in e)} | "
                 f"{sum(x['wikidata'] in ('unmatched', 'same_item') for x in e)} | {sum(x['both'] for x in e)} | {len(r['wikidata_extra_adjacent'])} | "
                 f"[png](lines/{r['line']}__{r['sequence']}.png) |")
    L += ["", "## 의심 엣지 상세", "", "기하 또는 Wikidata 중 하나라도 걸린 엣지. '둘 다'가 보정 후보.",
          "not_adjacent_weak = 한쪽 역의 Wikidata 아이템이 시퀀스 이웃 누구와도 P197 인접이 아님 (그 노선용 아이템이 없을 가능성이 크지만 순서 오류일 수도 있음).", "",
          "| 노선 | 시퀀스 | A | B | 거리(m) | 기하 | Wikidata | 둘 다 |", "| :- | :- | :- | :- | -: | :- | :- | :- |"]
    for r in seq:
        for e in r["edges"]:
            if e["geometry"] or e["wikidata"].startswith("not_adjacent"):
                L.append(f"| {r['line']} | {r['sequence']} | {e['a_name']} | {e['b_name']} | {e['distance_m']} | "
                         f"{', '.join(e['geometry']) or '-'} | {e['wikidata']} | {'**예**' if e['both'] else '-'} |")
    L += ["", "## Wikidata에는 인접인데 시퀀스에서 비연속인 쌍", "",
          "같은 시퀀스 안에 둘 다 있고, 우리 그래프 어떤 노선에서도 이웃이 아닌데 Wikidata P197은 인접이라고 하는 쌍.", "",
          "| 노선 | 시퀀스 | A (위치) | B (위치) | 거리(m) |", "| :- | :- | :- | :- | -: |"]
    n_extra = 0
    for r in seq:
        for x in r["wikidata_extra_adjacent"]:
            n_extra += 1
            L.append(f"| {r['line']} | {r['sequence']} | {x['a_name']} ({x['pos'][0]}) | {x['b_name']} ({x['pos'][1]}) | {x['distance_m']} |")
    if not n_extra:
        L.append("| - | - | - | - | - |")
    L += ["", "## Wikidata 매칭이 안 된 엣지", "", "| 노선 | A | B | 사유 |", "| :- | :- | :- | :- |"]
    um = [(r, e) for r in seq for e in r["edges"] if e["wikidata"] in ("unmatched", "same_item")]
    for r, e in um:
        why = e["wikidata"]
        if why == "unmatched":
            miss = [n for n, x in ((e["a_name"], e["a"]), (e["b_name"], e["b"])) if not doc["match"][x]["qid"]]
            why = "후보 없음: " + ", ".join(miss)
        L.append(f"| {r['line']} | {e['a_name']} | {e['b_name']} | {why} |")
    if not um:
        L.append("| - | - | - | - |")
    (REP / "n2_lines_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    c = doc["thresholds"]["coords"]
    L = ["# N3 좌표 검증", "", "생성: `python3 pipeline/08_validate_lines.py`. 임계값: `config/validation.yaml` coords", "",
         "## 1. 노선 내 좌표 스파이크", "",
         f"이웃 두 역과 모두 {c['spike_min_m']}m 이상 떨어져 있고, 그 거리가 이웃끼리 거리의 {c['spike_ratio']}배 이상이면 스파이크. "
         f"끝점은 바로 옆 구간이 그다음 구간의 {c['spike_end_ratio']}배 이상이면 의심.", "",
         "| 노선 | 시퀀스 | 역 | 앞 구간(m) | 뒤 구간(m) | 이웃끼리(m) |", "| :- | :- | :- | -: | -: | -: |"]
    n = 0
    for r in seq:
        for f in r["spike_flags"]:
            n += 1
            L.append(f"| {r['line']} | {r['sequence']} | {sid[r['station_ids'][f['i']]]['name_ko']}{' (끝점)' if f.get('end') else ''} | "
                     f"{f['d_prev']} | {f['d_next'] if f['d_next'] is not None else '-'} | {f['d_skip']} |")
    if not n:
        L.append("| - | - | 없음 | - | - | - |")
    L += ["", "### 검출력 확인: 이미 보정한 좌표를 원래 값으로 되돌렸을 때", "",
          "Wikidata 매칭은 이름 + 이웃 P197 인접으로 하므로 좌표가 틀려도 같은 아이템을 고른다.", "",
          "| 역 | 노선 | 스파이크 검사 | 근접 중복 검사 | Wikidata 좌표 비교 | 가장 가까운 다른 역 |", "| :- | :- | :- | :- | :- | :- |"]
    for x in doc["spike_regression"]:
        L.append(f"| {x['name']} | {x['line']} | {'잡힘' if x['detected_by_spike'] else '못 잡음'} | {'잡힘' if x['detected_by_near_dup'] else '못 잡음'} | "
                 f"{'잡힘' if x['detected_by_wikidata'] else '못 잡음'} ({x['wikidata_m']}m) | {x['nearest_other']} {x['nearest_other_m']}m |")
    L += ["", "스파이크 검사는 '다른 지역 좌표가 섞인' 경우(양원)를, 근접 중복 검사는 인접역 좌표 복사(마곡·이촌)를 잡는다. "
          "Wikidata 좌표 비교는 세 건 모두 잡는지 위 표 참고.", "",
          "## 2. Wikidata 좌표(P625)와 비교", "",
          f"Wikidata 아이템 매칭(이름 + 이웃 P197 인접 우선)이 된 역 중 거리가 {c['wikidata_mismatch_m']}m 넘는 것.", "",
          "| 역 | 노선 | Wikidata | 매칭 방법 | 이웃 인접 수 | 거리(m) | 우리 좌표 | Wikidata 좌표 |", "| :- | :- | :- | :- | -: | -: | :- | :- |"]
    for x in doc["coords_vs_wikidata"]:
        L.append(f"| {x['name']} | {x['line']} | {x['qid']} {x['wd_label']} | {x['method']} | {x['adj_score']} | {x['distance_m']} | "
                 f"{x['ours'][0]:.5f}, {x['ours'][1]:.5f} | {x['wikidata'][0]:.5f}, {x['wikidata'][1]:.5f} |")
    if not doc["coords_vs_wikidata"]:
        L.append("| 없음 | | | | | | | |")
    L += ["", "## 3. 다른 클러스터인데 좌표가 거의 같은 역 (좌표 복사 의심)", "",
          f"{c['near_duplicate_m']}m 미만.", "", "| A | B | 거리(m) |", "| :- | :- | -: |"]
    L += [f"| {x['a_name']} ({x['a']}) | {x['b_name']} ({x['b']}) | {x['distance_m']} |" for x in doc["near_duplicate_coords"]] or ["| 없음 | | |"]
    (REP / "n3_coords_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
