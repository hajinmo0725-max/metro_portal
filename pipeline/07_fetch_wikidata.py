#!/usr/bin/env python3
"""N2c·N3. Wikidata 한국 역 인접관계(P197)·좌표(P625) 수집 — 노선 순서·좌표 교차검증용.

입력: config/sources.yaml (wikidata 섹션: endpoint, 요청 간격, 청크 크기)
출력: data/raw/wikidata/{adjacency,items_NN}.json (캐시, gitignore)
      data/processed/kr/wikidata_stations.json (아이템별 한국어 라벨·좌표·노선·역번호·인접 아이템)

Wikidata 라벨은 커뮤니티 번역이라 포탈 매칭에는 쓰지 않는다 (DESIGN 3장). 여기서는 검증용으로만 쓴다.
라이선스: Wikidata 데이터는 CC0.
캐시가 있으면 다시 요청하지 않는다 (--force로 재수집). 요청 사이에 대기하고 User-Agent에 프로젝트명을 넣는다.
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

RAW = ROOT / "data" / "raw" / "wikidata"
OUT = ROOT / "data" / "processed" / "kr" / "wikidata_stations.json"

Q_ADJ = """SELECT ?st ?adj ?line ?towards WHERE {
  ?st wdt:P17 wd:Q884; p:P197 ?s.
  ?s ps:P197 ?adj.
  OPTIONAL { ?s pq:P81 ?line }
  OPTIONAL { ?s pq:P5051 ?towards }
}"""

Q_ITEMS = """SELECT ?st ?ko ?coord ?line ?code ?cls WHERE {{
  VALUES ?st {{ {values} }}
  OPTIONAL {{ ?st rdfs:label ?ko FILTER(LANG(?ko)="ko") }}
  OPTIONAL {{ ?st wdt:P625 ?coord }}
  OPTIONAL {{ ?st wdt:P81 ?line }}
  OPTIONAL {{ ?st wdt:P296 ?code }}
  OPTIONAL {{ ?st wdt:P31 ?cls }}
}}"""


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[1]


def sparql(cfg: dict, ua: str, query: str) -> dict:
    r = requests.get(cfg["endpoint"], params={"query": query},
                     headers={"User-Agent": ua, "Accept": "application/sparql-results+json"}, timeout=120)
    r.raise_for_status()
    return r.json()


def cached(path: Path, force: bool, fetch):
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8")), "cache"
    data = fetch()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data, "download"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    src = yaml.safe_load(open(ROOT / "config" / "sources.yaml", encoding="utf-8"))
    cfg, ua = src["wikidata"], src["user_agent"]
    RAW.mkdir(parents=True, exist_ok=True)

    adj_raw, how = cached(RAW / "adjacency.json", a.force, lambda: sparql(cfg, ua, Q_ADJ))
    print(f"[07] adjacency: {how}, {len(adj_raw['results']['bindings'])} rows")
    adj = {}
    ids = set()
    for b in adj_raw["results"]["bindings"]:
        s, t = qid(b["st"]["value"]), qid(b["adj"]["value"])
        line = qid(b["line"]["value"]) if "line" in b else ""
        ids |= {s, t} | ({line} if line else set())
        adj.setdefault(s, set()).add((t, line))

    ids = sorted(ids, key=lambda q: (len(q), q))
    chunk = cfg["chunk_size"]
    items = {}
    for n, i in enumerate(range(0, len(ids), chunk)):
        part = ids[i:i + chunk]
        path = RAW / f"items_{n:02d}.json"

        def fetch(part=part):
            time.sleep(cfg["request_interval_s"])
            return sparql(cfg, ua, Q_ITEMS.format(values=" ".join(f"wd:{q}" for q in part)))
        data, how = cached(path, a.force, fetch)
        print(f"[07] items chunk {n}: {how}, {len(data['results']['bindings'])} rows")
        for b in data["results"]["bindings"]:
            q = qid(b["st"]["value"])
            it = items.setdefault(q, {"qid": q, "label_ko": "", "coords": set(), "lines": set(), "codes": set(), "classes": set()})
            if "ko" in b:
                it["label_ko"] = b["ko"]["value"]
            if "coord" in b and b["coord"]["value"].startswith("Point("):
                lon, lat = b["coord"]["value"][6:-1].split()
                it["coords"].add((round(float(lat), 6), round(float(lon), 6)))
            if "line" in b:
                it["lines"].add(qid(b["line"]["value"]))
            if "code" in b:
                it["codes"].add(b["code"]["value"])
            if "cls" in b:
                it["classes"].add(qid(b["cls"]["value"]))

    out_items = []
    for q in sorted(items, key=lambda q: (len(q), q)):
        it = items[q]
        coords = sorted(it["coords"])
        out_items.append({
            "qid": q, "label_ko": it["label_ko"],
            "lat": coords[0][0] if coords else None, "lon": coords[0][1] if coords else None,
            "n_coords": len(coords),
            "lines": sorted(it["lines"]), "codes": sorted(it["codes"]), "classes": sorted(it["classes"]),
            "adjacent": [{"qid": t, "line": ln} for t, ln in sorted(adj.get(q, ()))],
        })
    doc = {"meta": {"source": "Wikidata Query Service", "endpoint": cfg["endpoint"], "license": "CC0",
                    "query_adjacency": Q_ADJ, "properties": {"P197": "adjacent station", "P625": "coordinate",
                                                            "P81": "connecting line", "P296": "station code"},
                    "fetched_at": json.loads((RAW / "fetch_meta.json").read_text())["fetched_at"]
                    if (RAW / "fetch_meta.json").exists() and not a.force else
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "counts": {"items": len(out_items), "adjacency_rows": len(adj_raw["results"]["bindings"])}},
           "items": out_items}
    if not (RAW / "fetch_meta.json").exists() or a.force:
        (RAW / "fetch_meta.json").write_text(json.dumps({"fetched_at": doc["meta"]["fetched_at"]}), encoding="utf-8")
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[07] wrote {OUT.relative_to(ROOT)} items={len(out_items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
