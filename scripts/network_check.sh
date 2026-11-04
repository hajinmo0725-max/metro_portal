#!/usr/bin/env bash
# 외부 데이터 호스트 접근성 점검. 결과를 markdown 표로 stdout에 출력한다.
# 사용: scripts/network_check.sh > docs/reports/network_check.md
set -u
UA="metro_portal/0.1 (side project; network check)"
HOSTS=(
  "https://data.go.kr/"
  "https://www.data.go.kr/"
  "https://data.kric.go.kr/"
  "https://overpass-api.de/api/status"
  "https://query.wikidata.org/"
  "https://apis.data.go.kr/"
  "https://api.odcloud.kr/"
  "https://z.overpass-api.de/api/status"
  "https://overpass.kumi.systems/api/status"
  "https://overpass.private.coffee/api/status"
  "https://maps.mail.ru/osm/tools/overpass/api/status"
  "https://download.geofabrik.de/"
  "https://tile.openstreetmap.org/"
  "https://unpkg.com/"
  "https://cdn.jsdelivr.net/"
  "https://registry.npmjs.org/"
  "https://pypi.org/simple/"
)
echo "점검 시각(UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "| URL | HTTP 상태 | x-deny-reason | 비고 |"
echo "| :- | :- | :- | :- |"
for u in "${HOSTS[@]}"; do
  hdr=$(curl -sS -o /dev/null -D - --max-time 20 -A "$UA" "$u" 2>&1)
  # 프록시 CONNECT 응답(200 Connection Established) 이후의 실제 응답 코드
  code=$(printf "%s" "$hdr" | grep -E "^HTTP/" | grep -v "Connection Established" | tail -1 | awk '{print $2}')
  deny=$(printf "%s" "$hdr" | grep -i "^x-deny-reason:" | tail -1 | cut -d: -f2- | tr -d '\r ')
  note=""
  if printf "%s" "$hdr" | grep -q "CONNECT tunnel failed, response 403"; then code="403"; note="프록시 CONNECT 거부 (허용 목록 밖)"; fi
  if printf "%s" "$hdr" | grep -q "Connection reset"; then code="-"; note="CONNECT 허용, TLS 핸드셰이크 중 연결 리셋"; fi
  echo "| $u | ${code:--} | ${deny:-없음} | ${note} |"
  sleep 1
done
