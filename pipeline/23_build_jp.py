#!/usr/bin/env python3
"""5차 T1-2. 도쿄권(Phase 1b) 역·노선·승차 엣지 정제 (Wikidata 원문 → 한국·타이베이와 같은 스키마).

- 역: 범위 노선(P81)에 걸린 아이템 중 1도 3현(P131 사슬, 없으면 좌표 bbox로 받고 의심 목록에 올림), 사용 중, 개통일 ≤ as_of.
  노선별 레코드 1개 (id = jp:<노선 QID>:<역번호 또는 아이템 QID>).
- 이름 (4차 Q6-1 현지어 라벨 준공식 규칙): ja 라벨 = native_label(lang ja, script Jpan), 공식명 P1448(ja) = official,
  en 라벨 = foreign_label. 라벨의 동음이의 괄호('府中駅 (東京都)')와 끝의 '駅'는 표시 이름에서 뗀다.
- 순서: P197(인접역) 중 노선 한정자(pq:P81)가 그 노선인 진술 + 한정자 없는 진술은 두 역의 공통 범위 노선이 그 노선 하나일 때만.
  JR은 인프라 노선(東北本線 등) 단위라 병행 선로(京浜東北·宇都宮 계통)로 순환이 생긴다 → 신장 숲으로 본선·지선 시퀀스를 만들고
  순환을 닫는 엣지도 버리지 않고 2역짜리 연결 시퀀스(link-*)로 남긴다 (타이베이는 버렸다: 오류였기 때문).
  방향은 그 노선 역번호 오름차순. 노선 역번호 접두어 = 한정자 붙은 역번호의 최빈 접두어(역 절반 이상일 때).
- 검증 (두 근거): (1) P197 진술 자체 + 대칭성·역번호 연속성, (2) 좌표 기하 (현재 순서 길이 / 좌표 최적 순서 길이).
  어긋나면 의심 목록 (고치지 않는다).

입력: data/raw/wikidata_jp/*.json, config/jp_scope.yaml
출력: data/processed/jp/{stations,lines,ride_edges,lines_validation}.json, docs/reports/t1_tokyo_data.md
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.geo import haversine_m  # noqa: E402
from metro_portal.lineseq import break_cycles, code_consecutive, code_key, decompose  # noqa: E402
from metro_portal.lineval import dist_matrix, optimize_order, path_length  # noqa: E402

RAW = ROOT / "data" / "raw" / "wikidata_jp"
OUT = ROOT / "data" / "processed" / "jp"
_PAREN = re.compile(r"\s*[(（].*?[)）]\s*$")


def q(u):
    return u.rsplit("/", 1)[1]


def rows(name):
    return json.loads((RAW / f"{name}.json").read_text(encoding="utf-8"))["results"]["bindings"]


def val(v):
    return q(v["value"]) if v["type"] == "uri" else v["value"]


_CFG = {}


def strip_label(label: str) -> str:
    """ja 라벨 → 역 이름: 동음이의 괄호('府中駅 (東京都)')와 운영사 구분 접두어('JR東日本', '東京メトロ南北線' 등, 공식명 아님)를
    떼고, 끝의 '駅'·'停留場'를 뗀다 (한 글자 이상 남을 때: 柏駅 → 柏)."""
    s = _PAREN.sub("", label).strip()
    if _CFG.get("prefix"):
        s = _CFG["prefix"].sub("", s).strip() or s
    for suf in _CFG.get("suffixes", ("駅",)):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
            break
    return s


def norm_code(code: str, pat) -> str | None:
    m = pat.match(code.strip().upper().replace("－", "-").replace("　", " ")) if code else None
    if not m:
        return None
    return f"{m.group(1)}{int(m.group(2)):02d}{m.group(3).lower()}"


def main() -> int:
    scope = yaml.safe_load(open(ROOT / "config" / "jp_scope.yaml", encoding="utf-8"))
    meta_raw = json.loads((RAW / "fetch_meta.json").read_text(encoding="utf-8"))
    pat = re.compile(scope["code_pattern"])
    _CFG.update(prefix=re.compile(scope["label_prefix_pattern"]), suffixes=tuple(scope["name_suffixes"]))
    nonst = re.compile(scope["non_station_pattern"])
    ops = set(scope["operators"])
    as_of, recent, bb = scope["as_of"], scope["recent_since"], scope["bbox"]

    # ---- 노선 ----
    linfo = defaultdict(lambda: defaultdict(set))
    for b in rows("lines"):
        k = q(b["line"]["value"])
        for kk, v in b.items():
            if kk != "line":
                linfo[k][kk].add(val(v))
    # ---- 역 ----
    st = defaultdict(lambda: defaultdict(set))
    for b in rows("stations"):
        k = q(b["st"]["value"])
        for kk, v in b.items():
            if kk == "off":
                st[k]["off"].add((v["value"], v.get("xml:lang", "")))
            elif kk != "st":
                st[k][kk].add(val(v))
    prefs = defaultdict(set)
    for b in rows("prefs"):
        prefs[q(b["st"]["value"])].add(q(b["pref"]["value"]))
    has131 = {q(b["st"]["value"]) for b in rows("has_p131")}
    codes = defaultdict(list)   # st -> [(code, cline, cop)]
    for b in rows("codes"):
        c = norm_code(b["code"]["value"], pat)
        if c:
            codes[q(b["st"]["value"])].append((c, q(b["cline"]["value"]) if "cline" in b else None, q(b["cop"]["value"]) if "cop" in b else None))
    for k in codes:
        codes[k] = sorted(set(codes[k]), key=lambda x: (x[0], x[1] or "", x[2] or ""))

    def coord(k):
        pts = sorted(x for x in st[k].get("coord", ()) if x.startswith("Point("))   # 값 모름(빈 노드) 표기는 건너뛴다
        if not pts:
            return None
        lon, lat = map(float, pts[0][6:-1].split())
        return lat, lon

    excluded, recent_open, p131_missing = [], [], []
    keep = {}
    transparent = set()   # 역이 아닌 시설: 인접 사슬에서 축약
    for k in sorted(st, key=lambda x: (len(x), x)):
        v = st[k]
        lab = sorted(v.get("ja") or v.get("en") or {k})[0]
        c = coord(k)
        in_pref = bool(prefs[k] & set(scope["prefectures"]))
        in_bbox = c is not None and bb["lat_min"] <= c[0] <= bb["lat_max"] and bb["lon_min"] <= c[1] <= bb["lon_max"]
        if not in_pref and not (k not in has131 and in_bbox):
            continue   # 범위(1도 3현) 밖. P131이 아예 없는 아이템만 좌표 범위로 받는다
        why = None
        if nonst.search(lab):
            transparent.add(k)
            why = "역이 아닌 시설 (신호장·분기점·화물역) — 인접 사슬은 건너뛰어 잇는다"
        elif v.get("state", set()) & set(scope["not_in_use_states"]):
            why = f"사용 상태 아님 ({','.join(sorted(v['state']))})"
        elif v.get("closed") and min(v["closed"])[:10] <= as_of:
            why = f"폐지일 {min(v['closed'])[:10]}"
        elif c is None:
            why = "좌표 없음"
        elif v.get("open") and min(v["open"])[:10] > as_of:
            why = f"개통일 {min(v['open'])[:10]} > {as_of}"
        if why:
            excluded.append({"qid": k, "label": lab, "reason": why})
            continue
        keep[k] = (c[0], c[1], lab)
        if not in_pref:
            p131_missing.append({"qid": k, "label": lab})
        if v.get("open") and max(v["open"])[:10] >= recent:
            recent_open.append({"qid": k, "label": lab, "opened": max(v["open"])[:10]})

    # 범위 노선: 범위 운영사, 제외 목록 밖, 폐지·해산 안 됨, 범위 안 역 min_stations 이상
    line_stations = defaultdict(set)
    for k in keep:
        for L in st[k].get("line", ()):
            line_stations[L].add(k)
    lines_skipped = []
    scope_lines = []
    for L in sorted(line_stations, key=lambda x: (len(x), x)):
        inf = linfo.get(L, {})
        name = sorted(inf.get("ja") or {L})[0]
        if not (inf.get("op", set()) & ops):
            continue
        why = None
        if L in scope["exclude_lines"]:
            why = f"제외 목록: {scope['exclude_lines'][L]}"
        elif inf.get("closed") and min(inf["closed"])[:10] <= as_of or inf.get("dissolved") and min(inf["dissolved"])[:10] <= as_of:
            why = "폐지·해산 표기"
        elif len(line_stations[L]) < scope["min_stations_in_scope"]:
            why = f"범위 안 역 {len(line_stations[L])}개"
        if why:
            lines_skipped.append({"qid": L, "name": name, "stations_in_scope": len(line_stations[L]), "reason": why})
            continue
        scope_lines.append(L)
    scope_set = set(scope_lines)

    # 노선 역번호 접두어: 한정자(pq:P81 = 노선)가 붙은 역번호의 최빈 접두어, 없으면 노선 역의 전체 역번호 최빈 (역 절반 이상)
    pref_of = {}
    for L in scope_lines:
        ss = line_stations[L]
        qual = Counter(re.match(r"[A-Z]+", c).group(0) for k in ss for c, cl, _ in codes[k] if cl == L)
        allp = Counter(re.match(r"[A-Z]+", c).group(0) for k in ss for c in {x[0] for x in codes[k]})
        for cnt in (qual, allp):
            if cnt:
                p, n = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0]
                if n >= max(2, len(ss) * 0.5):
                    pref_of[L] = p
                    break

    def code_on(k, L):
        cs = codes[k]
        exact = sorted({c for c, cl, _ in cs if cl == L and (L not in pref_of or c.startswith(pref_of[L]))})
        if exact:
            return exact[0]
        if L in pref_of:
            pp = sorted({c for c, _, _ in cs if re.match(r"[A-Z]+", c).group(0) == pref_of[L]}, key=code_key)
            return pp[0] if pp else ""
        return ""

    # ---- 인접 ----
    adj_q = defaultdict(set)    # (a, b) -> {한정자 노선 | None}
    for b in rows("adjacency"):
        a, t = q(b["st"]["value"]), q(b["adj"]["value"])
        adj_q[(a, t)].add(q(b["aline"]["value"]) if "aline" in b else None)

    def scope_lines_of(k):
        return {L for L in st[k].get("line", ()) if L in scope_set}

    stations, rec_of, sidx = [], {}, {}
    lines_out, edges, val_lines = [], [], []
    suspects = defaultdict(list)
    for L in scope_lines:
        inf = linfo[L]
        lname = sorted(inf.get("ja") or {L})[0]
        lid = f"jp-{L}"
        cand, unq_ignored, asym = set(), [], []
        added_members = set()
        for (a, t), quals in sorted(adj_q.items()):
            if a == t or (a not in keep and a not in transparent) or (t not in keep and t not in transparent):
                continue
            e = tuple(sorted((a, t)))
            if L in quals:
                cand.add(e)
                for x in e:
                    if L not in st[x].get("line", ()) and x in keep:
                        added_members.add(x)
            elif None in quals and L in st[a].get("line", ()) and L in st[t].get("line", ()):
                common = scope_lines_of(a) & scope_lines_of(t)
                if common == {L}:
                    cand.add(e)
                else:
                    unq_ignored.append(e)
        # 역이 아닌 시설 축약: 이웃이 둘이면 둘을 잇는다 (셋 이상이면 역번호·거리 순으로 사슬처럼). 사슬로 이어진 시설도 반복해서 지운다
        contracted = []
        while True:
            tn = sorted({x for e in cand for x in e if x in transparent})
            if not tn:
                break
            x = tn[0]
            nb = sorted({y for e in cand if x in e for y in e if y != x})
            cand = {e for e in cand if x not in e}
            if len(nb) >= 2:
                c0 = coord(x)
                nb.sort(key=lambda y: (haversine_m(*c0, *coord(y)) if (c0 and coord(y)) else 0, y))
                for y1, y2 in zip(nb, nb[1:]) if len(nb) > 2 else [tuple(nb)]:
                    if y1 != y2:
                        cand.add(tuple(sorted((y1, y2))))
                contracted.append(f"{st[x].get('ja', {x}) and sorted(st[x]['ja'])[0]} ({len(nb)}이웃)")
        # 대칭성: 한쪽만 그 노선 한정자로 인접을 적은 쌍
        for a, t in sorted(cand):
            fw, bw = L in adj_q.get((a, t), set()), L in adj_q.get((t, a), set())
            if fw != bw and (fw or bw):
                asym.append((a, t))
        members = (line_stations[L] | added_members)
        nodes_e = sorted({x for e in cand for x in e})
        isolated = sorted(members - set(nodes_e))
        if not nodes_e:
            lines_skipped.append({"qid": L, "name": lname, "stations_in_scope": len(members), "reason": "범위 안 인접 진술 없음"})
            continue
        code = {k: code_on(k, L) for k in nodes_e}
        # 같은 노선에서 역번호가 둘 이상 아이템에 겹치면 id에 아이템 id
        dupc = {c for c, n in Counter(c for c in code.values() if c).items() if n > 1}
        for k in nodes_e:
            c = code[k]
            sid = f"jp:{L}:{c}" if c and c not in dupc else f"jp:{L}:{k}"
            rec_of[(k, L)] = sid
        rcode = {rec_of[(k, L)]: code[k] for k in nodes_e}
        redges = sorted(tuple(sorted((rec_of[(a, L)], rec_of[(t, L)]))) for a, t in cand)
        kept, dropped = break_cycles(sorted(rcode), redges, rcode)
        seqs = decompose(sorted(rcode), kept, rcode)
        out_seqs = []
        for i, sq in enumerate(seqs):
            sq_id = "main" if i == 0 else f"branch-{rcode[sq[-1]] or sq[-1].rsplit(':', 1)[1]}"
            out_seqs.append({"id": sq_id, "station_ids": sq, "circular": False, "directed": False})
        # 순환을 닫는 엣지(병행 선로·급행 건너뛰기 진술)는 버리지 않고 2역 연결 시퀀스로 (그래프 엣지 보존)
        for j, (a, b) in enumerate(dropped):
            x, y = (a, b) if code_key(rcode[a]) <= code_key(rcode[b]) else (b, a)
            out_seqs.append({"id": f"link-{j + 1}", "station_ids": [x, y], "circular": False, "directed": False})
        ids_on = {x for s in out_seqs for x in s["station_ids"]}
        # 역 레코드
        op = "/".join(sorted(scope["operators"][o] for o in inf.get("op", set()) if o in scope["operators"]))
        for k in nodes_e:
            sid = rec_of[(k, L)]
            if sid not in ids_on or sid in sidx:
                continue
            lat, lon, lab = keep[k]
            v = st[k]
            ja = sorted(v.get("ja") or [""])[0]
            en = sorted(v.get("en") or [""])[0]
            names = []
            for text, lang in sorted(v.get("off", ())):
                if (lang or "").lower().startswith("ja"):
                    names.append({"text": strip_label(text), "lang": "ja", "script": "Jpan", "source": "wikidata_p1448", "official": True, "kind": "primary"})
            if ja:
                names.append({"text": strip_label(ja), "lang": "ja", "script": "Jpan", "source": "wikidata_label", "official": False, "kind": "primary"})
            if en:
                names.append({"text": _PAREN.sub("", en).strip(), "lang": "en", "script": "Latn", "source": "wikidata_label", "official": False, "kind": "primary"})
            offs = sorted(t for t, lg in v.get("off", ()) if (lg or "").lower().startswith("ja"))
            disp = strip_label(offs[0]) if offs else strip_label(ja or en or k)
            rec = {"id": sid, "code": code[k], "name_ko": disp, "name_ja": ja, "name_en": en,
                   "lat": round(lat, 7), "lon": round(lon, 7), "line_no": L, "line_name": lname, "line_group": f"JP:{lid}",
                   "operator": op, "region": scope["city"], "country": "JP", "wikidata": k, "names": names,
                   "source": "wikidata", "transfer_flag": False}
            stations.append(rec)
            sidx[sid] = rec
        for s in out_seqs:
            for a, b in zip(s["station_ids"], s["station_ids"][1:]):
                x, y = sorted((a, b))
                edges.append({"line": lid, "sequence": s["id"], "a": x, "b": y,
                              "distance_m": round(haversine_m(sidx[x]["lat"], sidx[x]["lon"], sidx[y]["lat"], sidx[y]["lon"]), 1)})
        color = sorted(inf.get("color") or [""])[0]
        lines_out.append({"id": lid, "name": lname, "name_en": sorted(inf.get("en") or [""])[0], "source_no": L, "source_name": lname,
                          "operator": op, "city": scope["city"], "country": "JP",
                          "color": f"#{color}" if re.fullmatch(r"[0-9A-Fa-f]{6}", color or "") else scope["default_color"],
                          "pools": [f"JP:{lid}"], "sequences": out_seqs, "patched": False, "wikidata": [L]})
        # ---- 검증 ----
        nm = lambda sid: sidx[sid]["name_ko"]  # noqa: E731
        lc = set(rcode.values())
        all_e = kept + [tuple(sorted(e)) for e in dropped]
        noncons = [(a, b) for a, b in all_e if rcode[a] and rcode[b] and rcode[a][:2] == rcode[b][:2] and not code_consecutive(rcode[a], rcode[b], lc)]
        es = {frozenset(e) for e in all_e}
        rs_sorted = sorted(rcode)
        missing = [(a, b) for i, a in enumerate(rs_sorted) for b in rs_sorted[i + 1:]
                   if rcode[a] and rcode[b] and code_consecutive(rcode[a], rcode[b], lc) and frozenset((a, b)) not in es]
        geo = []
        for s in out_seqs:
            if s["id"].startswith("link"):
                continue
            pts = [(sidx[x]["lat"], sidx[x]["lon"]) for x in s["station_ids"]]
            if len(pts) < 4:
                geo.append({"sequence": s["id"], "n": len(pts), "ratio": None})
                continue
            cur = path_length(list(range(len(pts))), dist_matrix(pts))
            _, opt_len = optimize_order(pts, current=list(range(len(pts))))
            geo.append({"sequence": s["id"], "n": len(pts), "ratio": round(cur / opt_len, 4)})
        long_e = [(a, b, round(haversine_m(sidx[a]["lat"], sidx[a]["lon"], sidx[b]["lat"], sidx[b]["lon"]))) for a, b in all_e
                  if haversine_m(sidx[a]["lat"], sidx[a]["lon"], sidx[b]["lat"], sidx[b]["lon"]) > scope["adjacent_max_m"]]
        vl = {"line": lid, "qid": L, "name": lname, "operator": op, "code_prefix": pref_of.get(L, ""), "stations": len(rcode),
              "members_p81": len(members), "edges": len(all_e), "sequences": [(s["id"], len(s["station_ids"])) for s in out_seqs],
              "cycle_links": [f"{nm(a)}–{nm(b)}" for a, b in dropped], "geometry": geo,
              "isolated_members": [keep[k][2] for k in isolated], "added_by_qualifier": [keep[k][2] for k in sorted(added_members)],
              "asymmetric_p197": [f"{keep[a][2]}–{keep[t][2]}" for a, t in asym],
              "code_non_consecutive_edges": [f"{nm(a)}({rcode[a]})–{nm(b)}({rcode[b]})" for a, b in noncons],
              "code_consecutive_without_adjacency": [f"{nm(a)}({rcode[a]})–{nm(b)}({rcode[b]})" for a, b in missing],
              "long_edges": [f"{nm(a)}–{nm(b)} {d}m" for a, b, d in long_e],
              "unqualified_ignored": len(unq_ignored), "contracted_non_stations": contracted}
        val_lines.append(vl)
        for kind in ("asymmetric_p197", "code_non_consecutive_edges", "code_consecutive_without_adjacency", "long_edges", "isolated_members"):
            for x in vl[kind]:
                suspects[kind].append({"line": lname, "item": x})
        for g in geo:
            if g["ratio"] and g["ratio"] > 1.05:
                suspects["geometry"].append({"line": lname, "item": f"{g['sequence']} ({g['n']}역) 비율 {g['ratio']}"})
    edges.sort(key=lambda e: (e["line"], e["a"], e["b"], e["sequence"]))
    stations.sort(key=lambda s: s["id"])
    from metro_portal.names import assign_grades
    assign_grades(stations, "JP")
    langs = Counter(f"{n['lang']}-{n['script']}-{n['source']}" for s in stations for n in s["names"])
    items = {s["wikidata"] for s in stations}
    meta = {"description": "도쿄권 (1도 3현) JR東日本·東京メトロ·都営·간토 대형 사철 8사 도시철도. 노선별 역 단위. Wikidata (CC0).",
            "source": "Wikidata Query Service (CC0)", "fetched_at": {k: v["fetched_at"] for k, v in meta_raw.items()},
            "counts": {"stations": len(stations), "physical_items": len(items), "lines": len(lines_out), "ride_edges": len(edges),
                       "excluded_items": len(excluded), "lines_skipped": len(lines_skipped),
                       "names_by_lang_script_source": dict(sorted(langs.items())),
                       "official_names": sum(1 for s in stations for n in s["names"] if n["official"]),
                       "names_by_grade": dict(sorted(Counter(n["grade"] for s in stations for n in s["names"]).items())),
                       "suspects": {k: len(v) for k, v in sorted(suspects.items())}},
            "excluded": excluded, "lines_skipped": lines_skipped, "recent_openings": sorted(recent_open, key=lambda r: (r["opened"], r["qid"])),
            "p131_missing_bbox_included": p131_missing}
    OUT.mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # noqa: E731
    dump("stations.json", {"meta": meta, "stations": stations})
    dump("lines.json", {"lines": lines_out})
    dump("ride_edges.json", {"edges": edges})
    dump("lines_validation.json", {"lines": val_lines, "suspects": {k: v for k, v in sorted(suspects.items())}})
    write_report(meta, lines_out, val_lines, suspects, sidx)
    print(json.dumps(meta["counts"], ensure_ascii=False))
    return 0


def write_report(meta, lines, val_lines, suspects, sidx):
    c = meta["counts"]
    L = ["# T1 도쿄권 데이터 (Phase 1b, Wikidata)", "",
         "생성: `python3 pipeline/22_fetch_jp_wikidata.py && python3 pipeline/23_build_jp.py` (범위 `config/jp_scope.yaml`)", "",
         "- 범위: 1도 3현(東京·神奈川·埼玉·千葉, 역 아이템 P131 사슬), 운영사 JR東日本·東京メトロ·都営·간토 대형 사철 8사 "
         "(東武·西武·京成·東急·京急·小田急·京王·相鉄)의 노선 아이템. JR은 Wikidata 인프라 노선 단위. 신칸센·화물선·폐선 제외.",
         "- 이름: 4차 Q6-1 규칙 — ja 라벨 = native_label(준공식), 공식명 P1448(ja) = official, en 라벨 = foreign_label.",
         "- 원문 수집 시각: " + ", ".join(f"{k} {v}" for k, v in meta["fetched_at"].items()),
         f"- 물리 역(아이템) {c['physical_items']}, 노선별 역 레코드 {c['stations']}, 노선 {c['lines']}, 승차 엣지 {c['ride_edges']}, "
         f"제외 아이템 {c['excluded_items']}, 제외 노선 {c['lines_skipped']}",
         "- 이름: " + ", ".join(f"{k} {v}" for k, v in c["names_by_lang_script_source"].items()) + f" · 등급 " +
         ", ".join(f"{k} {v}" for k, v in c["names_by_grade"].items()),
         "- 의심 목록 건수: " + (", ".join(f"{k} {v}" for k, v in c["suspects"].items()) or "없음"), "",
         "## 노선", "",
         "기하 = 현재 순서 길이 / 좌표 최적 순서 길이 (4역 이상 시퀀스, 1.000 = 좌표상 최적 순서와 같음). 연결 = 순환을 닫는 엣지(병행 선로·급행)를 2역 시퀀스로 보존한 수.", "",
         "| 노선 | 운영 | 역번호 | 역 | 엣지 | 시퀀스 | 연결 | 기하 (본선·지선) | 비대칭 P197 | 역번호 불연속 |",
         "| :- | :- | :- | -: | -: | -: | -: | :- | -: | -: |"]
    for v in val_lines:
        g = ", ".join(f"{x['ratio']:.3f}" for x in v["geometry"] if x["ratio"]) or "-"
        nseq = sum(1 for s, _ in v["sequences"] if not s.startswith("link"))
        L.append(f"| {v['name']} | {v['operator']} | {v['code_prefix'] or '-'} | {v['stations']} | {v['edges']} | {nseq} | {len(v['cycle_links'])} | "
                 f"{g} | {len(v['asymmetric_p197'])} | {len(v['code_non_consecutive_edges'])} |")
    titles = {"geometry": "좌표 기하 비율 1.05 초과 시퀀스 (순서 의심)",
              "code_non_consecutive_edges": "역번호가 같은 접두어인데 이어지지 않는 인접 엣지 (급행 건너뛰기·지선 분기·오류)",
              "code_consecutive_without_adjacency": "역번호는 이어지는데 인접 진술이 없는 쌍",
              "asymmetric_p197": "한쪽 역만 그 노선 한정자로 인접을 적은 쌍 (P197 비대칭)",
              "long_edges": "인접역 거리 8km 초과", "isolated_members": "노선(P81)에 걸렸지만 그 노선 인접 진술이 없는 역 (노선에서 뺌)"}
    L += ["", "## 의심 목록", "", "두 근거(P197 진술, 좌표 기하·역번호)가 어긋나는 곳. 데이터는 고치지 않았다.", ""]
    for k in ("geometry", "code_non_consecutive_edges", "code_consecutive_without_adjacency", "asymmetric_p197", "long_edges", "isolated_members"):
        xs = suspects.get(k, [])
        L += [f"### {titles[k]} — {len(xs)}건", ""]
        L += [f"- {x['line']}: {x['item']}" for x in xs[:80]] or ["없음."]
        if len(xs) > 80:
            L.append(f"- … 외 {len(xs) - 80}건 (`data/processed/jp/lines_validation.json`)")
        L.append("")
    L += ["## 제외한 노선", "", "| 노선 | QID | 범위 안 역 | 사유 |", "| :- | :- | -: | :- |"]
    L += [f"| {x['name']} | {x['qid']} | {x['stations_in_scope']} | {x['reason']} |" for x in meta["lines_skipped"]]
    L += ["", "## 최근 개통 표기 (검증 필요, Wikidata 단일 근거)", ""]
    L += [f"- {r['label']} ({r['qid']}) {r['opened']}" for r in meta["recent_openings"]] or ["없음."]
    L += ["", "## P131(소재 행정구역)이 없어 좌표 범위로 넣은 아이템", ""]
    L += [f"- {r['label']} ({r['qid']})" for r in meta["p131_missing_bbox_included"]] or ["없음."]
    L += ["", f"## 제외한 역 아이템 ({len(meta['excluded'])})", ""]
    L += [f"- {x['label']} ({x['qid']}): {x['reason']}" for x in meta["excluded"][:60]]
    if len(meta["excluded"]) > 60:
        L.append(f"- … 외 {len(meta['excluded']) - 60}건")
    (ROOT / "docs" / "reports" / "t1_tokyo_data.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
