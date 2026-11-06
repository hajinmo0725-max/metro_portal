#!/usr/bin/env python3
"""4차 Q6-7. T2 포탈 감사표: 포탈마다 어떤 글자를 정규화해서 일치했는지, 다대일 간체화에 기대는지.

OpenCC t2s는 유지한다 (2026-11-06 사용자 결정). 대신 이 단계가 근거를 출력한다.
- 원문을 등급 정규화(접미사·괄호 제거)만 한 문자열끼리 글자 단위로 비교해, 서로 다른 글자 쌍과 그 쌍을 같게 만든 경로
  (OpenCC t2s / Unihan 필드)를 적는다. 원문이 이미 같으면 '원문 동일'.
- 다대일 의존: 그 글자 쌍이 t2s 결과(간체자)가 같아서 맞았고, 그 간체자로 접히는 번체자가 둘 이상(t2s 역상 크기 ≥ 2)인 경우.
  t2s 역상은 CJK 통합 한자(기본 + 확장 A + 호환)를 한 글자씩 변환해서 만든다 (문맥 변환은 반영 안 됨 — 근사).
- 차집합 관점 보조: 원문 글자 자체가 다대일 간체자로 접히는 경우(같은 글자끼리라도)도 '다대일 글자 포함'으로 따로 센다.

입력: config/rulesets/tw_t12.yaml (T2 설정), data/processed/{kr,tw}
출력: data/processed/world/t2_audit.json, docs/reports/q6_t2_audit.md
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.graph import tier_normalize  # noqa: E402
from metro_portal.normalize import normalize_name  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.variants import folder_for, load_unihan_pairs  # noqa: E402
from metro_portal.world import build_world, load_multi  # noqa: E402

RANGES = [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF)]


@lru_cache(maxsize=1)
def t2s_inverse():
    """간체자 → 그 간체자로 접히는 '번체' 글자 집합.
    호환 한자(U+F900–FAFF)는 NFKC로 이미 통합되므로 빼고, 간체자 자신은 s2t로 되돌려도 자기 자신일 때(回·云처럼
    번체에서도 쓰는 글자)만 번체로 센다. 龙(간체 전용)은 빠지므로 龍→龙은 일대일, 雲·云→云은 다대일이 된다."""
    import opencc
    cc, back = opencc.OpenCC("t2s"), opencc.OpenCC("s2t")
    inv = {}
    for lo, hi in RANGES[:2]:
        for cp in range(lo, hi + 1):
            ch = chr(cp)
            out = cc.convert(ch)
            if len(out) != 1:
                continue
            if ch == out and back.convert(ch) != ch:
                continue  # 간체 전용 글자 (번체 역상 아님)
            inv.setdefault(out, set()).add(ch)
    return inv, cc


def unihan_relation(a, b, cfg):
    path = ROOT / cfg.get("unihan_file", "data/raw/unihan/Unihan_Variants.txt")
    rel = sorted({f for x, y, f in load_unihan_pairs(path, cfg.get("unihan_fields", [])) if {x, y} == {a, b}})
    return rel


def explain(texts, tcfg, norm):
    """원문들 → 정규화 문자열, 서로 다른 글자 위치별 근거."""
    folder = folder_for(tcfg["variant_fold"])
    tn = tier_normalize(tcfg, norm)
    inv, cc = t2s_inverse()
    normed = sorted({normalize_name(t, tn) for t in texts})
    many_chars = sorted({ch for s in normed for ch in s if len(inv.get(cc.convert(ch), ())) >= 2 and cc.convert(ch) != ch})
    if len(normed) == 1:
        return {"normalized": normed, "same_text": True, "diffs": [], "many_to_one": False, "many_to_one_chars": many_chars}
    lengths = {len(s) for s in normed}
    if len(lengths) != 1:
        return {"normalized": normed, "same_text": False, "diffs": [{"note": "길이 다름 (문맥 변환)"}], "many_to_one": True, "many_to_one_chars": many_chars}
    diffs, many = [], False
    base = normed[0]
    for other in normed[1:]:
        for i, (a, b) in enumerate(zip(base, other)):
            if a == b:
                continue
            sa, sb = cc.convert(a), cc.convert(b)
            via = []
            if sa == sb:
                pre = sorted(inv.get(sa, set()))
                via.append(f"t2s → {sa} (역상 {''.join(pre)})")
                if len(pre) >= 2:
                    many = True
            rel = unihan_relation(a, b, tcfg["variant_fold"])
            if rel:
                via.append("Unihan " + "/".join(rel))
            fa, fb = folder.fold(a), folder.fold(b)
            if not via and fa == fb:
                via.append(f"Unihan 클래스 대표 {fa} (간접)")
            diffs.append({"pos": i, "a": a, "b": b, "t2s": [sa, sb], "folded": fa, "via": via,
                          "t2s_preimage_size": len(inv.get(sa, ())) if sa == sb else None})
    return {"normalized": normed, "same_text": False, "diffs": diffs, "many_to_one": many, "many_to_one_chars": many_chars}


def main() -> int:
    rs = load_ruleset("tw_t12")
    tcfg = rs["portals"]["T2"]
    w = build_world(*load_multi(("KR", "TW")), rs)
    sm = {s["id"]: s for s in w["stations"]}
    rows = []
    for p in sorted(w["portals"] + [x for x in w["capped"] if x["tier"] == "T2"], key=lambda p: p["id"]):
        if p["tier"] != "T2":
            continue
        ex = explain(p["texts"], tcfg, rs["normalize"])
        rows.append({"key": p["name"], "subsumed": bool(p.get("subsumed")), "texts": p["texts"], "grades": p.get("grades", []),
                     "confidence": p.get("confidence", ""),
                     "stations": sorted({f"{sm[x].get('country', 'KR')}:{sm[x]['name_ko']}[{sm[x]['line_name']}]" for x in p["station_ids"]}),
                     **ex})
    out = ROOT / "data" / "processed" / "world" / "t2_audit.json"
    out.write_text(json.dumps({"ruleset": rs["name"], "rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    act = [r for r in rows if not r["subsumed"]]
    L = ["# Q6-7 T2 포탈 감사표 (이체자 정규화 근거)", "", "생성: `python3 pipeline/19_t2_audit.py` (ruleset `tw_t12`: OpenCC t2s + Unihan 7필드, 클래스 상한 8)", "",
         "- '원문 동일': 등급 정규화(접미사 '站'·괄호 부역명 제거)만으로 같아진 경우. 이체자 접기가 필요 없었다.",
         "- '글자 근거': 서로 다른 글자 쌍과 그 쌍을 같게 만든 경로. t2s 역상 = 그 간체자로 접히는 번체 글자 집합 (한 글자씩 변환한 근사. 호환 한자 제외, 간체 전용 글자 제외).",
         "- **다대일 의존**: 서로 다른 글자 쌍이 t2s로 같은 간체자가 됐고 그 간체자의 역상이 2자 이상. 과병합 후보라 따로 표시한다.",
         "- '다대일 글자 포함': 원문 글자가 같더라도 그 글자가 다대일로 접히는 글자인 경우 (다른 역과 잘못 맞을 여지).", "",
         f"## 활성 T2 포탈 {len(act)}개", "",
         "| 접힌 키 | 원문 | 정규화 후 | 글자 근거 | 다대일 의존 | 다대일 글자 포함 | 신뢰도 | 연결 역 |", "| :- | :- | :- | :- | :- | :- | :- | :- |"]
    for r in act:
        ev = "원문 동일" if r["same_text"] else "; ".join(
            (f"{d['a']}↔{d['b']}: " + ", ".join(d["via"])) if "a" in d else d.get("note", "") for d in r["diffs"])
        L.append(f"| {r['key']} | {' / '.join(r['texts'])} | {' / '.join(r['normalized'])} | {ev} | {'**예**' if r['many_to_one'] else '아니오'} | "
                 f"{''.join(r['many_to_one_chars']) or '-'} | {r['confidence']} | {'; '.join(r['stations'])} |")
    sub = [r for r in rows if r["subsumed"]]
    L += ["", f"## T1과 겹쳐 생략된 T2 후보 {len(sub)}개 (dedupe, 경로 영향 없음)", "",
          "| 접힌 키 | 원문 | 글자 근거 | 다대일 의존 |", "| :- | :- | :- | :- |"]
    for r in sub:
        ev = "원문 동일" if r["same_text"] else "; ".join((f"{d['a']}↔{d['b']}: " + ", ".join(d["via"])) if "a" in d else d.get("note", "") for d in r["diffs"])
        L.append(f"| {r['key']} | {' / '.join(r['texts'])} | {ev} | {'**예**' if r['many_to_one'] else '아니오'} |")
    n_many = sum(r["many_to_one"] for r in act)
    L += ["", f"요약: 활성 T2 {len(act)}개 중 원문 동일 {sum(r['same_text'] for r in act)}, 이체자 접기 필요 {sum(not r['same_text'] for r in act)}, "
          f"다대일 의존 {n_many}."]
    (ROOT / "docs" / "reports" / "q6_t2_audit.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
