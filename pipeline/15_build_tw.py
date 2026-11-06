#!/usr/bin/env python3
"""B1-2. 타이베이 대도시권 역·노선·승차 엣지 정제 (Wikidata 원문 → 한국과 같은 스키마).

- 역: P16 ∈ 범위 시스템 또는 P81 ∈ 범위 노선, 사용 중(P5817), 좌표가 bbox 안, 개통일 ≤ as_of. 노선별 레코드 1개
  (한국 표준데이터처럼 '노선별 역'). id = tw:<노선>:<역번호>
- 이름: Wikidata에 공식명(P1448)이 거의 없어서(범위 내 0건) 라벨(zh-hant → zh-tw → zh, en)을 official=False,
  source=wikidata_label로 넣는다. 공식명만 쓰는 ruleset은 이 이름을 매칭에 쓰지 않는다 (phase1 보고서).
- 순서: P197(인접역) 중 P81 한정자가 그 노선인 진술 + 한정자 없는 진술은 역번호가 이어질 때만. 순환은 역번호
  비연속 엣지부터 끊는다. 본선 = 가장 긴 경로, 나머지는 지선 (metro_portal/lineseq.py). 방향은 역번호 오름차순.

입력: data/raw/wikidata_tw/{stations,codes,adjacency,lines}.json, config/tw_scope.yaml
출력: data/processed/tw/{stations,lines,ride_edges,lines_validation}.json, docs/reports/b1_taipei_data.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.lineseq import break_cycles, code_consecutive, code_key, decompose, parse_code  # noqa: E402
from metro_portal.lineval import dist_matrix, optimize_order, path_length  # noqa: E402

RAW = ROOT / "data" / "raw" / "wikidata_tw"
OUT = ROOT / "data" / "processed" / "tw"


def q(u):
    return u.rsplit("/", 1)[1]


def rows(name):
    return json.loads((RAW / f"{name}.json").read_text(encoding="utf-8"))["results"]["bindings"]


def val(v):
    return q(v["value"]) if v["type"] == "uri" else v["value"]


def display_name(label: str) -> str:
    """표시용: 라벨 끝의 '站'은 떼고 '車站'은 둔다 (台北車站). 괄호 설명은 그대로 (정규화가 지운다)."""
    if label.endswith("站") and not label.endswith("車站") and len(label) > 2:
        return label[:-1]
    return label


def main() -> int:
    scope = yaml.safe_load(open(ROOT / "config" / "tw_scope.yaml", encoding="utf-8"))
    meta_raw = json.loads((RAW / "fetch_meta.json").read_text(encoding="utf-8"))
    line_of = {}
    for ln in scope["lines"]:
        for x in ln["qids"]:
            line_of[x] = ln["id"]
    ldef = {ln["id"]: ln for ln in scope["lines"]}

    st = defaultdict(lambda: defaultdict(set))
    for b in rows("stations"):
        k = q(b["st"]["value"])
        for kk, v in b.items():
            if kk == "off":
                st[k]["off"].add((v["value"], v.get("xml:lang", "")))
            elif kk != "st":
                st[k][kk].add(val(v))
    codes, slines = defaultdict(set), defaultdict(set)
    for b in rows("codes"):
        k = q(b["st"]["value"])
        if "code" in b:
            codes[k].add(b["code"]["value"])
        if "line" in b:
            slines[k].add(q(b["line"]["value"]))
    linfo = defaultdict(lambda: defaultdict(set))
    for b in rows("lines"):
        k = q(b["line"]["value"])
        for kk, v in b.items():
            if kk != "line":
                linfo[k][kk].add(val(v))

    bb, as_of, recent = scope["bbox"], scope["as_of"], scope["recent_since"]
    excluded, recent_open = [], []
    keep = {}
    for k in sorted(st, key=lambda x: (len(x), x)):
        v = st[k]
        lab = sorted(v.get("zh_hant") or v.get("zh_tw") or v.get("zh") or v.get("en") or {k})[0]
        ls = sorted({line_of[x] for x in slines[k] if x in line_of})
        if not ls:
            continue  # 범위 노선이 아닌 아이템 (노선 아이템 자체, 국철역 등)
        why = None
        if not (v.get("state", set()) & set(scope["include_states"])):
            why = f"사용 상태 아님 ({','.join(sorted(v.get('state', {'-'})))})"
        elif not v.get("coord"):
            why = "좌표 없음"
        else:
            lon, lat = map(float, sorted(v["coord"])[0][6:-1].split())
            if not (bb["lat_min"] <= lat <= bb["lat_max"] and bb["lon_min"] <= lon <= bb["lon_max"]):
                why = f"bbox 밖 ({lat:.3f}, {lon:.3f})"
            elif v.get("open") and min(v["open"])[:10] > as_of:
                why = f"개통일 {min(v['open'])[:10]} > {as_of}"
        if why:
            excluded.append({"qid": k, "label": lab, "lines": ls, "codes": sorted(codes[k]), "reason": why})
            continue
        keep[k] = (lat, lon, lab, ls)
        if v.get("open") and max(v["open"])[:10] >= recent:
            recent_open.append({"qid": k, "label": lab, "lines": ls, "codes": sorted(codes[k]), "opened": max(v["open"])[:10]})

    # 노선별 역 레코드. 같은 노선에서 역번호가 여러 아이템에 겹치면(Wikidata 오류) id에 아이템 id를 붙인다
    claim = Counter()
    for k, (lat, lon, lab, ls) in keep.items():
        for L in ls:
            for c in codes[k]:
                if (parse_code(c) or ("",))[0] == ldef[L]["code_prefix"]:
                    claim[(L, c)] += 1
    dup_codes = sorted({f"{L}:{c}" for (L, c), n in claim.items() if n > 1})
    stations, rec_of = [], {}
    for k, (lat, lon, lab, ls) in sorted(keep.items(), key=lambda kv: (len(kv[0]), kv[0])):
        v = st[k]
        zh = sorted(v.get("zh_hant") or v.get("zh_tw") or v.get("zh") or [""])[0]
        en = sorted(v.get("en") or [""])[0]
        names = []
        for text, lang in sorted(v.get("off", ())):
            lg = (lang or "").lower()
            if lg.startswith("zh"):
                names.append({"text": text, "lang": "zh", "script": "Hant", "source": "wikidata_p1448", "official": True, "kind": "primary"})
            elif lg == "en":
                names.append({"text": text, "lang": "en", "script": "Latn", "source": "wikidata_p1448", "official": True, "kind": "primary"})
        if zh:
            names.append({"text": zh, "lang": "zh", "script": "Hant", "source": "wikidata_label", "official": False, "kind": "primary"})
        if en:
            names.append({"text": en, "lang": "en", "script": "Latn", "source": "wikidata_label", "official": False, "kind": "primary"})
        for L in ls:
            pref = ldef[L]["code_prefix"]
            cs = sorted((c for c in codes[k] if (parse_code(c) or ("",))[0] == pref), key=code_key)
            code = cs[0] if cs else ""
            sid = f"tw:{L}:{code}:{k}" if f"{L}:{code}" in dup_codes else f"tw:{L}:{code or k}"
            stations.append({"id": sid, "code": code, "name_ko": display_name(zh or en or k), "name_zh": zh, "name_en": en,
                             "lat": round(lat, 7), "lon": round(lon, 7), "line_no": L, "line_name": "",
                             "line_group": f"TW:{L}", "operator": "", "region": scope["city"], "country": "TW",
                             "wikidata": k, "names": names, "source": "wikidata", "transfer_flag": False})
            rec_of[(k, L)] = sid
    sidx = {s["id"]: s for s in stations}

    # 인접 관계
    adj = defaultdict(set)
    for b in rows("adjacency"):
        a, t = q(b["st"]["value"]), q(b["adj"]["value"])
        adj[(a, t)].add(q(b["line"]["value"]) if "line" in b else None)

    lines, edges, val_lines = [], [], []
    for ln in scope["lines"]:
        L = ln["id"]
        nodes = sorted(sid for (k, LL), sid in rec_of.items() if LL == L)
        if not nodes:
            continue
        code = {sid: sidx[sid]["code"] for sid in nodes}
        qid_rec = {k: sid for (k, LL), sid in rec_of.items() if LL == L}
        cand, ignored = set(), []
        for (a, t), quals in adj.items():
            if a not in qid_rec or t not in qid_rec or a == t:
                continue
            ra, rt = qid_rec[a], qid_rec[t]
            e = tuple(sorted((ra, rt)))
            if quals & set(ln["qids"]):
                cand.add(e)
            elif None in quals and code_consecutive(code[ra], code[rt], set(code.values())):
                cand.add(e)
            else:
                ignored.append({"a": sidx[e[0]]["name_ko"], "b": sidx[e[1]]["name_ko"], "codes": f"{code[e[0]]}–{code[e[1]]}",
                                "qualifiers": sorted(x or "-" for x in quals)})
        kept, dropped = break_cycles(nodes, sorted(cand), code)
        seqs = decompose(nodes, kept, code)
        # 시퀀스 id: 본선 main, 지선은 끝 역번호
        out_seqs = []
        for i, sq in enumerate(seqs):
            sq_id = "main" if i == 0 else f"branch-{code[sq[-1]] or sq[-1].rsplit(':', 1)[1]}"
            out_seqs.append({"id": sq_id, "station_ids": sq, "circular": False, "directed": False})
            for a, b in zip(sq, sq[1:]):
                x, y = sorted((a, b))
                edges.append({"line": L, "sequence": sq_id, "a": x, "b": y,
                              "distance_m": round(haversine_m(sidx[x]["lat"], sidx[x]["lon"], sidx[y]["lat"], sidx[y]["lon"]), 1)})
        mains = [ld for ld in ln["qids"] if ld in linfo]
        main_q = mains[0] if mains else ln["qids"][0]
        zh_name = sorted(linfo[main_q].get("zh_hant") or linfo[main_q].get("zh") or [L])[0]
        en_name = sorted(linfo[main_q].get("en") or [""])[0]
        op = "/".join(sorted({scope["operators"].get(o, o) for o in linfo[main_q].get("op", set())}))
        for sid in nodes:
            sidx[sid]["line_name"] = zh_name
            sidx[sid]["operator"] = op
        # 역번호 검사: 채택 엣지 중 역번호 비연속, 역번호는 이어지는데 인접 진술 없음
        kept_set = {frozenset(e) for e in kept}
        lc = set(code.values())
        noncons = [{"a": sidx[a]["name_ko"], "b": sidx[b]["name_ko"], "codes": f"{code[a]}–{code[b]}"}
                   for a, b in kept if not code_consecutive(code[a], code[b], lc)]
        missing = [{"a": sidx[a]["name_ko"], "b": sidx[b]["name_ko"], "codes": f"{code[a]}–{code[b]}"}
                   for i, a in enumerate(sorted(nodes)) for b in sorted(nodes)[i + 1:]
                   if code_consecutive(code[a], code[b], lc) and frozenset((a, b)) not in kept_set]
        lines.append({"id": L, "name": zh_name, "name_en": en_name, "source_no": L, "source_name": zh_name, "operator": op,
                      "city": scope["city"], "country": "TW", "color": ln["color"], "pools": [f"TW:{L}"],
                      "sequences": out_seqs, "patched": False, "wikidata": ln["qids"]})
        # 두 번째 근거: 좌표 기하 (2차 08 단계와 같은 최적 경로 비교). 현재 순서 길이 / 좌표 최적 순서 길이
        geo = []
        for s in out_seqs:
            pts = [(sidx[x]["lat"], sidx[x]["lon"]) for x in s["station_ids"]]
            if len(pts) < 4:
                geo.append({"sequence": s["id"], "ratio": None, "same_order": None})
                continue
            cur = path_length(list(range(len(pts))), dist_matrix(pts))
            opt_order, opt_len = optimize_order(pts, current=list(range(len(pts))))
            geo.append({"sequence": s["id"], "ratio": round(cur / opt_len, 4),
                        "same_order": opt_order in (list(range(len(pts))), list(range(len(pts)))[::-1])})
        val_lines.append({"line": L, "name": zh_name, "stations": len(nodes), "edges_candidate": len(cand), "edges_kept": len(kept),
                          "geometry": geo,
                          "dropped_cycle": [{"a": sidx[a]["name_ko"], "b": sidx[b]["name_ko"], "codes": f"{code[a]}–{code[b]}"} for a, b in dropped],
                          "ignored": ignored, "kept_non_consecutive": noncons, "consecutive_without_adjacency": missing,
                          "sequences": [(s["id"], len(s["station_ids"])) for s in out_seqs],
                          "components": len([s for s in out_seqs if s["id"] == "main"]) + sum(1 for s in out_seqs if s["id"] != "main" and s["station_ids"][0] not in {x for o in out_seqs for x in o["station_ids"] if o is not s})})
    edges.sort(key=lambda e: (e["line"], e["a"], e["b"]))
    stations.sort(key=lambda s: s["id"])
    # 4차 Q6-1: 이름 출처 등급. zh-Hant 라벨 = native_label(현지어 라벨, 준공식), en 라벨 = foreign_label
    from metro_portal.names import assign_grades
    assign_grades(stations, "TW")
    out_long = [{**e, "a_name": sidx[e["a"]]["name_ko"], "b_name": sidx[e["b"]]["name_ko"]} for e in edges if e["distance_m"] > scope["adjacent_max_m"]]
    langs = Counter(f"{n['lang']}-{n['script']}-{n['source']}" for s in stations for n in s["names"])
    meta = {"description": "타이베이 대도시권 도시철도 (타이베이 메트로·신베이 메트로·타오위안 공항 MRT). 노선별 역 단위.",
            "source": "Wikidata Query Service (CC0)", "fetched_at": {k: v["fetched_at"] for k, v in meta_raw.items()},
            "counts": {"stations": len(stations), "physical_items": len(keep), "lines": len(lines), "ride_edges": len(edges),
                       "excluded": len(excluded), "names_by_lang_script_source": dict(sorted(langs.items())),
                       "official_names": sum(1 for s in stations for n in s["names"] if n["official"]),
                       "names_by_grade": dict(sorted(Counter(n["grade"] for s in stations for n in s["names"]).items()))},
            "excluded": excluded, "recent_openings": sorted(recent_open, key=lambda r: (r["opened"], r["qid"])),
            "duplicate_codes": dup_codes,
            "missing_zh_label": sorted({s["wikidata"] for s in stations if not s["name_zh"]}),
            "missing_en_label": sorted({s["wikidata"] for s in stations if not s["name_en"]})}
    OUT.mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # noqa: E731
    dump("stations.json", {"meta": meta, "stations": stations})
    dump("lines.json", {"lines": lines})
    dump("ride_edges.json", {"edges": edges})
    dump("lines_validation.json", {"lines": val_lines, "long_edges": out_long})
    write_report(meta, lines, val_lines, out_long, sidx)
    print(json.dumps(meta["counts"], ensure_ascii=False))
    return 0


def geo_txt(geo):
    return ", ".join("{}={:.3f}".format(g["sequence"], g["ratio"]) for g in geo if g["ratio"]) or "-"


def write_report(meta, lines, val_lines, out_long, sidx):
    c = meta["counts"]
    L = ["# B1 타이베이 데이터 (Wikidata 대체 수집)", "", "생성: `python3 pipeline/14_fetch_tw_wikidata.py && python3 pipeline/15_build_tw.py`", "",
         "Geofabrik 대만 추출본과 대만 공식 오픈데이터 호스트(data.taipei, data.gov.tw, TDX, 운영사 사이트)가 세션 네트워크에서 막혀",
         "Wikidata(CC0)로 대체했다. 역번호(P296)는 운영사 번호, 인접(P197)·좌표(P625)·사용 상태(P5817)·개통일(P1619)은 Wikidata 진술이다.", "",
         f"- 원문 수집 시각: " + ", ".join(f"{k} {v}" for k, v in meta["fetched_at"].items()),
         f"- 물리 역(아이템) {c['physical_items']}, 노선별 역 레코드 {c['stations']}, 노선 {c['lines']}, 승차 엣지 {c['ride_edges']}, 제외 {c['excluded']}",
         f"- 이름: " + ", ".join(f"{k} {v}" for k, v in c["names_by_lang_script_source"].items()),
         f"- **공식명(P1448) {c['official_names']}건.** 이름은 전부 Wikidata 라벨(커뮤니티 표기)이라 official=False로 저장했다.", "",
         "## 노선", "", "기하 = 현재 순서 길이 / 좌표 최적 순서 길이 (4역 이상 시퀀스, 1.000이면 좌표상 최적 순서와 같다. 2차 08 단계와 같은 방법)", "",
         "| id | 이름 | 영문 | 운영 | 역 | 시퀀스 (역 수) | 기하 | 후보 엣지 | 채택 | 순환 제거 | 역번호 비연속 채택 | 역번호 연속인데 인접 없음 |",
         "| :- | :- | :- | :- | -: | :- | :- | -: | -: | :- | :- | :- |"]
    vmap = {v["line"]: v for v in val_lines}
    for ln in lines:
        v = vmap[ln["id"]]
        fmt = lambda lst: "; ".join(f"{x['a']}–{x['b']}({x['codes']})" for x in lst) or "-"  # noqa: E731
        L.append(f"| {ln['id']} | {ln['name']} | {ln['name_en']} | {ln['operator']} | {v['stations']} | "
                 f"{', '.join(f'{a}({n})' for a, n in v['sequences'])} | {geo_txt(v['geometry'])} | "
                 f"{v['edges_candidate']} | {v['edges_kept']} | {fmt(v['dropped_cycle'])} | "
                 f"{fmt(v['kept_non_consecutive'])} | {fmt(v['consecutive_without_adjacency'])} |")
    L += ["", "역번호 비연속 채택 엣지는 지선 분기(대교두 O12 → 싼충궈샤오 O50 등)이고, 순환 제거는 한정자 없는 옛 철도선 진술이 만든 삼각형이다.", "",
          "## 노선별 정차 순서", ""]
    for ln in lines:
        for sq in ln["sequences"]:
            L.append(f"- **{ln['id']} {sq['id']}**: " + " → ".join(f"{sidx[s]['name_ko']}({sidx[s]['code']})" for s in sq["station_ids"]))
    L += ["", "## 다른 노선 한정자라 안 쓴 인접 진술", ""]
    ign = [(v["line"], x) for v in val_lines for x in v["ignored"]]
    L += [f"- {ln}: {x['a']}–{x['b']} ({x['codes']}, 한정자 {', '.join(x['qualifiers'])})" for ln, x in ign] or ["없음."]
    L += ["", f"## 인접역 거리 {6000}m 초과", ""]
    L += [f"- {e['line']}: {e['a_name']}–{e['b_name']} {e['distance_m']:.0f}m" for e in out_long] or ["없음."]
    L += ["", "## 최근 개통 표기 (검증 필요, Wikidata 단일 근거)", "", "| 역 | 역번호 | 노선 | 개통일 |", "| :- | :- | :- | :- |"]
    L += [f"| {r['label']} | {', '.join(r['codes'])} | {', '.join(r['lines'])} | {r['opened']} |" for r in meta["recent_openings"]] or ["| - | - | - | - |"]
    L += ["", "## 제외한 아이템", "", "| 아이템 | 라벨 | 노선 | 역번호 | 사유 |", "| :- | :- | :- | :- | :- |"]
    L += [f"| {x['qid']} | {x['label']} | {', '.join(x['lines'])} | {', '.join(x['codes'])} | {x['reason']} |" for x in meta["excluded"]]
    L += ["", "## 같은 노선에서 역번호가 겹치는 아이템 (Wikidata 오류 의심)", "",
          "id에 아이템 id를 붙여 따로 두고, 순서는 인접 진술(P197)로 정했다. 역번호 값은 고치지 않았다.", ""]
    for dc in meta["duplicate_codes"]:
        L.append(f"- {dc}: " + ", ".join(f"{s['name_ko']}({s['wikidata']})" for s in sidx.values() if f"{s['line_no']}:{s['code']}" == dc))
    if not meta["duplicate_codes"]:
        L.append("없음.")
    L += ["", f"zh 라벨 없는 아이템: {', '.join(meta['missing_zh_label']) or '없음'} · en 라벨 없는 아이템: {', '.join(meta['missing_en_label']) or '없음'}"]
    (ROOT / "docs" / "reports" / "b1_taipei_data.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
