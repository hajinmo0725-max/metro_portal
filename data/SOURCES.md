# 데이터 출처·라이선스

| 데이터 | 출처 | 라이선스 | 수집 방식 | 상태 |
| :- | :- | :- | :- | :- |
| 전국도시철도역사정보표준데이터 | 공공데이터포털 data.go.kr 15013205 (제공: 국가철도공단 철도산업정보센터) | 이용허락범위 제한 없음 | 자동 수집 시도 → 실패 (브라우저 JS XHR 다운로드, OpenAPI는 serviceKey 필요) | 미사용. 수동 다운로드 시 `data/raw/manual/`에 커밋 |
| OSM 역·노선 (route relation) | OpenStreetMap via Overpass API | ODbL 1.0 (© OpenStreetMap contributors) | Overpass 호출 → 세션 네트워크에서 TLS 리셋으로 실패 | 미사용. 허용되면 `pipeline/02_fetch_osm_routes.py`로 재생성 |
