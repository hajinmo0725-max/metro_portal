#!/usr/bin/env python3
"""도쿄권 데이터 소스 조사용 Wikidata 실측 (3차 추가 작업). 그래프에는 쓰지 않는다 — 규모·다국어 커버리지·매칭 충돌 추정만.

bbox(도쿄권 1도3현 근사, 일부 주변 현 포함) 안의 역 아이템을 받아 커버리지와, 한국 표준데이터 한자·영문명 /
타이베이 라벨과의 T2·T3 키 충돌 수를 tw_t123 ruleset 규칙으로 계산한다. 일본 쪽 이름은 Wikidata 라벨(커뮤니티)이라 추정치다.

출력: data/raw/wikidata_jp/stations.json (원문 캐시), data/processed/jp_survey.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.graph import tier_normalize  # noqa: E402
from metro_portal.normalize import normalize_name, script_ok  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.variants import folder_for  # noqa: E402

RAW = ROOT / "data" / "raw" / "wikidata_jp"
BBOX = ("Point(138.95 35.05)", "Point(140.95 36.30)")
CLASSES = ["Q55488", "Q928830", "Q2175765", "Q22808404", "Q4663385", "Q1793804"]  # 철도역, 지하철역, 노면전차 정류장 등
NOT_IN_USE = {"Q811683", "Q63065035", "Q30108381", "Q12377751", "Q11639308", "Q50376823"}
Q = """SELECT ?st ?cls ?op ?line ?state ?off ?ja ?en ?ko ?zht ?zhs ?code ?adj WHERE {{
  SERVICE wikibase:box {{ ?st wdt:P625 ?coord .
    bd:serviceParam wikibase:cornerSouthWest "{sw}"^^geo:wktLiteral . bd:serviceParam wikibase:cornerNorthEast "{ne}"^^geo:wktLiteral . }}
  VALUES ?cls {{ {classes} }} ?st wdt:P31 ?cls .
  OPTIONAL {{ ?st wdt:P137 ?op }} OPTIONAL {{ ?st wdt:P81 ?line }} OPTIONAL {{ ?st wdt:P5817 ?state }}
  OPTIONAL {{ ?st wdt:P1448 ?off }}
  OPTIONAL {{ ?st rdfs:label ?ja FILTER(LANG(?ja)="ja") }} OPTIONAL {{ ?st rdfs:label ?en FILTER(LANG(?en)="en") }}
  OPTIONAL {{ ?st rdfs:label ?ko FILTER(LANG(?ko)="ko") }} OPTIONAL {{ ?st rdfs:label ?zht FILTER(LANG(?zht)="zh-hant") }}
  OPTIONAL {{ ?st rdfs:label ?zhs FILTER(LANG(?zhs)="zh-hans") }}
  OPTIONAL {{ ?st wdt:P296 ?code }} OPTIONAL {{ ?st wdt:P197 ?adj }}
}}"""


def main() -> int:
    src = yaml.safe_load(open(ROOT / "config" / "sources.yaml", encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    raw = RAW / "stations.json"
    if not raw.exists():
        q = Q.format(sw=BBOX[0], ne=BBOX[1], classes=" ".join(f"wd:{c}" for c in CLASSES))
        r = requests.get(src["wikidata"]["endpoint"], params={"query": q},
                         headers={"User-Agent": src["user_agent"], "Accept": "application/sparql-results+json"}, timeout=300)
        r.raise_for_status()
        raw.write_text(r.text, encoding="utf-8")
        (RAW / "fetch_meta.json").write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}), encoding="utf-8")
    q_ = lambda u: u.rsplit("/", 1)[1]  # noqa: E731
    st = defaultdict(lambda: defaultdict(set))
    for b in json.loads(raw.read_text(encoding="utf-8"))["results"]["bindings"]:
        k = q_(b["st"]["value"])
        for kk, v in b.items():
            if kk != "st":
                st[k][kk].add(q_(v["value"]) if v["type"] == "uri" else v["value"])
    inuse = sorted(k for k, v in st.items() if not (v.get("state", set()) & NOT_IN_USE))
    cov = {k: sum(1 for x in inuse if st[x].get(k)) for k in ("ja", "en", "ko", "zht", "zhs", "code", "adj", "line", "op", "off")}
    lines = Counter(l for x in inuse for l in st[x].get("line", ()))
    rs = load_ruleset("tw_t123")
    t2, t3 = rs["portals"]["T2"], rs["portals"]["T3"]
    n2, n3 = tier_normalize(t2, rs["normalize"]), tier_normalize(t3, rs["normalize"])
    fold = folder_for(t2["variant_fold"])

    def k2(t):
        k = normalize_name(t, n2)
        return fold.fold(k) if script_ok(k, "Hani") else None

    def k3(t):
        k = normalize_name(t, n3)
        return k if script_ok(k, "Latn") else None
    jp2, jp3 = defaultdict(set), defaultdict(set)
    for x in inuse:
        for t in st[x].get("ja", ()):
            if k2(t):
                jp2[k2(t)].add(t)
        for t in st[x].get("en", ()):
            if k3(t):
                jp3[k3(t)].add(t)
    kr2, kr3, tw2, tw3 = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    for s in json.loads((ROOT / "data" / "processed" / "kr" / "stations.json").read_text(encoding="utf-8"))["stations"]:
        for n in s["names"]:
            if n["source"] == "kric_std" and n["script"] == "Hani" and k2(n["text"]):
                kr2[k2(n["text"])].add(s["name_ko"])
            if n["source"] == "kric_std" and n["lang"] == "en" and k3(n["text"]):
                kr3[k3(n["text"])].add(s["name_ko"])
    for s in json.loads((ROOT / "data" / "processed" / "tw" / "stations.json").read_text(encoding="utf-8"))["stations"]:
        if k2(s["name_zh"]):
            tw2[k2(s["name_zh"])].add(s["name_zh"])
        if k3(s["name_en"]):
            tw3[k3(s["name_en"])].add(s["name_en"])
    pairs = lambda a, b: sorted((sorted(a[k])[0], sorted(b[k])) for k in set(a) & set(b))  # noqa: E731
    out = {"bbox": BBOX, "fetched_at": json.loads((RAW / "fetch_meta.json").read_text())["fetched_at"] if (RAW / "fetch_meta.json").exists() else "",
           "items": len(st), "in_use": len(inuse), "coverage": cov, "lines": len(lines),
           "records_by_line": sum(len(st[x].get("line", ())) for x in inuse),
           "operators_top": Counter(o for x in inuse for o in st[x].get("op", ())).most_common(15),
           "t2_keys": {"jp": len(jp2), "kr": len(kr2), "tw": len(tw2)},
           "t2_jp_kr": pairs(jp2, kr2), "t2_jp_tw": pairs(jp2, tw2), "t2_kr_tw": pairs(kr2, tw2),
           "t2_all3": sorted(set(jp2) & set(kr2) & set(tw2)),
           "t3_jp_kr": pairs(jp3, kr3), "t3_jp_tw": pairs(jp3, tw3), "t3_kr_tw": pairs(kr3, tw3),
           "jp_internal_t2_shared": sum(1 for k in jp2 if sum(1 for x in inuse if any(k2(t) == k for t in st[x].get("ja", ()))) >= 2)}
    (ROOT / "data" / "processed" / "jp_survey.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k in ("in_use", "coverage", "lines", "records_by_line", "t2_keys", "t2_jp_kr", "t2_jp_tw", "t2_all3", "t3_jp_kr", "t3_jp_tw")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
