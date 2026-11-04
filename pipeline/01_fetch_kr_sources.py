#!/usr/bin/env python3
"""M1-1. 한국 역·노선 원본 수집.

입력: config/sources.yaml
출력: data/raw/kric/{stations_std,lines_std,stations_metro}.xlsx, data/raw/kric/fetch_log.json

우선순위: data/raw/manual/kric/<key>.xlsx (수동 다운로드) > 캐시 > 레일포털 다운로드.
이미 받은 파일은 --force 없이는 다시 받지 않는다 (외부 API 매너, CLAUDE.md).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402

RAW = ROOT / "data" / "raw" / "kric"
MANUAL = ROOT / "data" / "raw" / "manual" / "kric"
XLSX_MAGIC = b"PK\x03\x04"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="캐시 무시하고 다시 받기")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(ROOT / "config" / "sources.yaml", encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    log = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {}}
    ok = True
    for i, (key, spec) in enumerate(sorted(cfg["kric"]["files"].items())):
        out = RAW / f"{key}.xlsx"
        manual = MANUAL / f"{key}.xlsx"
        entry = {"url": spec["url"], "title": spec["title"]}
        if manual.exists():
            shutil.copyfile(manual, out)
            entry.update(source="manual", path=str(manual.relative_to(ROOT)))
        elif out.exists() and not args.force:
            entry.update(source="cache")
        else:
            if i:
                time.sleep(cfg["request_interval_s"])
            try:
                r = requests.get(spec["url"], headers={"User-Agent": cfg["user_agent"]}, timeout=120)
                r.raise_for_status()
                if not r.content.startswith(XLSX_MAGIC):
                    raise ValueError(f"not an xlsx (content-type={r.headers.get('content-type')})")
                out.write_bytes(r.content)
                entry.update(source="download", status=r.status_code,
                             content_disposition=(r.headers.get("content-disposition") or "").encode("latin-1", "replace").decode("utf-8", "replace"))
            except Exception as e:  # noqa: BLE001
                entry.update(source="error", error=f"{type(e).__name__}: {e}")
                ok = False
        if out.exists():
            entry["bytes"] = out.stat().st_size
        log["files"][key] = entry
        print(f"[01] {key}: {entry['source']} {entry.get('bytes', '')} {entry.get('error', '')}")
    (RAW / "fetch_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    if not ok:
        print("[01] 일부 다운로드 실패. data/raw/manual/kric/에 수동 파일을 두면 그걸 쓴다.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
