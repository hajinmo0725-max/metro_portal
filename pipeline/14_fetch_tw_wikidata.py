#!/usr/bin/env python3
"""B1-1. 타이베이 대도시권 도시철도 역·노선·인접 관계를 Wikidata에서 받는다 (CC0).
역은 P16(교통망) ∈ 범위 시스템 또는 P81(노선) ∈ 범위 노선으로 찾는다 (단해 경전철 역은 P16이 없다).

Geofabrik 대만 추출본(OSM)과 대만 공식 오픈데이터 호스트가 세션 네트워크에서 막혀 Wikidata로 대체했다.
쿼리 4회 (역 기본, 역번호, 인접 P197+한정자, 노선 라벨). 요청 사이 대기, User-Agent에 프로젝트명, 원문 캐시.

입력: config/tw_scope.yaml, config/sources.yaml
출력: data/raw/wikidata_tw/*.json (원문 캐시, gitignore)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402

RAW = ROOT / "data" / "raw" / "wikidata_tw"

Q_STATIONS = """SELECT ?st ?sys ?cls ?coord ?state ?open ?zh_hant ?zh_tw ?zh ?en ?off WHERE {{
  {{ VALUES ?sys {{ {systems} }} ?st wdt:P16 ?sys }} UNION {{ VALUES ?ln {{ {lines} }} ?st wdt:P81 ?ln }}
  OPTIONAL {{ ?st wdt:P31 ?cls }}
  OPTIONAL {{ ?st wdt:P625 ?coord }}
  OPTIONAL {{ ?st wdt:P5817 ?state }}
  OPTIONAL {{ ?st wdt:P1619 ?open }}
  OPTIONAL {{ ?st rdfs:label ?zh_hant FILTER(LANG(?zh_hant) = "zh-hant") }}
  OPTIONAL {{ ?st rdfs:label ?zh_tw FILTER(LANG(?zh_tw) = "zh-tw") }}
  OPTIONAL {{ ?st rdfs:label ?zh FILTER(LANG(?zh) = "zh") }}
  OPTIONAL {{ ?st rdfs:label ?en FILTER(LANG(?en) = "en") }}
  OPTIONAL {{ ?st wdt:P1448 ?off }}
}}"""

Q_CODES = """SELECT ?st ?code ?line WHERE {{
  {{ VALUES ?sys {{ {systems} }} ?st wdt:P16 ?sys }} UNION {{ VALUES ?ln {{ {lines} }} ?st wdt:P81 ?ln }}
  OPTIONAL {{ ?st wdt:P296 ?code }}
  OPTIONAL {{ ?st wdt:P81 ?line }}
}}"""

Q_ADJ = """SELECT ?st ?adj ?line ?towards WHERE {{
  {{ VALUES ?sys {{ {systems} }} ?st wdt:P16 ?sys }} UNION {{ VALUES ?ln {{ {lines} }} ?st wdt:P81 ?ln }}
  ?st p:P197 ?s .
  ?s ps:P197 ?adj .
  OPTIONAL {{ ?s pq:P81 ?line }}
  OPTIONAL {{ ?s pq:P5051 ?towards }}
}}"""

Q_LINES = """SELECT ?line ?zh_hant ?zh ?en ?op ?open ?state WHERE {{
  VALUES ?line {{ {lines} }}
  OPTIONAL {{ ?line rdfs:label ?zh_hant FILTER(LANG(?zh_hant) = "zh-hant") }}
  OPTIONAL {{ ?line rdfs:label ?zh FILTER(LANG(?zh) = "zh") }}
  OPTIONAL {{ ?line rdfs:label ?en FILTER(LANG(?en) = "en") }}
  OPTIONAL {{ ?line wdt:P137 ?op }}
  OPTIONAL {{ ?line wdt:P1619 ?open }}
  OPTIONAL {{ ?line wdt:P5817 ?state }}
}}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    src = yaml.safe_load(open(ROOT / "config" / "sources.yaml", encoding="utf-8"))
    scope = yaml.safe_load(open(ROOT / "config" / "tw_scope.yaml", encoding="utf-8"))
    cfg, ua = src["wikidata"], src["user_agent"]
    systems = " ".join(f"wd:{s['qid']}" for s in scope["systems"])
    lines = " ".join(sorted({f"wd:{q}" for l in scope["lines"] for q in l["qids"]}))
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = [("stations", Q_STATIONS.format(systems=systems, lines=lines)), ("codes", Q_CODES.format(systems=systems, lines=lines)),
            ("adjacency", Q_ADJ.format(systems=systems, lines=lines)), ("lines", Q_LINES.format(lines=lines))]
    meta_path = RAW / "fetch_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() and not a.force else {}
    for i, (name, q) in enumerate(jobs):
        path = RAW / f"{name}.json"
        if path.exists() and not a.force:
            print(f"[14] {name}: cache")
            continue
        if i:
            time.sleep(cfg["request_interval_s"])
        r = requests.get(cfg["endpoint"], params={"query": q},
                         headers={"User-Agent": ua, "Accept": "application/sparql-results+json"}, timeout=120)
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
        meta[name] = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "query": q,
                      "rows": len(r.json()["results"]["bindings"])}
        print(f"[14] {name}: download {meta[name]['rows']} rows")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
