#!/usr/bin/env bash
# 전체 파이프라인 재생성. 원본은 캐시가 있으면 다시 받지 않는다.
# 사용: scripts/build_all.sh [ruleset]   (기본 strict)
set -euo pipefail
cd "$(dirname "$0")/.."
RS="${1:-strict}"
python3 pipeline/01_fetch_kr_sources.py
python3 pipeline/02_build_kr_stations.py
python3 pipeline/03_build_kr_lines.py
python3 pipeline/04_build_graph.py --ruleset "$RS" > /dev/null
# 비교용 ruleset (환승 비용 1). 기본 ruleset을 바꿔 돌릴 때는 생략
if [ "$RS" = "strict" ]; then python3 pipeline/04_build_graph.py --ruleset strict_transfer1 > /dev/null; fi
python3 pipeline/05_route.py --ruleset "$RS" --examples > /dev/null
python3 pipeline/06_build_web_data.py --ruleset "$RS"
# 노선 순서·좌표 검증 (Wikidata 캐시가 없으면 받아 온다). PNG까지 약 1분
python3 pipeline/07_fetch_wikidata.py > /dev/null
python3 pipeline/08_validate_lines.py > /dev/null
# ruleset 비교 (환승 비용 × D)
python3 pipeline/09_compare_rulesets.py > /dev/null
python3 -m pytest -q
npm test --silent
