# N2 노선 순서 검증 (OSM 없이)

생성: `python3 pipeline/08_validate_lines.py`. 임계값: `config/validation.yaml`

근거 1 = 좌표 기하 (2-opt 최적 경로 비교, 급반전, 국소 스왑). 근거 2 = Wikidata P197 인접역. `config/kr_lines.yaml` 수정은 두 근거가 같은 결론일 때만 한다.

## Wikidata 매칭

| 방법 | 역 레코드 수 |
| :- | -: |
| adj | 123 |
| adj+nearest | 4 |
| coord_fallback | 6 |
| nearest | 1 |
| no_candidate | 1 |
| unique | 7 |
| unique+adj | 958 |

unique = 이름 후보 1개, adj = 이웃 역과 P197 인접인 후보, nearest = 동률이라 거리로 고름, coord_fallback = 같은 이름 아이템이 없어 가까운 아이템을 붙임(라벨 차이, 좌표 검사 제외), no_candidate = 매칭 없음

| 우리 역 | Wikidata 라벨 (coord_fallback) | 거리(m) |
| :- | :- | -: |
| 총신대입구(이수) (4호선) | 이수역 | 36 |
| 건대입구 (2호선) | 건국대역 | 63 |
| 건대입구 (7호선) | 건국대역 | 156 |
| 수성알파시티(삼성라이온즈파크) (대구 도시철도 2호선) | 대공원역 | 36 |
| 서구청 (인천지하철 2호선) | 서해구청역 | 20 |
| 학동증심사입구 (광주도시철도 1호선) | 학동·증심사입구역 | 62 |

## 시퀀스별 요약

ratio = 현재 길이 / 좌표 최적 경로 길이. 1.02 초과면 순서 의심.

| 노선 | 시퀀스 | 역 | 현재 km | 최적 km | ratio | 기하 의심 엣지 | WD 비인접 | WD 매칭 안 됨 | 둘 다 | WD 추가 인접 | PNG |
| :- | :- | -: | -: | -: | -: | -: | -: | -: | -: | -: | :- |
| 1호선 경인선 | main | 21 | 25.8 | 25.8 | 1.000 | 0 | 0 | 0 | 0 | 9 | [png](lines/seoul-1-gyeongin__main.png) |
| 3호선 | main | 34 | 36.3 | 36.3 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-3__main.png) |
| 4호선 | main | 26 | 29.5 | 29.5 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-4__main.png) |
| 신분당선 | main | 16 | 31.4 | 31.4 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/shinbundang__main.png) |
| 동해선 (광역전철) | main | 23 | 60.3 | 60.3 | 1.000 | 0 | 0 | 0 | 0 | 1 | [png](lines/donghae__main.png) |
| 대경선 | main | 8 | 54.3 | 54.3 | 1.000 | 0 | 1 | 0 | 0 | 4 | [png](lines/daegyeong__main.png) |
| 공항철도 | main | 14 | 55.7 | 55.7 | 1.000 | 0 | 0 | 2 | 0 | 1 | [png](lines/arex__main.png) |
| 수인·분당선 (분당선 구간) | main | 36 | 50.5 | 50.5 | 1.000 | 0 | 1 | 0 | 0 | 1 | [png](lines/suin-bundang__main.png) |
| 수인·분당선 (수인선 구간) | main | 27 | 49.1 | 49.1 | 1.000 | 0 | 2 | 0 | 0 | 2 | [png](lines/suin-bundang-suin__main.png) |
| 1호선 경부선 | main | 44 | 113.2 | 113.2 | 1.000 | 0 | 0 | 0 | 0 | 17 | [png](lines/seoul-1-gyeongbu__main.png) |
| 1호선 경부선 | gwangmyeong | 2 | 4.5 | 4.5 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-1-gyeongbu__gwangmyeong.png) |
| 1호선 경부선 | seodongtan | 2 | 2.1 | 2.1 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-1-gyeongbu__seodongtan.png) |
| 1호선 (서울역~청량리) | main | 10 | 7.5 | 7.5 | 1.000 | 0 | 0 | 0 | 0 | 1 | [png](lines/seoul-1__main.png) |
| 1호선 경원선 | main | 28 | 59.1 | 59.1 | 1.000 | 0 | 0 | 0 | 0 | 6 | [png](lines/seoul-1-gyeongwon__main.png) |
| 4호선 안산·과천선 | main | 23 | 38.0 | 38.0 | 1.000 | 0 | 0 | 0 | 0 | 4 | [png](lines/seoul-4-ansan__main.png) |
| 4호선 진접선 | main | 4 | 13.1 | 13.1 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-4-jinjeop__main.png) |
| 3호선 일산선 | main | 11 | 18.1 | 18.1 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-3-ilsan__main.png) |
| 경의·중앙선 | main | 55 | 120.8 | 120.8 | 1.000 | 0 | 0 | 0 | 0 | 19 | [png](lines/gyeongui-jungang__main.png) |
| 경의·중앙선 | seoul-station | 3 | 5.2 | 5.2 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/gyeongui-jungang__seoul-station.png) |
| 경춘선 | main | 22 | 80.1 | 80.1 | 1.000 | 0 | 0 | 0 | 0 | 1 | [png](lines/gyeongchun__main.png) |
| 경춘선 | cheongnyangni | 4 | 4.0 | 4.0 | 1.000 | 0 | 0 | 0 | 0 | 1 | [png](lines/gyeongchun__cheongnyangni.png) |
| 경강선 | main | 12 | 53.3 | 53.3 | 1.000 | 0 | 0 | 0 | 0 | 1 | [png](lines/gyeonggang__main.png) |
| 서해선 | main | 21 | 45.4 | 45.4 | 1.000 | 0 | 0 | 0 | 0 | 2 | [png](lines/seohae__main.png) |
| 신림선 | main | 11 | 6.8 | 6.8 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/sillim__main.png) |
| 우이신설선 | main | 13 | 10.5 | 10.5 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/ui-sinseol__main.png) |
| 부산 4호선 | main | 14 | 11.2 | 11.2 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/busan-4__main.png) |
| 용인 에버라인 | main | 15 | 16.4 | 16.4 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/everline__main.png) |
| 김포골드라인 | main | 10 | 21.7 | 21.7 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/gimpo-gold__main.png) |
| 의정부 경전철 | main | 15 | 9.7 | 9.7 | 1.000 | 0 | 2 | 0 | 0 | 0 | [png](lines/uijeongbu__main.png) |
| 부산김해경전철 | main | 21 | 21.5 | 21.5 | 1.000 | 0 | 3 | 0 | 0 | 0 | [png](lines/busan-gimhae__main.png) |
| 2호선 | main | 43 | 47.1 | 47.1 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-2__main.png) |
| 5호선 | main | 49 | 50.0 | 50.0 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-5__main.png) |
| 5호선 | macheon | 8 | 6.5 | 6.5 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-5__macheon.png) |
| 6호선 | main | 34 | 29.3 | 29.3 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-6__main.png) |
| 6호선 | eungam-loop | 6 | 6.1 | 6.1 | 1.000 | 2 | 0 | 0 | 0 | 0 | [png](lines/seoul-6__eungam-loop.png) |
| 7호선 (인천 구간) | main | 12 | 13.9 | 13.9 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-7-incheon__main.png) |
| 7호선 | main | 42 | 45.9 | 45.9 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-7__main.png) |
| 8호선 | main | 24 | 29.2 | 29.2 | 1.000 | 0 | 0 | 0 | 0 | 1 | [png](lines/seoul-8__main.png) |
| 9호선 | main | 38 | 37.0 | 37.0 | 1.000 | 0 | 0 | 0 | 0 | 13 | [png](lines/seoul-9__main.png) |
| 2호선 성수지선 | main | 5 | 5.0 | 5.0 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-2-seongsu__main.png) |
| 2호선 신정지선 | main | 5 | 5.4 | 5.4 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/seoul-2-sinjeong__main.png) |
| 부산 1호선 | main | 40 | 37.7 | 37.7 | 1.000 | 0 | 2 | 0 | 0 | 0 | [png](lines/busan-1__main.png) |
| 부산 2호선 | main | 43 | 43.3 | 43.3 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/busan-2__main.png) |
| 부산 3호선 | main | 17 | 17.1 | 17.1 | 1.000 | 0 | 2 | 0 | 0 | 0 | [png](lines/busan-3__main.png) |
| 대구 1호선 | main | 35 | 36.7 | 36.7 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/daegu-1__main.png) |
| 대구 2호선 | main | 29 | 30.1 | 30.1 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/daegu-2__main.png) |
| 대구 3호선 | main | 30 | 22.4 | 22.4 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/daegu-3__main.png) |
| 인천 1호선 | main | 33 | 34.7 | 34.7 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/incheon-1__main.png) |
| 인천 2호선 | main | 27 | 27.9 | 27.9 | 1.000 | 0 | 0 | 0 | 0 | 1 | [png](lines/incheon-2__main.png) |
| 광주 1호선 | main | 20 | 19.8 | 19.8 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/gwangju-1__main.png) |
| 대전 1호선 | main | 22 | 19.7 | 19.7 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/daejeon-1__main.png) |
| GTX-A | north | 5 | 30.7 | 30.7 | 1.000 | 0 | 0 | 0 | 0 | 0 | [png](lines/gtx-a__north.png) |
| GTX-A | south | 4 | 32.1 | 32.1 | 1.000 | 0 | 1 | 0 | 0 | 1 | [png](lines/gtx-a__south.png) |

## 의심 엣지 상세

기하 또는 Wikidata 중 하나라도 걸린 엣지. '둘 다'가 보정 후보.
not_adjacent_weak = 한쪽 역의 Wikidata 아이템이 시퀀스 이웃 누구와도 P197 인접이 아님 (그 노선용 아이템이 없을 가능성이 크지만 순서 오류일 수도 있음).

| 노선 | 시퀀스 | A | B | 거리(m) | 기하 | Wikidata | 둘 다 |
| :- | :- | :- | :- | -: | :- | :- | :- |
| daegyeong | main | 왜관역 | 서대구역 | 17553 | - | not_adjacent | - |
| suin-bundang | main | 매교역 | 수원역(분당) | 1380 | - | not_adjacent_weak | - |
| suin-bundang-suin | main | 수원역(분당) | 고색역 | 2505 | - | not_adjacent_weak | - |
| suin-bundang-suin | main | 송도역 | 인하대역 | 2095 | - | not_adjacent | - |
| uijeongbu | main | 발곡 | 회룡 | 578 | - | not_adjacent_weak | - |
| uijeongbu | main | 회룡 | 범골 | 490 | - | not_adjacent_weak | - |
| busan-gimhae | main | 사상 | 괘법르네시떼 | 758 | - | not_adjacent_weak | - |
| busan-gimhae | main | 등구 | 대저 | 1902 | - | not_adjacent_weak | - |
| busan-gimhae | main | 대저 | 평강 | 892 | - | not_adjacent_weak | - |
| seoul-6 | eungam-loop | 응암 | 역촌 | 1043 | backtrack@응암 | adjacent | - |
| seoul-6 | eungam-loop | 구산 | 응암 | 1409 | backtrack@응암 | adjacent | - |
| busan-1 | main | 연산 | 교대 | 1091 | - | not_adjacent | - |
| busan-1 | main | 교대 | 동래 | 1091 | - | not_adjacent | - |
| busan-3 | main | 연산 | 거제 | 736 | - | not_adjacent_weak | - |
| busan-3 | main | 거제 | 종합운동장 | 656 | - | not_adjacent_weak | - |
| gtx-a | south | 구성역 | 동탄역 | 10992 | - | not_adjacent_weak | - |

## Wikidata에는 인접인데 시퀀스에서 비연속인 쌍

같은 시퀀스 안에 둘 다 있고, 우리 그래프 어떤 노선에서도 이웃이 아닌데 Wikidata P197은 인접이라고 하는 쌍.

| 노선 | 시퀀스 | A (위치) | B (위치) | 거리(m) |
| :- | :- | :- | :- | -: |
| seoul-1-gyeongin | main | 구로역 (0) | 개봉역 (2) | 2280 |
| seoul-1-gyeongin | main | 개봉역 (2) | 역곡역 (5) | 4271 |
| seoul-1-gyeongin | main | 역곡역 (5) | 부천역 (7) | 2548 |
| seoul-1-gyeongin | main | 소사역 (6) | 중동역 (8) | 2785 |
| seoul-1-gyeongin | main | 부천역 (7) | 송내역 (9) | 2653 |
| seoul-1-gyeongin | main | 송내역 (9) | 부평역 (11) | 2519 |
| seoul-1-gyeongin | main | 부평역 (11) | 동암역 (13) | 2812 |
| seoul-1-gyeongin | main | 동암역 (13) | 주안역 (15) | 2072 |
| seoul-1-gyeongin | main | 주안역 (15) | 동인천역 (19) | 4399 |
| donghae | main | 남창역 (18) | 덕하역 (20) | 8475 |
| daegyeong | main | 구미역 (0) | 왜관역 (3) | 16403 |
| daegyeong | main | 구미역 (0) | 대구역 (5) | 36815 |
| daegyeong | main | 왜관역 (3) | 대구역 (5) | 21825 |
| daegyeong | main | 서대구역 (4) | 동대구역 (6) | 7994 |
| arex | main | 청라국제도시 (8) | 운서 (10) | 13554 |
| suin-bundang | main | 오리역 (22) | 보정역 (24) | 3013 |
| suin-bundang-suin | main | 중앙역 (7) | 초지역 (9) | 2907 |
| suin-bundang-suin | main | 안산역 (10) | 정왕역 (12) | 4907 |
| seoul-1-gyeongbu | main | 서울역 (0) | 용산역 (2) | 2958 |
| seoul-1-gyeongbu | main | 용산역 (2) | 영등포역 (6) | 5297 |
| seoul-1-gyeongbu | main | 노량진역 (3) | 신도림역 (7) | 4460 |
| seoul-1-gyeongbu | main | 영등포역 (6) | 안양역 (14) | 12728 |
| seoul-1-gyeongbu | main | 영등포역 (6) | 수원역 (22) | 28929 |
| seoul-1-gyeongbu | main | 가산디지털단지역 (9) | 금천구청역 (11) | 3050 |
| seoul-1-gyeongbu | main | 금천구청역 (11) | 안양역 (14) | 6487 |
| seoul-1-gyeongbu | main | 안양역 (14) | 금정역 (16) | 3804 |
| seoul-1-gyeongbu | main | 안양역 (14) | 수원역 (22) | 16567 |
| seoul-1-gyeongbu | main | 금정역 (16) | 의왕역 (19) | 5720 |
| seoul-1-gyeongbu | main | 수원역 (22) | 평택역 (32) | 31573 |
| seoul-1-gyeongbu | main | 병점역 (24) | 오산역 (27) | 7437 |
| seoul-1-gyeongbu | main | 오산역 (27) | 서정리역 (30) | 9974 |
| seoul-1-gyeongbu | main | 서정리역 (30) | 평택역 (32) | 7880 |
| seoul-1-gyeongbu | main | 성환역 (33) | 두정역 (35) | 9323 |
| seoul-1-gyeongbu | main | 성환역 (33) | 천안역 (36) | 11862 |
| seoul-1-gyeongbu | main | 아산역 (39) | 배방역 (41) | 4878 |
| seoul-1 | main | 청량리(서울시립대입구) (0) | 서울역 (9) | 6975 |
| seoul-1-gyeongwon | main | 광운대역 (5) | 창동역 (8) | 3520 |
| seoul-1-gyeongwon | main | 창동역 (8) | 도봉산역 (11) | 4052 |
| seoul-1-gyeongwon | main | 도봉산역 (11) | 회룡역 (13) | 3831 |
| seoul-1-gyeongwon | main | 의정부역 (14) | 양주역 (17) | 3954 |
| seoul-1-gyeongwon | main | 양주역 (17) | 덕정역 (19) | 7806 |
| seoul-1-gyeongwon | main | 동두천중앙역 (21) | 동두천역 (23) | 2867 |
| seoul-4-ansan | main | 산본역 (10) | 상록수역 (14) | 8494 |
| seoul-4-ansan | main | 상록수역 (14) | 중앙역 (16) | 2879 |
| seoul-4-ansan | main | 중앙역 (16) | 초지역 (18) | 2907 |
| seoul-4-ansan | main | 안산역 (19) | 정왕역 (21) | 4907 |
| gyeongui-jungang | main | 임진강역 (0) | 문산역 (2) | 5189 |
| gyeongui-jungang | main | 문산역 (2) | 금촌역 (5) | 9902 |
| gyeongui-jungang | main | 금촌역 (5) | 운정역 (7) | 4569 |
| gyeongui-jungang | main | 운정역 (7) | 일산역 (10) | 4810 |
| gyeongui-jungang | main | 운정역 (7) | 탄현역 (9) | 3523 |
| gyeongui-jungang | main | 일산역 (10) | 백마역 (12) | 3442 |
| gyeongui-jungang | main | 백마역 (12) | 대곡역 (14) | 3281 |
| gyeongui-jungang | main | 대곡역 (14) | 행신역 (16) | 3018 |
| gyeongui-jungang | main | 행신역 (16) | 디지털미디어시티역 (20) | 6972 |
| gyeongui-jungang | main | 행신역 (16) | 홍대입구역 (22) | 10179 |
| gyeongui-jungang | main | 공덕역 (24) | 용산역 (26) | 1810 |
| gyeongui-jungang | main | 이촌역 (27) | 옥수역 (30) | 4437 |
| gyeongui-jungang | main | 옥수역 (30) | 왕십리역 (32) | 2930 |
| gyeongui-jungang | main | 회기역 (34) | 상봉역 (36) | 2553 |
| gyeongui-jungang | main | 상봉역 (36) | 구리역 (39) | 5145 |
| gyeongui-jungang | main | 도농역 (40) | 덕소역 (42) | 4857 |
| gyeongui-jungang | main | 도심역 (43) | 양수역 (46) | 10076 |
| gyeongui-jungang | main | 양수역 (46) | 양평역 (51) | 15543 |
| gyeongui-jungang | main | 양평역 (51) | 용문역 (53) | 9111 |
| gyeongchun | main | 광운대역 (0) | 망우역 (2) | 3731 |
| gyeongchun | cheongnyangni | 회기역 (1) | 상봉역 (3) | 2533 |
| gyeonggang | main | 판교역 (0) | 이매역 (2) | 1406 |
| seohae | main | 일산역 (0) | 백마역 (2) | 3442 |
| seohae | main | 백마역 (2) | 대곡역 (4) | 3266 |
| seoul-8 | main | 복정 (16) | 산성 (18) | 2580 |
| seoul-9 | main | 마곡나루(서울식물원) (4) | 가양 (6) | 2500 |
| seoul-9 | main | 가양 (6) | 염창 (9) | 2341 |
| seoul-9 | main | 염창 (9) | 당산 (12) | 2829 |
| seoul-9 | main | 당산 (12) | 여의도 (14) | 2357 |
| seoul-9 | main | 여의도 (14) | 노량진 (16) | 1729 |
| seoul-9 | main | 노량진 (16) | 동작(현충원) (19) | 3507 |
| seoul-9 | main | 동작(현충원) (19) | 고속터미널 (22) | 2298 |
| seoul-9 | main | 고속터미널 (22) | 신논현 (24) | 1805 |
| seoul-9 | main | 신논현 (24) | 선정릉 (26) | 1825 |
| seoul-9 | main | 선정릉 (26) | 봉은사 (28) | 1519 |
| seoul-9 | main | 종합운동장 (29) | 석촌 (32) | 2733 |
| seoul-9 | main | 석촌 (32) | 올림픽공원(한국체대) (35) | 2400 |
| seoul-9 | main | 올림픽공원(한국체대) (35) | 중앙보훈병원 (37) | 2135 |
| incheon-2 | main | 주안국가산단 (16) | 시민공원 (18) | 1697 |
| gtx-a | south | 수서역 (0) | 동탄역 (3) | 31904 |

## Wikidata 매칭이 안 된 엣지

| 노선 | A | B | 사유 |
| :- | :- | :- | :- |
| arex | 청라국제도시 | 영종 | 후보 없음: 영종 |
| arex | 영종 | 운서 | 후보 없음: 영종 |
