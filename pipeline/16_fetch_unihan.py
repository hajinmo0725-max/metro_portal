#!/usr/bin/env python3
"""B2-1. Unihan 이체자 데이터 받기 (T2 이체자 정규화용). 캐시가 있으면 다시 받지 않는다.

입력: config/sources.yaml unihan
출력: data/raw/unihan/Unihan_Variants.txt, data/raw/unihan/fetch_meta.json
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402

RAW = ROOT / "data" / "raw" / "unihan"


def main() -> int:
    src = yaml.safe_load(open(ROOT / "config" / "sources.yaml", encoding="utf-8"))
    cfg = src["unihan"]
    out = RAW / cfg["member"]
    if out.exists() and "--force" not in sys.argv:
        print(f"[16] cache {out.relative_to(ROOT)}")
        return 0
    RAW.mkdir(parents=True, exist_ok=True)
    r = requests.get(cfg["url"], headers={"User-Agent": src["user_agent"]}, timeout=180)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        out.write_bytes(z.read(cfg["member"]))
        version = next((ln for ln in z.read(cfg["member"]).decode("utf-8").splitlines()[:5] if "Unihan" in ln or "Date" in ln), "")
    (RAW / "fetch_meta.json").write_text(json.dumps({"url": cfg["url"], "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                     "bytes": len(r.content), "header": version}, ensure_ascii=False), encoding="utf-8")
    print(f"[16] downloaded {len(r.content)} bytes → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
