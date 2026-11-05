# 데이터 출처·라이선스

| 데이터 | 출처 | 라이선스 | 수집 방식 | 상태 |
| :- | :- | :- | :- | :- |
| 전국도시철도역사정보표준데이터 (역사정보) | 레일포털 data.kric.go.kr `M_01_01/detail.do?id=32` (공공데이터포털 15013205의 제공 시스템, 국가철도공단) | 이용허락범위 제한 없음 | `pipeline/01_fetch_kr_sources.py` 자동 다운로드 (로그인 불필요). data.go.kr 직접 다운로드는 JS XHR 구조라 실패 | **사용 (역 마스터)**. 기준일 2026-06-30 |
| 전국도시철도노선정보표준데이터 (노선정보, 정거장구성) | 레일포털 `detail.do?id=18` | 이용허락범위 제한 없음 | 자동 다운로드 | **사용 (정차 순서 기본값)**. 기준일 2026-06-30 |
| 전국 도시광역철도 역사정보 (다국어 역명) | 레일포털 `detail.do?id=1294` | 레일포털 이용약관 (검증 못 함: 상세 라이선스 문구 미확인) | 자동 다운로드 | **사용 (일/중 역명·부역명 보강)**. 좌표는 부산 1호선 등에서 오류가 있어 보강에는 쓰지 않음. 3차부터 표준데이터 미수록 GTX-A 9역은 이 파일 행(좌표·이름·신설일자·환승노선명)으로 역 레코드를 만든다 (`config/kr_supplement.yaml`). 기준일 2026-07-01 |
| OSM 역·노선 (route relation) | OpenStreetMap via Overpass API, Geofabrik 추출본(.osm.pbf) | ODbL 1.0 (© OpenStreetMap contributors) | Overpass·Geofabrik 둘 다 허용 목록에 있으나 세션 egress에서 TLS 핸드셰이크 중 터널 종료(2026-11-05 2·3차 동일) | 미사용. 우회 시도 안 함 (미러·다른 OSM 배포처도 쓰지 않음) |
| Wikidata 한국 역 인접역(P197)·좌표(P625)·노선(P81)·역번호(P296) | Wikidata Query Service `query.wikidata.org/sparql` | CC0 1.0 | `pipeline/07_fetch_wikidata.py` (SPARQL 7회: 인접 1 + 아이템 청크 6, 요청 간 3초, User-Agent에 프로젝트명). 원문 캐시 `data/raw/wikidata/` | **검증용만 사용** (N2 노선 순서·N3 좌표 교차검증, `data/processed/kr/wikidata_stations.json`). 한국어 라벨은 커뮤니티 번역이라 포탈 매칭에 쓰지 않는다. 좌표 보정 1건(동해선 동래)에 값 사용 |
| Wikidata GTX-A·2024년 이후 개통 역 | Wikidata Query Service | CC0 1.0 | SPARQL 2회 (3차 A6, 수동 실행 기록: docs/reports/a6_missing_lines.md) | 개통 확인 근거로만 사용 |
| 개통 여부 웹 검색 | WebSearch 도구 결과 (뉴스 기사 제목·요약) | 각 기사 저작권 | 3차 A6에서 3회 검색. 본문 수집 안 함 | 의심 목록 판단 근거로만 사용. 출처 URL은 a6 보고서에 기록 |
| 타이베이 대도시권 도시철도 역·노선·인접·역번호 (Phase 1) | Wikidata Query Service (P16 교통망 ∈ 臺北捷運·新北捷運·桃園捷運, 또는 P81 ∈ 범위 노선) | CC0 1.0 | `pipeline/14_fetch_tw_wikidata.py` (SPARQL 4회, 요청 간 3초, User-Agent에 프로젝트명). 원문 캐시 `data/raw/wikidata_tw/` | **사용 (구조·좌표·순서·역번호)**. Geofabrik 대만 추출본·대만 공식 오픈데이터(data.taipei, data.gov.tw, TDX, 운영사 사이트)가 세션 네트워크에서 막혀 대체. 공식명(P1448) 0건이라 이름(zh-Hant·en 라벨)은 official=False로만 저장 |
| Unihan 이체자 데이터 (Phase 1 T2) | Unicode Consortium `www.unicode.org/Public/UCD/latest/ucd/Unihan.zip` | Unicode License v3 | `pipeline/16_fetch_unihan.py` 자동 다운로드, 캐시 `data/raw/unihan/` | T2 이체자 정규화 |
| OpenCC 변환표 (Phase 1 T2) | PyPI `opencc` 패키지 내장 사전 | Apache-2.0 | `pip install opencc` | T2 이체자 정규화 |
