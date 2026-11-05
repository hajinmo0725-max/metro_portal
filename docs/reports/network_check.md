# 네트워크 점검 (M0)

재현: `scripts/network_check.sh`

점검 시각(UTC): 2026-11-04T19:45:35Z

| URL | HTTP 상태 | x-deny-reason | 비고 |
| :- | :- | :- | :- |
| https://data.go.kr/ | 301 | 없음 |  |
| https://www.data.go.kr/ | 200 | 없음 |  |
| https://data.kric.go.kr/ | 200 | 없음 |  |
| https://overpass-api.de/api/status | - | 없음 | CONNECT 허용, TLS 핸드셰이크 중 연결 리셋 |
| https://query.wikidata.org/ | 200 | 없음 |  |
| https://apis.data.go.kr/ | 400 | 없음 |  |
| https://api.odcloud.kr/ | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://z.overpass-api.de/api/status | - | 없음 | CONNECT 허용, TLS 핸드셰이크 중 연결 리셋 |
| https://overpass.kumi.systems/api/status | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://overpass.private.coffee/api/status | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://maps.mail.ru/osm/tools/overpass/api/status | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://download.geofabrik.de/ | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://tile.openstreetmap.org/ | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://unpkg.com/ | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://cdn.jsdelivr.net/ | 403 | 없음 | 프록시 CONNECT 거부 (허용 목록 밖) |
| https://registry.npmjs.org/ | 200 | 없음 |  |
| https://pypi.org/simple/ | 200 | 없음 |  |

## 해석

- `x-deny-reason`: 모든 403은 프록시가 **CONNECT 단계**에서 거부한 것이라 curl이 응답 헤더를 노출하지 않는다. 그래서 헤더 값은 전부 "없음"으로 찍힌다. 프록시 상태 엔드포인트(`$HTTPS_PROXY/__agentproxy/status`)의 `recentRelayFailures`에는 `connect_rejected: gateway answered 403 to CONNECT (policy denial or upstream failure)`로 기록됐다.
- **overpass-api.de / z.overpass-api.de**: CONNECT는 200으로 허용되지만 TLS 핸드셰이크 도중 터널이 닫힌다 (`ws_closed_mid_exchange ... 517 B sent, 39 B received`). 정책 403과 증상이 다르다. 허용 목록에는 있는데 상류(egress 또는 Overpass 서버)에서 끊는 것으로 보인다. 원인은 검증 못 함. 3회 이상 간격 두고 재시도해도 동일.
- **data.go.kr**: 페이지는 열리지만 표준데이터 파일 다운로드는 브라우저 JS가 `/download/columList.json`·`/download/standard.json`을 XHR로 호출해서 클라이언트에서 CSV를 조립하는 구조다. 일반 GET은 404 에러 페이지를 돌려준다. OpenAPI(`apis.data.go.kr`)는 serviceKey가 필요하다. → 자동 수집 불가로 판정.
- **query.wikidata.org**: SPARQL 정상 (200). 한때 대체 소스로 검토했으나, 레일포털(data.kric.go.kr) 공개 다운로드 URL로 표준데이터를 받을 수 있어서 쓰지 않았다.
- **data.kric.go.kr**: 200. 표준데이터 상세 페이지의 공개 다운로드 URL(`/rips/dataset/download.file?...`)이 로그인 없이 XLSX를 준다 → M1·M2 소스.
- 2026-11-04T20:13Z 재시도: overpass-api.de가 502로 바뀌었지만 여전히 사용 불가.
- 지도 타일(tile.openstreetmap.org)·CDN(unpkg, jsdelivr)은 **세션에서만** 막힌다. 배포된 웹페이지는 사용자 브라우저에서 열리므로 영향 없음. 다만 세션 내 테스트를 위해 Leaflet은 npm registry에서 받아 `web/vendor/`에 번들한다.
