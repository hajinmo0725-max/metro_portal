#!/usr/bin/env python3
"""3차 A3·A4. 환승 판정 감사.

A3: 환승 판정 규칙 비교 — 2차 규칙(거리 D=500만) vs 3차 규칙(표준데이터 공식 환승 정보 우선, 정보 없을 때만 D).
    같은 이름 쌍별 판정 차이, 클러스터·포탈 차이, 그래프 지표 차이, 공식 정보 상태 목록.
A4: 좌표 복사 전수 점검 — 정규화 이름이 같고 좌표 차이가 기준(config/validation.yaml coord_copy) 미만인데
    공식 환승역(yes)이 아닌 쌍을 모두 나열하고 유형을 분류한다.

입력: data/processed/kr/{stations,ride_edges,lines}.json, config/rulesets/<ruleset>.yaml, config/kr_transfer_codes.yaml
출력: data/processed/kr/transfer_audit.json, docs/reports/a3_transfer_rules.md, docs/reports/a4_coord_copy.md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.graph import build_clusters  # noqa: E402
from metro_portal.metrics import compute_metrics  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.transfer import OfficialTransfers, coord_copy_pairs  # noqa: E402
from metro_portal.world import build_world, load_base  # noqa: E402

PROC = ROOT / "data" / "processed" / "kr"


def portal_sig(p, cmap):
    parts = []
    for cid in p["cluster_ids"]:
        c = cmap[cid]
        parts.append(f"{'/'.join(c['cities'])}:{'+'.join(sorted(set(l.split(':', 1)[1] for l in c['lines'])))}")
    return f"{p['name']} [{' ↔ '.join(sorted(parts))}]"


def build(rs):
    st, ed, ln = load_base()
    audit = []
    official = OfficialTransfers(st)
    w = build_world(st, ed, ln, rs)
    build_clusters(st, rs, official=official, audit=audit)
    m = compute_metrics(st, ed, ln, w["clusters"], w["portals"], w["adj"], rs)
    return w, m, audit, official


def lbl(s):
    return f"{s['name_ko']}[{s['line_name']}]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruleset", default="strict")
    a = ap.parse_args()
    rs_new = load_ruleset(a.ruleset)
    if rs_new["cluster"].get("transfer_rule") != "official_first":
        raise SystemExit("[12] 기준 ruleset이 official_first가 아님")
    rs_old = load_ruleset(a.ruleset, overrides={"cluster": {"transfer_rule": "distance"}}, name=f"{a.ruleset}_distance_only")
    D = rs_new["cluster"]["transfer_distance_m"]
    w_new, m_new, aud_new, off = build(rs_new)
    w_old, m_old, aud_old, _ = build(rs_old)
    S = {s["id"]: s for s in w_new["stations"]}
    old_by = {(x["a"], x["b"], x.get("via_alias", False)): x for x in aud_old}

    pair_rows = []
    for x in aud_new:
        o = old_by[(x["a"], x["b"], x.get("via_alias", False))]
        ia, ib = off.info[x["a"]], off.info[x["b"]]
        pair_rows.append({**x, "merged_d500": o["merged"], "relation": off.relation(S[x["a"]], S[x["b"]]),
                          "status_a": ia["status"], "status_b": ib["status"], "changed": o["merged"] != x["merged"]})
    changed = [r for r in pair_rows if r["changed"]]

    # 클러스터·포탈 차이
    def name_counts(w):
        return Counter(c["name"] for c in w["clusters"])
    nc_old, nc_new = name_counts(w_old), name_counts(w_new)
    names_changed = sorted(n for n in set(nc_old) | set(nc_new) if nc_old[n] != nc_new[n])
    cm_old = {c["id"]: c for c in w_old["clusters"]}
    cm_new = {c["id"]: c for c in w_new["clusters"]}
    ps_old = {portal_sig(p, cm_old) for p in w_old["portals"]}
    ps_new = {portal_sig(p, cm_new) for p in w_new["portals"]}

    # 공식 정보 상태
    status = Counter(v["status"] for v in off.info.values())
    unknown = sorted(({"id": sid, "station": lbl(S[sid]), "reason": v["reason"], "codes": v["unknown_codes"],
                       "raw": S[sid].get("transfer_line_nos_raw", "")} for sid, v in off.info.items() if v["status"] == "unknown"),
                     key=lambda r: r["id"])
    # 공식 환승노선인데 같은 클러스터에 그 노선 역이 없음 (이름이 달라서 못 묶었거나 노선 데이터가 없음)
    cof = {sid: c for c in w_new["clusters"] for sid in c["station_ids"]}
    fam_names = {}
    for f in yaml.safe_load(open(ROOT / "config" / "kr_transfer_codes.yaml", encoding="utf-8"))["line_families"]:
        for ln_ in f["line_nos"]:
            fam_names.setdefault(ln_, f["name"])
    line_label = {}
    for s in w_new["stations"]:
        line_label.setdefault(s["line_no"], s["line_name"])
    missing = []
    for sid, v in sorted(off.info.items()):
        if v["status"] != "listed":
            continue
        have = set()
        for x in cof[sid]["station_ids"]:
            have |= off.family_of(S[x]["line_no"])
        # 패밀리로 확장된 목록이라, 패밀리 단위로 하나라도 있으면 충족
        need_fams = defaultdict(set)
        for ln_ in v["lines"]:
            need_fams[fam_names.get(ln_, ln_)].add(ln_)
        lack = [fam for fam, lns in sorted(need_fams.items()) if not (lns & have)]
        if lack:
            missing.append({"id": sid, "station": lbl(S[sid]), "cluster": cof[sid]["id"],
                            "missing_lines": [f"{fam}({'/'.join(sorted(line_label.get(x, x) for x in need_fams[fam]))})" for fam in lack],
                            "raw": S[sid].get("transfer_line_nos_raw", "")})

    # A4: 좌표 복사 점검
    vc = yaml.safe_load(open(ROOT / "config" / "validation.yaml", encoding="utf-8"))["coord_copy"]
    lim = vc["same_name_max_m"]
    copies = []
    for c in coord_copy_pairs(w_new["stations"], off, rs_new["normalize"], lim):
        x, y, rel = S[c["a"]], S[c["b"]], c["relation"]
        if rel == "same_line":
            kind = "같은 노선 패밀리 레코드 (직결 경계·그룹 분할) — 같은 역, 정상"
        else:
            kind = "공식 비환승인데 좌표 거의 같음 — 좌표 복사 의심" if rel == "no" else "공식 정보 불완전 — 판정 보류"
        copies.append({**c, "a_label": lbl(x), "b_label": lbl(y), "same_cluster": cof[x["id"]]["id"] == cof[y["id"]]["id"],
                       "kind": kind, "coord_fix_a": bool(x.get("coord_fix")), "coord_fix_b": bool(y.get("coord_fix"))})
    # 검출력 확인: 2차까지 고친 좌표(config/kr_station_fixes.yaml)를 원래 값으로 되돌리면 잡히는지
    regress = []
    for s in w_new["stations"]:
        if not s.get("coord_fix"):
            continue
        orig = [dict(x) for x in w_new["stations"]]
        for x in orig:
            if x["id"] == s["id"]:
                x["lat"], x["lon"] = s["coord_fix"]["from"]
        hits = [c for c in coord_copy_pairs(orig, off, rs_new["normalize"], lim) if s["id"] in (c["a"], c["b"])]
        regress.append({"id": s["id"], "station": lbl(s), "detected": bool(hits),
                        "hits": [f"{S[c['a']]['name_ko']}[{S[c['a']]['line_name']}]–{S[c['b']]['name_ko']}[{S[c['b']]['line_name']}] {c['distance_m']}m {c['relation']}" for c in hits]})

    def mrow(m):
        return {"clusters": m["counts"]["clusters"], "multi": m["counts"]["transfer_clusters_multi"],
                "portals": m["counts"]["portals_total"], "portal_links": m["counts"]["portal_links"],
                "dia_w": m["with_warp"]["diameter"]["value"], "mean_w": m["with_warp"]["diameter"]["mean_cost"],
                "comp_n": m["without_warp"]["components"], "dia_n": m["without_warp"]["diameter"]["value"]}
    out = {"ruleset": rs_new["name"], "D": D,
           "basis_counts": dict(Counter(r["basis"] for r in pair_rows)),
           "status_counts": dict(status), "pairs": pair_rows, "changed_pairs": changed,
           "names_cluster_count_changed": {n: [nc_old[n], nc_new[n]] for n in names_changed},
           "portals_added": sorted(ps_new - ps_old), "portals_removed": sorted(ps_old - ps_new),
           "metrics": {"distance_only_D500": mrow(m_old), "official_first": mrow(m_new)},
           "unknown_status": unknown, "official_missing_partner": missing,
           "coord_copy": {"threshold_m": lim, "pairs": copies, "regression": regress}}
    (PROC / "transfer_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_a3(out, S)
    write_a4(out)
    print(json.dumps({k: out[k] for k in ("basis_counts", "status_counts", "names_cluster_count_changed", "portals_added", "portals_removed", "metrics")},
                     ensure_ascii=False))
    print(f"[12] changed pairs={len(changed)} unknown={len(unknown)} missing_partner={len(missing)} coord_copy={len(copies)}")
    return 0


BASIS_KO = {"official_yes": "공식 yes", "official_no": "공식 no", "distance(same_line)": "같은 노선 패밀리 → 거리",
            "distance(unknown)": "정보 불완전 → 거리", "distance": "거리"}


def write_a3(o, S):
    L = ["# A3 환승 판정 규칙 비교 — 공식 환승 정보 우선 vs 거리 D=500", "",
         "생성: `python3 pipeline/12_audit_transfers.py`. 규칙 구현: `metro_portal/transfer.py`, `metro_portal/graph.py` `transfer_decision`.", "",
         "## 규칙", "",
         "- **2차 (distance)**: 정규화 이름이 같고 거리 D=500m 이하면 같은 클러스터(환승).",
         "- **3차 (official_first, 기본 ruleset `strict`)**: 표준데이터 '환승역구분'·'환승노선번호'를 먼저 본다.",
         "  - 공식 yes (한쪽의 환승노선 목록에 다른 쪽 노선이 있음) → 묶음 (상한 1500m)",
         "  - 공식 no (둘 다 정보가 완전한데 서로를 안 적음. '일반역'도 완전한 정보) → 거리와 무관하게 안 묶음",
         "  - 같은 노선 패밀리 (직결 경계: 3호선↔일산선 지축, 같은 노선번호 I4108의 경의중앙선/경춘선 그룹 등) → 공식 정보가 말할 수 없으므로 거리 D",
         "  - 정보 불완전 (해석 못 하는 코드, '환승역'인데 노선 목록 없음) → 거리 D",
         "- 환승노선번호 해석: 대부분 우리 노선번호와 같다. 다른 체계 코드 16종(I41K4=경의중앙 등)과 노선 패밀리는 `config/kr_transfer_codes.yaml`에 근거와 함께 적었다.",
         "- 별칭(괄호 부역명) 쌍도 같은 판정을 쓴다.", "",
         "## 판정 근거별 쌍 수 (같은 이름·별칭 쌍)", "", "| 근거 | 쌍 |", "| :- | -: |"]
    L += [f"| {BASIS_KO.get(k, k)} | {v} |" for k, v in sorted(o["basis_counts"].items())]
    L += ["", "역 레코드별 공식 정보 상태: " + ", ".join(f"{k} {v}" for k, v in sorted(o["status_counts"].items())) +
          " (listed = 환승노선 목록 있음, none = 일반역, unknown = 불완전)", "",
          "## 판정이 바뀐 쌍 (D=500 대비)", ""]
    if o["changed_pairs"]:
        L += ["| 이름 | A | B | 거리(m) | D=500 | 3차 | 근거 | 공식 상태 A / B |", "| :- | :- | :- | -: | :- | :- | :- | :- |"]
        for r in o["changed_pairs"]:
            L.append(f"| {r['name']} | {lbl(S[r['a']])} | {lbl(S[r['b']])} | {r['distance_m']:.0f} | {'환승' if r['merged_d500'] else '분리'} | "
                     f"{'환승' if r['merged'] else '분리'} | {BASIS_KO.get(r['basis'], r['basis'])} | {r['status_a']} / {r['status_b']} |")
    else:
        L.append("없음.")
    L += ["", "## 클러스터 수가 바뀐 이름", ""]
    if o["names_cluster_count_changed"]:
        L += ["| 이름 | D=500 클러스터 | 3차 클러스터 |", "| :- | -: | -: |"]
        L += [f"| {n} | {a} | {b} |" for n, (a, b) in o["names_cluster_count_changed"].items()]
    else:
        L.append("없음.")
    L += ["", "## 포탈 차이", "", "| 구분 | 포탈 [도시:노선 ↔ ...] |", "| :- | :- |"]
    L += [f"| 추가 | {p} |" for p in o["portals_added"]] + [f"| 삭제 | {p} |" for p in o["portals_removed"]]
    if not o["portals_added"] and not o["portals_removed"]:
        L.append("| - | 없음 |")
    a, b = o["metrics"]["distance_only_D500"], o["metrics"]["official_first"]
    L += ["", "## 그래프 지표", "", "| 항목 | D=500 | 3차 (공식 우선) |", "| :- | -: | -: |"]
    for k, t in (("clusters", "클러스터"), ("multi", "다중 레코드 클러스터"), ("portals", "T1 포탈"), ("portal_links", "포탈 연결"),
                 ("dia_w", "워프 有 지름"), ("mean_w", "워프 有 평균 비용"), ("comp_n", "워프 無 컴포넌트"), ("dia_n", "워프 無 지름")):
        L.append(f"| {t} | {a[k]} | {b[k]} |")
    L += ["", "## 거리 판정으로 넘어간 쌍 (같은 노선 패밀리·정보 불완전)", "",
          "| 이름 | A | B | 거리(m) | 묶음 | 근거 |", "| :- | :- | :- | -: | :- | :- |"]
    for r in o["pairs"]:
        if r["basis"].startswith("distance("):
            L.append(f"| {r['name']} | {lbl(S[r['a']])} | {lbl(S[r['b']])} | {r['distance_m']:.0f} | {'예' if r['merged'] else '아니오'} | {BASIS_KO[r['basis']]} |")
    L += ["", "## 공식 no인데 D=500 이내였던 쌍 / 공식 yes인데 D=500 밖이었던 쌍", ""]
    rows = [r for r in o["pairs"] if (r["basis"] == "official_no" and r["distance_m"] <= o["D"]) or (r["basis"] == "official_yes" and r["distance_m"] > o["D"])]
    if rows:
        L += ["| 이름 | A | B | 거리(m) | 근거 |", "| :- | :- | :- | -: | :- |"]
        L += [f"| {r['name']} | {lbl(S[r['a']])} | {lbl(S[r['b']])} | {r['distance_m']:.0f} | {BASIS_KO[r['basis']]} |" for r in rows]
    else:
        L.append("없음.")
    L += ["", "## 공식 정보 불완전 역 레코드", "", "| 역 | 사유 | 해석 못 한 코드 | 환승노선번호 원문 |", "| :- | :- | :- | :- |"]
    L += [f"| {u['station']} | {u['reason']} | {', '.join(u['codes']) or '-'} | {u['raw'] or '-'} |" for u in o["unknown_status"]] or ["| - | - | - | - |"]
    L += ["", "## 공식 환승노선인데 같은 클러스터에 그 노선 역이 없는 경우", "",
          "이름이 달라 못 묶었거나(별칭 누락), 그 노선이 데이터에 없거나(미수록 노선), 공식 정보 오류다. 판정은 하지 않고 목록만 둔다.", "",
          "| 역 | 클러스터 | 빠진 공식 환승노선 | 환승노선번호 원문 |", "| :- | :- | :- | :- |"]
    L += [f"| {x['station']} | {x['cluster']} | {', '.join(x['missing_lines'])} | {x['raw']} |" for x in o["official_missing_partner"]] or ["| - | - | - | - |"]
    (ROOT / "docs" / "reports" / "a3_transfer_rules.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_a4(o):
    cc = o["coord_copy"]
    L = ["# A4 좌표 복사 전수 점검", "", "생성: `python3 pipeline/12_audit_transfers.py` (기준: `config/validation.yaml` coord_copy)", "",
         f"정규화 이름이 같고 좌표 차이 {cc['threshold_m']}m 미만인데 공식 환승역(yes)이 아닌 역 레코드 쌍 전부. "
         "2차에서 고친 동해선 동래(4호선 동래와 7m)가 이 패턴이었다.", "",
         f"결과: {len(cc['pairs'])}쌍", ""]
    kinds = Counter(p["kind"] for p in cc["pairs"])
    L += ["| 유형 | 쌍 |", "| :- | -: |"] + [f"| {k} | {v} |" for k, v in sorted(kinds.items())] + [""]
    L += ["| 이름 | A | B | 거리(m) | 공식 관계 | 같은 클러스터 | 유형 |", "| :- | :- | :- | -: | :- | :- | :- |"]
    L += [f"| {p['name']} | {p['a_label']} | {p['b_label']} | {p['distance_m']} | {p['relation']} | {'예' if p['same_cluster'] else '아니오'} | {p['kind']} |"
          for p in cc["pairs"]] or ["| - | - | - | - | - | - | - |"]
    L += ["", "## 검출력 확인 — 이미 고친 좌표를 원래 값으로 되돌렸을 때", "",
          "이름이 같은 짝이 없는 복사(마곡 = 발산 좌표, 이촌 = 신용산 좌표)는 이 검사 범위 밖이고 2차 근접 중복 검사(다른 클러스터 30m 이내)가 잡는다.", "",
          "| 보정된 역 | 이 검사로 검출 | 걸린 쌍 |", "| :- | :- | :- |"]
    L += [f"| {r['station']} | {'예' if r['detected'] else '아니오'} | {'; '.join(r['hits']) or '-'} |" for r in cc["regression"]]
    (ROOT / "docs" / "reports" / "a4_coord_copy.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
