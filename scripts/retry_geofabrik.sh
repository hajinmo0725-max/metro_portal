#!/usr/bin/env bash
# A5용 Geofabrik 접속 재시도. 같은 호스트·같은 경로로 간격을 두고 다시 시도만 한다 (위장·미러·다른 경로 없음, CLAUDE.md).
# 열리면 OPEN을 출력하고 0으로 끝난다. 시도마다 시각·결과를 로그에 남긴다.
# 사용: scripts/retry_geofabrik.sh [재시도 횟수=9] [간격 초=60] [로그=docs/reports/evidence/geofabrik_attempts.log]
set -u
URL="https://download.geofabrik.de/asia/south-korea-latest.osm.pbf.md5"
n=${1:-9}; gap=${2:-60}; log=${3:-docs/reports/evidence/geofabrik_attempts.log}
start=$(date -u +%FT%TZ)
err=$(curl -S -o /dev/null --max-time 30 --retry "$n" --retry-delay "$gap" --retry-all-errors "$URL" 2>&1 >/dev/null)
rc=$?
tries=$(( $(printf "%s" "$err" | grep -c "Will retry") + 1 ))
end=$(date -u +%FT%TZ)
if [ $rc -eq 0 ]; then
  echo "$start ~ $end 시도 $tries회: 열림" >> "$log"; echo "OPEN $end"; exit 0
fi
last=$(printf "%s" "$err" | grep -v "Will retry" | tail -1)
echo "$start ~ $end 시도 $tries회: 실패 ($last)" >> "$log"; echo "BLOCKED $end ($tries tries)"; exit 1
