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
# 게임 데이터 (퍼즐 후보, N정류장 최대 거리). 약 20초
python3 pipeline/10_build_game_data.py --ruleset "$RS" > /dev/null
python3 pipeline/11_fun_facts.py --ruleset "$RS" > /dev/null
# 환승 판정 감사 (3차 A3 공식 우선 vs D=500, A4 좌표 복사)
python3 pipeline/12_audit_transfers.py --ruleset "$RS" > /dev/null
# 5차: Unihan은 18(tw_t123 미리보기)이 쓰므로 그보다 먼저 받는다 (fresh clone에서 18이 실패하던 순서 버그)
python3 pipeline/16_fetch_unihan.py > /dev/null
# 4차 Q0: 개통 예정 노선(config/kr_planned.yaml)을 켰을 때의 포탈 미리보기, 최근 개통 역 점검
python3 pipeline/18_planned_preview.py > /dev/null
python3 scripts/q0_checklist.py > /dev/null
# Phase 1 타이베이 (Wikidata 캐시가 없으면 받아 온다), Unihan, 한국+타이베이 ruleset 비교
python3 pipeline/14_fetch_tw_wikidata.py > /dev/null
python3 pipeline/15_build_tw.py > /dev/null
python3 pipeline/17_compare_world_rulesets.py > /dev/null   # 약 1.5분 (한국 내 전쌍 최단 비용 × ruleset 5개)
python3 pipeline/19_t2_audit.py > /dev/null                 # 4차 Q6-7: T2 포탈 이체자 근거·다대일 의존 감사표
# 웹 통합 번들 (web/world.js RULESETS와 같은 목록)
for r in tw_t1 tw_t12 tw_t123 tw_t12_official tw_t123b; do python3 pipeline/06_build_web_data.py --ruleset "$r" --countries KR,TW > /dev/null; done
# 5차 R3: 도식 노선도는 커밋된 풀이 캐시(data/processed/schematic/<권역>.json)로만 웹 번들·SVG를 만든다 (결정적).
# 풀이(재계산)는 따로: python3 pipeline/20_solve_schematic.py [--regions ...]  — 수도권은 시간 제한 해라 재현되지 않는다.
# 그래프가 바뀌어 캐시 지문이 안 맞으면 21이 실패하고 어느 권역을 다시 풀어야 하는지 알려 준다
python3 pipeline/21_build_schematic_web.py > /dev/null
python3 -m pytest -q
npm test --silent
