#!/usr/bin/env python3
"""5차 T1-1. 도쿄권(Phase 1b) 도시철도 역·노선·인접 관계를 Wikidata에서 받는다 (CC0).

범위: config/jp_scope.yaml — 운영사(JR東日本·東京メトロ·都営·간토 대형 사철 8사) 노선 아이템(P81)에 걸린 역 중 1도 3현(P131 사슬).
쿼리 6회 (노선, 역 기본, 역번호+한정자, 인접 P197+한정자, 현 소속, P131 유무). 요청 사이 대기, User-Agent에 프로젝트명, 원문 캐시(재실행 시 재사용).
ODPT 등 공식 소스는 4차 결정(Q6-9)대로 쓰지 않는다. 운영사·국토수치정보·Geofabrik은 3차 조사에서 세션 네트워크에서 막혀 있었다.

입력: config/jp_scope.yaml, config/sources.yaml
출력: data/raw/wikidata_jp/{lines,stations,codes,adjacency,prefs,has_p131}.json, fetch_meta.json (gitignore)
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

RAW = ROOT / "data" / "raw" / "wikidata_jp"

# 범위 노선 = 운영사가 범위 운영사인 노선 아이템 (제외 목록은 정제 단계에서)
LINES_OF = "VALUES ?op {{ {ops} }} ?line wdt:P137 ?op ."

Q_LINES = """SELECT ?line ?op ?ja ?en ?ko ?color ?closed ?dissolved ?state WHERE {{
  """ + LINES_OF + """
  OPTIONAL {{ ?line rdfs:label ?ja FILTER(LANG(?ja) = "ja") }}
  OPTIONAL {{ ?line rdfs:label ?en FILTER(LANG(?en) = "en") }}
  OPTIONAL {{ ?line rdfs:label ?ko FILTER(LANG(?ko) = "ko") }}
  OPTIONAL {{ ?line wdt:P465 ?color }}
  OPTIONAL {{ ?line wdt:P3999 ?closed }}
  OPTIONAL {{ ?line wdt:P576 ?dissolved }}
  OPTIONAL {{ ?line wdt:P5817 ?state }}
}}"""

Q_STATIONS = """SELECT ?st ?line ?coord ?state ?open ?closed ?ja ?en ?off WHERE {{
  """ + LINES_OF + """
  ?st wdt:P81 ?line .
  OPTIONAL {{ ?st wdt:P625 ?coord }}
  OPTIONAL {{ ?st wdt:P5817 ?state }}
  OPTIONAL {{ ?st wdt:P1619 ?open }}
  OPTIONAL {{ ?st wdt:P3999 ?closed }}
  OPTIONAL {{ ?st rdfs:label ?ja FILTER(LANG(?ja) = "ja") }}
  OPTIONAL {{ ?st rdfs:label ?en FILTER(LANG(?en) = "en") }}
  OPTIONAL {{ ?st wdt:P1448 ?off }}
}}"""

Q_CODES = """SELECT ?st ?code ?cline ?cop WHERE {{
  """ + LINES_OF + """
  ?st wdt:P81 ?line .
  ?st p:P296 ?cs . ?cs ps:P296 ?code .
  OPTIONAL {{ ?cs pq:P81 ?cline }}
  OPTIONAL {{ ?cs pq:P137 ?cop }}
}}"""

Q_ADJ = """SELECT ?st ?adj ?aline ?towards WHERE {{
  """ + LINES_OF + """
  ?st wdt:P81 ?line .
  ?st p:P197 ?as . ?as ps:P197 ?adj .
  OPTIONAL {{ ?as pq:P81 ?aline }}
  OPTIONAL {{ ?as pq:P5051 ?towards }}
}}"""

Q_PREFS = """SELECT DISTINCT ?st ?pref WHERE {{
  """ + LINES_OF + """
  VALUES ?pref {{ {prefs} }}
  ?st wdt:P81 ?line .
  ?st wdt:P131+ ?pref .
}}"""


# P131(소재 행정구역)이 아예 없는 아이템만 좌표 범위로 받기 위해, P131이 있는 역 목록 (현 소속 쿼리는 1도 3현에 닿는 역만 돌려준다)
Q_HAS131 = """SELECT DISTINCT ?st WHERE {{
  """ + LINES_OF + """
  ?st wdt:P81 ?line .
  ?st wdt:P131 ?a .
}}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    src = yaml.safe_load(open(ROOT / "config" / "sources.yaml", encoding="utf-8"))
    scope = yaml.safe_load(open(ROOT / "config" / "jp_scope.yaml", encoding="utf-8"))
    cfg, ua = src["wikidata"], src["user_agent"]
    ops = " ".join(f"wd:{q}" for q in sorted(scope["operators"]))
    prefs = " ".join(f"wd:{q}" for q in sorted(scope["prefectures"]))
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = [("lines", Q_LINES.format(ops=ops)), ("stations", Q_STATIONS.format(ops=ops)), ("codes", Q_CODES.format(ops=ops)),
            ("adjacency", Q_ADJ.format(ops=ops)), ("prefs", Q_PREFS.format(ops=ops, prefs=prefs)), ("has_p131", Q_HAS131.format(ops=ops))]
    meta_path = RAW / "fetch_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() and not a.force else {}
    first = True
    for name, q in jobs:
        path = RAW / f"{name}.json"
        if path.exists() and not a.force:
            print(f"[22] {name}: cache")
            continue
        if not first:
            time.sleep(cfg["request_interval_s"])
        first = False
        r = requests.get(cfg["endpoint"], params={"query": q},
                         headers={"User-Agent": ua, "Accept": "application/sparql-results+json"}, timeout=300)
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
        meta[name] = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "query": q,
                      "rows": len(r.json()["results"]["bindings"])}
        print(f"[22] {name}: download {meta[name]['rows']} rows")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
