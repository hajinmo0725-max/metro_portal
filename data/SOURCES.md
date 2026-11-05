# 데이터 출처·라이선스

| 데이터 | 출처 | 라이선스 | 수집 방식 | 상태 |
| :- | :- | :- | :- | :- |
| 전국도시철도역사정보표준데이터 (역사정보) | 레일포털 data.kric.go.kr `M_01_01/detail.do?id=32` (공공데이터포털 15013205의 제공 시스템, 국가철도공단) | 이용허락범위 제한 없음 | `pipeline/01_fetch_kr_sources.py` 자동 다운로드 (로그인 불필요). data.go.kr 직접 다운로드는 JS XHR 구조라 실패 | **사용 (역 마스터)**. 기준일 2026-06-30 |
| 전국도시철도노선정보표준데이터 (노선정보, 정거장구성) | 레일포털 `detail.do?id=18` | 이용허락범위 제한 없음 | 자동 다운로드 | **사용 (정차 순서 기본값)**. 기준일 2026-06-30 |
| 전국 도시광역철도 역사정보 (다국어 역명) | 레일포털 `detail.do?id=1294` | 레일포털 이용약관 (검증 못 함: 상세 라이선스 문구 미확인) | 자동 다운로드 | **사용 (일/중 역명·부역명 보강만)**. 좌표는 부산 1호선 등에서 오류가 있어 쓰지 않음 |
| OSM 역·노선 (route relation) | OpenStreetMap via Overpass API | ODbL 1.0 (© OpenStreetMap contributors) | Overpass 호출 → 세션 네트워크에서 TLS 리셋으로 실패 | 미사용. 노선 순서는 표준데이터 정거장구성 + `config/kr_lines.yaml` 보정으로 대체. Overpass가 허용되면 교차검증용으로 추가 예정 |
| Wikidata 한국 역 인접역(P197)·좌표(P625)·노선(P81)·역번호(P296) | Wikidata Query Service `query.wikidata.org/sparql` | CC0 1.0 | `pipeline/07_fetch_wikidata.py` (SPARQL 7회: 인접 1 + 아이템 청크 6, 요청 간 3초, User-Agent에 프로젝트명). 원문 캐시 `data/raw/wikidata/` | **검증용만 사용** (N2 노선 순서·N3 좌표 교차검증, `data/processed/kr/wikidata_stations.json`). 한국어 라벨은 커뮤니티 번역이라 포탈 매칭에 쓰지 않는다. 좌표 보정 1건(동해선 동래)에 값 사용 |
