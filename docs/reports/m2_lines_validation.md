# M2 노선 검증 리포트

생성: `python3 pipeline/03_build_kr_lines.py`

## 요약

| 항목 | 값 |
| :- | -: |
| lines | 46 |
| sequences | 50 |
| ride_edges | 1060 |
| stations | 1097 |
| stations_sequenced | 1096 |
| stop_failures | 0 |
| outliers | 21 |
| outliers_unexplained | 0 |

노선 순서 소스: 레일포털 표준데이터 노선정보 '정거장구성' + config/kr_lines.yaml 보정.
OSM route relation은 세션 네트워크에서 Overpass 접근 불가(TLS 리셋)라 쓰지 못했다.

## 1. 정차역 매칭 실패

없음.

## 2. 어떤 시퀀스에도 안 들어간 역

| id | 역명 | 노선그룹 |
| :- | :- | :- |
| kr:I4108:경의중앙선:1019 | 광운대역 | I4108:경의중앙선 |

## 3. 인접역 간 거리 이상치

기준: config/validation.yaml. 이상치가 곧 오류는 아니다 (교외 구간은 원래 길다). 목록을 보고 순서 오류만 보정한다.

| 노선 | A | B | 거리(m) | 사유 | 판정 |
| :- | :- | :- | -: | :- | :- |
| arex | 디지털미디어시티 | 마곡나루 | 6335 | >6000m | 실제 장거리 구간(판단) |
| arex | 청라국제도시 | 영종 | 10143 | >6000m | 실제 장거리 구간(판단) |
| daegu-1 | 대구한의대병원 | 부호(경일대·호산대) | 5682 | >4.0×중앙값(893m) | 실제 장거리 구간(판단) |
| daegyeong | 북삼역 | 왜관역 | 8692 | >6000m | 실제 장거리 구간(판단) |
| daegyeong | 왜관역 | 서대구역 | 17553 | >6000m | 실제 장거리 구간(판단) |
| daegyeong | 동대구역 | 경산역 | 11138 | >6000m | 실제 장거리 구간(판단) |
| donghae | 서생역 | 남창역 | 8242 | >6000m | 실제 장거리 구간(판단) |
| gyeongchun | 마석역 | 대성리역 | 6898 | >6000m | 실제 장거리 구간(판단) |
| gyeongchun | 대성리역 | 청평역 | 7089 | >6000m | 실제 장거리 구간(판단) |
| gyeongchun | 상천역 | 가평역 | 6986 | >6000m | 실제 장거리 구간(판단) |
| gyeongchun | 강촌역 | 김유정역 | 7191 | >6000m | 실제 장거리 구간(판단) |
| gyeonggang | 이매역 | 삼동역 | 6926 | >6000m | 실제 장거리 구간(판단) |
| gyeonggang | 곤지암역 | 신둔도예촌역 | 6515 | >6000m | 실제 장거리 구간(판단) |
| gyeonggang | 신둔도예촌역 | 이천역 | 6569 | >6000m | 실제 장거리 구간(판단) |
| gyeonggang | 부발역 | 세종대왕릉역 | 8021 | >6000m | 실제 장거리 구간(판단) |
| incheon-maglev | 파라다이스시티역 | 워터파크역 | 2435 | >4.0×중앙값(468m) | 실제 장거리 구간(판단) |
| seohae | 능곡역 | 김포공항역 | 6463 | >6000m | 실제 장거리 구간(판단) |
| seoul-1-gyeongbu | 평택역 | 성환역 | 9096 | >6000m | 실제 장거리 구간(판단) |
| seoul-1-gyeongwon | 전곡역 | 연천역 | 8502 | >6000m, >4.0×중앙값(1493m) | 실제 장거리 구간(판단) |
| seoul-4-jinjeop | 오남역 | 별내별가람역 | 7846 | >6000m | 실제 장거리 구간(판단) |
| shinbundang | 청계산입구 | 판교 | 7743 | >6000m, >4.0×중앙값(1701m) | 실제 장거리 구간(판단) |

## 4. 노선별 커버리지

pool = 이 노선에 속한 표준데이터 역 수, sequenced = 시퀀스에 들어간 역 수 (직결 분기점 포함)

| 노선 | 이름 | pool | sequenced | pool∩seq | 시퀀스 | 엣지 |
| :- | :- | -: | -: | -: | -: | -: |
| seoul-1-gyeongin | 1호선 경인선 | 20 | 21 | 20 | 1 | 20 |
| seoul-3 | 3호선 | 34 | 34 | 34 | 1 | 33 |
| seoul-4 | 4호선 | 26 | 26 | 26 | 1 | 25 |
| shinbundang | 신분당선 | 16 | 16 | 16 | 1 | 15 |
| donghae | 동해선 (광역전철) | 23 | 23 | 23 | 1 | 22 |
| daegyeong | 대경선 | 8 | 8 | 8 | 1 | 7 |
| arex | 공항철도 | 14 | 14 | 14 | 1 | 13 |
| suin-bundang | 수인·분당선 (분당선 구간) | 36 | 36 | 36 | 1 | 35 |
| suin-bundang-suin | 수인·분당선 (수인선 구간) | 26 | 27 | 26 | 1 | 26 |
| seoul-1-gyeongbu | 1호선 경부선 | 45 | 46 | 45 | 3 | 45 |
| seoul-1 | 1호선 (서울역~청량리) | 10 | 10 | 10 | 1 | 9 |
| seoul-1-gyeongwon | 1호선 경원선 | 35 | 28 | 28 | 1 | 27 |
| seoul-4-ansan | 4호선 안산·과천선 | 22 | 23 | 22 | 1 | 22 |
| seoul-4-jinjeop | 4호선 진접선 | 3 | 4 | 3 | 1 | 3 |
| seoul-3-ilsan | 3호선 일산선 | 11 | 11 | 11 | 1 | 10 |
| gyeongui-jungang | 경의·중앙선 | 86 | 57 | 57 | 2 | 56 |
| gyeongchun | 경춘선 | 20 | 23 | 20 | 1 | 22 |
| gyeonggang | 경강선 | 12 | 12 | 12 | 1 | 11 |
| seohae | 서해선 | 21 | 21 | 21 | 1 | 20 |
| sillim | 신림선 | 11 | 11 | 11 | 1 | 10 |
| ui-sinseol | 우이신설선 | 13 | 13 | 13 | 1 | 12 |
| busan-4 | 부산 4호선 | 14 | 14 | 14 | 1 | 13 |
| everline | 용인 에버라인 | 15 | 15 | 15 | 1 | 14 |
| gimpo-gold | 김포골드라인 | 10 | 10 | 10 | 1 | 9 |
| uijeongbu | 의정부 경전철 | 15 | 15 | 15 | 1 | 14 |
| busan-gimhae | 부산김해경전철 | 21 | 21 | 21 | 1 | 20 |
| seoul-2 | 2호선 | 43 | 43 | 43 | 1 | 43 |
| seoul-5 | 5호선 | 56 | 56 | 56 | 2 | 55 |
| seoul-6 | 6호선 | 39 | 39 | 39 | 1 | 38 |
| seoul-7-incheon | 7호선 (인천 구간) | 11 | 12 | 11 | 1 | 11 |
| seoul-7 | 7호선 | 42 | 42 | 42 | 1 | 41 |
| seoul-8 | 8호선 | 22 | 24 | 22 | 1 | 23 |
| seoul-9 | 9호선 | 38 | 38 | 38 | 1 | 37 |
| seoul-2-seongsu | 2호선 성수지선 | 4 | 5 | 4 | 1 | 4 |
| seoul-2-sinjeong | 2호선 신정지선 | 3 | 5 | 3 | 1 | 4 |
| busan-1 | 부산 1호선 | 40 | 40 | 40 | 1 | 39 |
| busan-2 | 부산 2호선 | 43 | 43 | 43 | 1 | 42 |
| busan-3 | 부산 3호선 | 17 | 17 | 17 | 1 | 16 |
| daegu-1 | 대구 1호선 | 35 | 35 | 35 | 1 | 34 |
| daegu-2 | 대구 2호선 | 29 | 29 | 29 | 1 | 28 |
| daegu-3 | 대구 3호선 | 30 | 30 | 30 | 1 | 29 |
| incheon-1 | 인천 1호선 | 33 | 33 | 33 | 1 | 32 |
| incheon-2 | 인천 2호선 | 27 | 27 | 27 | 1 | 26 |
| incheon-maglev | 인천공항 자기부상철도 | 6 | 6 | 6 | 1 | 5 |
| gwangju-1 | 광주 1호선 | 20 | 20 | 20 | 1 | 19 |
| daejeon-1 | 대전 1호선 | 22 | 22 | 22 | 1 | 21 |

## 5. 보정 내역

### 좌표 보정 (config/kr_station_fixes.yaml)

| id | 역명 | 이동 거리(m) |
| :- | :- | -: |
| kr:I4108:1204 | 양원역 | 189462 |
| kr:S1105:0514 | 마곡 | 1027 |
| kr:I1104:0430 | 이촌(국립중앙박물관) | 879 |

### 노선 보정 (config/kr_lines.yaml)

| 노선 id | 원본 | 보정 종류 |
| :- | :- | :- |
| seoul-1 | I4101 수도권 광역철도 1호선 | pools |
| seoul-1-gyeongbu | I4101 경부선 | branches, patch, pools |
| seoul-1-gyeongin | I1101 경인선 | patch |
| seoul-1-gyeongwon | I4102 경원선 | pools |
| seoul-2 | S1102 수도권 도시철도 2호선 | circular |
| seoul-2-seongsu | S1121 수도권 도시철도 2호선 | patch |
| seoul-2-sinjeong | S1122 수도권 도시철도 2호선 | sequences |
| seoul-4-jinjeop | I4104 진접선 | patch |
| seoul-4-ansan | I4103 안산·과천선 | patch |
| seoul-5 | S1105 수도권 도시철도 5호선 | branches, patch |
| seoul-7 | S1107 수도권 도시철도 7호선 | pools |
| seoul-7-incheon | S1107 도시철도 7호선 | patch, pools |
| seoul-8 | S1108 수도권 도시철도 8호선 | patch |
|  | S4108 수도권 전철 8호선 | skip |
| gyeongui-jungang | I4108 경의·중앙선 | pools, sequences |
| gyeongchun | I41K2 경춘선 | patch, pools |
| suin-bundang | I28K1 분당선 | patch, pools |
| suin-bundang-suin | I28K1 수인선 | patch, pools |
| seohae | I41WS 서해선 | patch |
| incheon-1 | S2801 인천지하철 1호선 | patch |
