# Phase 0 야간 작업 보고서

- 시작: 2026-11-04T19:40:49Z (UTC, `date` 기록) · 보고서 작성: 2026-11-04T20:15:15Z
- 브랜치: `claude/relaxed-rubin-uc43ep` · draft PR: https://github.com/hajinmo0725-max/metro_portal/pull/1
- 재현: `scripts/build_all.sh` (수집 → 역 → 노선 → 그래프·지표 → 경로 예시 → 웹 데이터 → pytest → node test)

## 요약

- **M0~M6 전부 완료.** GitHub Pages 실제 배포만 남음 (main 머지 + Pages 소스 설정이 필요해서 내가 할 수 없음).
- 데이터는 **레일포털(data.kric.go.kr) 표준데이터를 로그인 없이 자동 수집**했다. data.go.kr 직접 다운로드는 JS 구조라 실패했지만 같은 데이터의 제공 시스템에 공개 다운로드 URL이 있었다. 그래서 OSM 대체는 필요 없었다.
- **Overpass는 끝까지 접근 불가** (TLS 리셋, 마지막 재시도는 502). 노선 순서는 OSM 대신 표준데이터 노선정보의 '정거장구성'을 쓰고, 깨진 20개 노선은 `config/kr_lines.yaml`로 보정했다.
- strict(T1, D=500m): 역 1097 / 물리적 역 941 / 승차 엣지 1060 / **T1 포탈 28개**. 워프를 켜면 전국이 컴포넌트 1개(100%), 끄면 5개(수도권 69.8%).
- **강남 → 교대 ⇢ 부산 교대 → 동래 = 비용 3** 으로 밈이 그대로 나온다. 예시 3개 모두 워프 없이는 연결 안 됨.
- 테스트: pytest **82 passed**, node **7 passed**, GitHub Actions CI **success**. 산출물은 2회 실행 md5 동일(결정성 확인).

## 1. 단계별 완료 증거

### M0 — 레포 구조·ruleset·hook·네트워크 점검

- `docs/DESIGN.md` 이동, CLAUDE.md 프로젝트명 `metro_portal`, DESIGN 9장 구조, `.gitignore`(data/raw 무시, data/raw/manual 추적), `requirements.txt`
- SessionStart hook: `.claude/settings.json` → `scripts/install_pkgs.sh` (`CLAUDE_CODE_REMOTE=true`일 때만 설치). 로컬 분기(즉시 exit 0)와 원격 분기 둘 다 실행 확인
- `config/rulesets/strict.yaml`: T1만 활성, `transfer_distance_m: 500`
- 네트워크 점검 (`scripts/network_check.sh`, 상세 해석은 `docs/reports/network_check.md`):

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

- `x-deny-reason`은 전부 비어 있다. 403이 프록시 CONNECT 단계에서 나서 curl이 응답 헤더를 못 받기 때문이다. 프록시 상태 엔드포인트에는 `connect_rejected (policy denial or upstream failure)`로 찍혔다.
- 추가로 찍어 본 호스트: `data.kric.go.kr` 200 (M1에서 사용), `raw.githubusercontent.com` 301, `ko.wikipedia.org` 403, `api.openstreetmap.org` 403

### M1 — 한국 역 데이터

- 수집: `pipeline/01_fetch_kr_sources.py` → 레일포털 공개 다운로드 3종 (역사정보 id=32, 노선정보 id=18, 다국어 역사정보 id=1294). 기준일 2026-06-30 / 2026-07-01
- 정제: `pipeline/02_build_kr_stations.py` → `data/processed/kr/stations.json`
- 결과: **1097역** (노선별 역 단위), 노선 그룹 51개, 좌표 누락 0, 한반도 범위 밖 0
- 이름 수: ko-Hang 1431 (부역명 포함), en 1301, 한자(ko-Hani) 1097, ja 1038, zh-Hans 1063, zh-Hant 556, 로마자 468
- 중복 행 2건 제거 (경인선 주안역 중복, 7호선 0736 이수/총신대입구(이수))
- 좌표 보정 3건 (`config/kr_station_fixes.yaml`): 양원(영동선 양원역 좌표가 들어가 190km 오차), 5호선 마곡(발산 좌표 복사), 4호선 이촌(신용산 좌표 복사)
- 다국어 파일은 부산 1호선 좌표가 최대 24km 뒤섞여 있어 좌표는 쓰지 않고 이름만 보강했다.

### M2 — 노선별 정차 순서·승차 엣지

- `pipeline/03_build_kr_lines.py` → `lines.json`, `ride_edges.json`, `docs/reports/m2_lines_validation.md`
- **노선 46 / 시퀀스 50 (지선 분리 4: 5호선 마천지선, 경부선 광명·서동탄, 경의중앙 서울역) / 승차 엣지 1060**
- 정차역 매칭 실패 **0**, 시퀀스 미편입 역 **1** (경의중앙선 그룹의 광운대 레코드, 1호선 광운대와 환승 클러스터로 연결됨)
- 인접역 거리 이상치 21건: 전부 실제 장거리 구간으로 판단 (공항철도 청라~영종 10km, 대경선 왜관~서대구 17.6km 등). 미설명 이상치 0
- 노선 보정 20건: 경의·중앙선 전체 재구성(용산~회기 누락, 가좌·효창 순서 꼬임), 수인선 공용구간 삽입, 분당선 노선번호 오기, 경인선 구로·분당선 왕십리 등 직결 분기점 연결, 2호선 순환, 8호선 별내 연장, 인천1호선 검단 연장 등. 목록은 M2 리포트 5장

### M3 — 정규화·환승 클러스터·T1 포탈

- `metro_portal/normalize.py`, `metro_portal/graph.py`. 룰 값은 전부 `config/rulesets/strict.yaml`에서 읽는다
- 정규화: NFKC → 공백 정리 → 가운뎃점 9종 통일(·‧・．.∙•ㆍ) → 괄호 부역명 제거 → 접미사 '역' 제거
- 클러스터: 정규화 이름 같고 거리 ≤ D. 옵션으로 괄호 부역명 별칭(총신대입구(이수) ↔ 이수)과 데이터 별칭(자기부상 인천국제공항역 ↔ 공항철도 인천공항1터미널)
- CLAUDE.md 필수 엣지 케이스 테스트: 괄호 부역명(`test_parenthetical_subname_transfer`, `test_normalize[교대(법원·검찰청)-교대]`), 같은 이름 환승역(`test_same_name_transfer_station_is_one_cluster`), 같은 권역 동명이역(`test_same_region_homonym_is_portal_not_transfer`, `test_yangpyeong_two_clusters_and_portal`), 부분 일치 금지(`test_no_partial_match`, `test_incheon_city_hall_not_in_city_hall_portal`)
- pytest 출력 (전체는 `docs/reports/evidence/pytest_final.txt`):

```
tests/test_clusters_portals.py::test_same_name_transfer_station_is_one_cluster PASSED [  1%]
tests/test_clusters_portals.py::test_parenthetical_subname_transfer PASSED [  2%]
tests/test_clusters_portals.py::test_same_region_homonym_is_portal_not_transfer PASSED [  3%]
tests/test_clusters_portals.py::test_no_partial_match PASSED             [  4%]
tests/test_clusters_portals.py::test_city_hall_portal_excludes_incheon PASSED [  6%]
tests/test_clusters_portals.py::test_alias_clusters_but_never_portals PASSED [  7%]
tests/test_clusters_portals.py::test_distance_threshold_from_ruleset PASSED [  8%]
tests/test_clusters_portals.py::test_tier_disabled PASSED                [  9%]
tests/test_clusters_portals.py::test_hub_cap PASSED                      [ 10%]
tests/test_clusters_portals.py::test_subname_and_romanization_not_used_for_t1 PASSED [ 12%]
tests/test_clusters_portals.py::test_deterministic PASSED                [ 13%]
tests/test_clusters_portals.py::test_warp_graph_edges PASSED             [ 14%]
tests/test_clusters_portals.py::test_data_alias_clusters PASSED          [ 15%]
tests/test_lines.py::test_parse_stops_variants PASSED                    [ 17%]
tests/test_lines.py::test_code_key_equivalence[D007-D07] PASSED          [ 18%]
tests/test_lines.py::test_code_key_equivalence[0522-522] PASSED          [ 19%]
tests/test_lines.py::test_code_key_equivalence[100-0100] PASSED          [ 20%]
tests/test_lines.py::test_code_key_equivalence[P549-p549] PASSED         [ 21%]
tests/test_lines.py::test_code_key_equivalence[211-1-211-1] PASSED       [ 23%]
tests/test_lines.py::test_code_key_distinct PASSED                       [ 24%]
tests/test_lines.py::test_apply_patch_order PASSED                       [ 25%]
tests/test_lines.py::test_resolver_prefers_code_then_name_then_code_only PASSED [ 26%]
tests/test_lines.py::test_m2_validation_regression PASSED                [ 28%]
tests/test_lines.py::test_branches_are_separate_sequences PASSED         [ 29%]
tests/test_normalize.py::test_normalize[\uad50\ub300(\ubc95\uc6d0\xb7\uac80\ucc30\uccad)-\uad50\ub300] PASSED [ 30%]
tests/test_normalize.py::test_normalize[\ud558\ub0a8\uc2dc\uccad(\ub355\ud48d\u2219\uc2e0\uc7a5)-\ud558\ub0a8\uc2dc\uccad] PASSED [ 31%]
tests/test_normalize.py::test_normalize[\uc6a9\uc0b0(\uc11c\ubd80\ubc95\uc6d0\u2024\uac80\ucc30\uccad\uc785\uad6c)-\uc6a9\uc0b0] PASSED [ 32%]
tests/test_normalize.py::test_normalize[\uccad\ub7c9\ub9ac(\uc11c\uc6b8\uc2dc\ub9bd\ub300\uc785\uad6c)-\uccad\ub7c9\ub9ac] PASSED [ 34%]
tests/test_normalize.py::test_normalize[\uc544\ub77c(\ubd81\ubd80\ubc95\uc6d0, \uac80\ucc30\uccad)-\uc544\ub77c] PASSED [ 35%]
tests/test_normalize.py::test_normalize[\uc2e0\ucc3d(\uc21c\ucc9c\ud5a5\ub300)\uc5ed-\uc2e0\ucc3d] PASSED [ 36%]
tests/test_normalize.py::test_normalize[\ud64d\ub300\uc785\uad6c(\uacbd\uc758\uc120)\uc5ed-\ud64d\ub300\uc785\uad6c] PASSED [ 37%]
tests/test_normalize.py::test_normalize[\uc11c\uc6b8\uc5ed-\uc11c\uc6b8] PASSED [ 39%]
tests/test_normalize.py::test_normalize[\uc591\ud3c9\uc5ed-\uc591\ud3c9] PASSED [ 40%]
tests/test_normalize.py::test_normalize[\uad11\uc8fc\uc1a1\uc815\uc5ed-\uad11\uc8fc\uc1a1\uc815] PASSED [ 41%]
tests/test_normalize.py::test_normalize[  \uac15\ub0a8  -\uac15\ub0a8] PASSED [ 42%]
tests/test_normalize.py::test_normalize[\ubd81\uad6c\uccad\n(\ub300\uad6ciM\ubc45\ud06c\ud30c\ud06c)-\ubd81\uad6c\uccad] PASSED [ 43%]
tests/test_normalize.py::test_suffix_not_removed_to_empty PASSED         [ 45%]
tests/test_normalize.py::test_suffix_only_at_end PASSED                  [ 46%]
tests/test_normalize.py::test_middle_dot_variants_unify PASSED           [ 47%]
tests/test_normalize.py::test_fullwidth_parenthesis PASSED               [ 48%]
tests/test_normalize.py::test_unclosed_parenthesis PASSED                [ 50%]
tests/test_normalize.py::test_partial_match_is_not_equal PASSED          [ 51%]
tests/test_normalize.py::test_aliases PASSED                             [ 52%]
tests/test_normalize.py::test_rules_come_from_ruleset PASSED             [ 53%]
tests/test_normalize.py::test_bad_ruleset PASSED                         [ 54%]
tests/test_real_data.py::test_station_ids_unique PASSED                  [ 56%]
tests/test_real_data.py::test_every_station_in_one_cluster PASSED        [ 57%]
tests/test_real_data.py::test_seoul_gyodae_lines_2_3_same_cluster PASSED [ 58%]
tests/test_real_data.py::test_yangpyeong_two_clusters_and_portal PASSED  [ 59%]
tests/test_real_data.py::test_incheon_city_hall_not_in_city_hall_portal PASSED [ 60%]
tests/test_real_data.py::test_isu_alias_cluster PASSED                   [ 62%]
tests/test_real_data.py::test_seoul_station_variants_cluster PASSED      [ 63%]
tests/test_route.py::test_01bfs_matches_dijkstra[0] PASSED               [ 64%]
tests/test_route.py::test_01bfs_matches_dijkstra[1] PASSED               [ 65%]
tests/test_route.py::test_01bfs_matches_dijkstra[2] PASSED               [ 67%]
tests/test_route.py::test_01bfs_matches_dijkstra[3] PASSED               [ 68%]
tests/test_route.py::test_01bfs_matches_dijkstra[4] PASSED               [ 69%]
tests/test_route.py::test_01bfs_matches_dijkstra[5] PASSED               [ 70%]
tests/test_route.py::test_01bfs_matches_dijkstra[6] PASSED               [ 71%]
tests/test_route.py::test_01bfs_matches_dijkstra[7] PASSED               [ 73%]
tests/test_route.py::test_01bfs_matches_dijkstra[8] PASSED               [ 74%]
tests/test_route.py::test_01bfs_matches_dijkstra[9] PASSED               [ 75%]
tests/test_route.py::test_01bfs_matches_dijkstra[10] PASSED              [ 76%]
tests/test_route.py::test_01bfs_matches_dijkstra[11] PASSED              [ 78%]
tests/test_route.py::test_01bfs_matches_dijkstra[12] PASSED              [ 79%]
tests/test_route.py::test_01bfs_matches_dijkstra[13] PASSED              [ 80%]
tests/test_route.py::test_01bfs_matches_dijkstra[14] PASSED              [ 81%]
tests/test_route.py::test_01bfs_matches_dijkstra[15] PASSED              [ 82%]
tests/test_route.py::test_01bfs_matches_dijkstra[16] PASSED              [ 84%]
tests/test_route.py::test_01bfs_matches_dijkstra[17] PASSED              [ 85%]
tests/test_route.py::test_01bfs_matches_dijkstra[18] PASSED              [ 86%]
tests/test_route.py::test_01bfs_matches_dijkstra[19] PASSED              [ 87%]
tests/test_route.py::test_dijkstra_with_weights PASSED                   [ 89%]
tests/test_route.py::test_multi_source_target PASSED                     [ 90%]
tests/test_route.py::test_unreachable PASSED                             [ 91%]
tests/test_route.py::test_warp_cost_once PASSED                          [ 92%]
tests/test_route.py::test_gangnam_to_busan_dongnae_via_gyodae PASSED     [ 93%]
tests/test_route.py::test_examples_reachable_only_with_warp PASSED       [ 95%]
tests/test_route.py::test_route_matches_dijkstra PASSED                  [ 96%]
tests/test_route.py::test_same_city_route_no_warp_needed PASSED          [ 97%]
tests/test_route.py::test_ambiguous_and_city_prefix PASSED               [ 98%]
tests/test_route.py::test_deterministic PASSED                           [100%]
============================== 82 passed in 0.41s ==============================
```

### M4 — 그래프 지표·포탈 목록·후보 판정

`pipeline/04_build_graph.py --ruleset strict` → `docs/reports/graph_strict.md`

| 항목 | 값 |
| :- | -: |
| 역 (노선별 역 레코드) | 1097 |
| 환승 클러스터 (물리적 역) | 941 |
| 2개 이상 레코드를 가진 환승 클러스터 | 135 |
| 노선 / 시퀀스 | 46 / 50 |
| 승차 엣지 | 1060 |
| 포탈 (전체) | 28 |
| 포탈 T1 | 28 |
| 포탈-클러스터 연결 수 | 58 |
| 라우팅 그래프 노드 / 방향 엣지 | 1125 / 2618 |

| | 워프 있음 | 워프 없음 |
| :- | -: | -: |
| 연결 컴포넌트 수 | 1 | 5 |
| 최대 컴포넌트 비율 | 100.0% (941) | 69.8% (657) |
| 최대 컴포넌트 지름 (비용) | 68 (정확) | 71 (정확) |
| 지름 양 끝 | 신창#1 ↔ 연천#1 | 신창#1 ↔ 연천#1 |
| 최대 컴포넌트 평균 최단 비용 | 18.411 | 21.539 |

워프 있음 지름은 최대 컴포넌트가 커져서(여러 도시 합류) 워프 없음 지름과 직접 비교하면 안 된다.

워프가 없으면 고립되는 컴포넌트:

워프 없는 그래프에서 최대 컴포넌트를 뺀 나머지. '워프로 합류' = 워프를 켜면 최대 컴포넌트에 붙는지.

최대 컴포넌트(워프 없음): 657개 클러스터, 지역 {'수도권': 657}

| 크기 | 지역 | 노선 그룹 | 워프로 합류 |
| -: | :- | :- | :- |
| 145 | 부산(145) | I26K6:동해선, L2604:부산 경량도시철도 4호선, L48B1:부산김해경전철, S2601:부산 도시철도 1호선, S2602:부산 도시철도 2호선, S2603:부산 도시철도 3호선 | 예 |
| 97 | 대구(97) | I27K7:대경선, S2701:대구 도시철도 1호선, S2702:대구 도시철도 2호선, S2703:대구 도시철도 3호선 | 예 |
| 22 | 대전(22) | S3001:대전 도시철도 1호선 | 예 |
| 20 | 광주(20) | S2901:광주도시철도 1호선 | 예 |

#### 포탈 전체 목록 (T1 28개)

| 포탈 | 등급 | 비용 | 차수 | 연결 역 (노선) |
| :- | :- | -: | -: | :- |
| 고촌 | T1 | 1 | 2 | 부산 고촌[부산 경량도시철도 4호선]; 수도권 고촌역[김포도시철도] |
| 공항 | T1 | 1 | 2 | 광주 공항[광주도시철도 1호선]; 부산 공항[부산김해경전철] |
| 교대 | T1 | 1 | 3 | 부산 교대[부산 도시철도 1호선]/교대역[동해선]; 대구 교대[대구 도시철도 1호선]; 수도권 교대(법원·검찰청)[2호선]/교대(법원·검찰청)[3호선] |
| 구암 | T1 | 1 | 2 | 대구 구암(과학대보건대입구)[대구 도시철도 3호선]; 대전 구암[대전 도시철도 1호선] |
| 금곡 | T1 | 1 | 2 | 부산 금곡[부산 도시철도 2호선]; 수도권 금곡역[경춘선] |
| 남산 | T1 | 1 | 2 | 부산 남산[부산 도시철도 1호선]; 대구 남산(계명네거리)[대구 도시철도 3호선] |
| 대곡 | T1 | 1 | 2 | 대구 대곡(정부대구청사)[대구 도시철도 1호선]; 수도권 대곡역[경의중앙선]/대곡역[서해선]/대곡역[일산선] |
| 동백 | T1 | 1 | 2 | 부산 동백[부산 도시철도 2호선]; 수도권 동백(용인세브란스)[에버라인] |
| 동천 | T1 | 1 | 2 | 대구 동천[대구 도시철도 3호선]; 수도권 동천[신분당선] |
| 송정 | T1 | 1 | 2 | 부산 송정역[동해선]; 수도권 송정[5호선] |
| 시청 | T1 | 1 | 3 | 부산 시청(연제)[부산 도시철도 1호선]; 대전 시청[대전 도시철도 1호선]; 수도권 시청[1호선]/시청[2호선] |
| 신천 | T1 | 1 | 2 | 대구 신천(경북대입구)[대구 도시철도 1호선]; 수도권 신천역[서해선] |
| 신촌 | T1 | 1 | 2 | 수도권 신촌(지하)[2호선]; 수도권 신촌역[경의중앙선] |
| 신흥 | T1 | 1 | 2 | 대전 신흥[대전 도시철도 1호선]; 수도권 신흥[8호선] |
| 양정 | T1 | 1 | 2 | 부산 양정[부산 도시철도 1호선]; 수도권 양정역[경의중앙선] |
| 양평 | T1 | 1 | 2 | 수도권 양평역[경의중앙선]; 수도권 양평[5호선] |
| 용문 | T1 | 1 | 2 | 대전 용문[대전 도시철도 1호선]; 수도권 용문역[경의중앙선] |
| 용산 | T1 | 1 | 2 | 대구 용산(서부법원․검찰청입구)[대구 도시철도 2호선]; 수도권 용산역[경부선]/용산역[경원선] |
| 운천 | T1 | 1 | 2 | 광주 운천[광주도시철도 1호선]; 수도권 운천역[경의중앙선] |
| 월드컵경기장 | T1 | 1 | 2 | 대전 월드컵경기장[대전 도시철도 1호선]; 수도권 월드컵경기장(성산)[6호선] |
| 종합운동장 | T1 | 1 | 2 | 부산 종합운동장[부산 도시철도 3호선]; 수도권 종합운동장[2호선]/종합운동장[수도권 도시철도 9호선] |
| 좌천 | T1 | 1 | 2 | 부산 좌천[부산 도시철도 1호선]; 부산 좌천역[동해선] |
| 죽전 | T1 | 1 | 2 | 대구 죽전[대구 도시철도 2호선]; 수도권 죽전역[분당선] |
| 중동 | T1 | 1 | 2 | 부산 중동[부산 도시철도 2호선]; 수도권 중동역[경인선] |
| 중앙 | T1 | 1 | 2 | 부산 중앙[부산 도시철도 1호선]; 수도권 중앙역[수인선]/중앙역[안산과천선] |
| 중앙로 | T1 | 1 | 2 | 대구 중앙로[대구 도시철도 1호선]; 대전 중앙로[대전 도시철도 1호선] |
| 증산 | T1 | 1 | 2 | 부산 증산[부산 도시철도 2호선]; 수도권 증산(명지대앞)[6호선] |
| 화정 | T1 | 1 | 2 | 광주 화정[광주도시철도 1호선]; 수도권 화정역[일산선] |

#### 후보 판정

참 = 이 ruleset으로 T1 포탈이 실제로 생성됨. 정규화 이름 완전 일치만 인정하고 부분 일치는 제외한다.

| 후보 | 판정 | 연결 클러스터 (도시: 역[노선]) | 같은 이름이지만 같은 클러스터(환승) | 부분 일치라 제외된 역 |
| :- | :- | :- | :- | :- |
| 교대 | **참** (차수 3) | 부산: 교대[부산 도시철도 1호선]/교대역[동해선]; 대구: 교대[대구 도시철도 1호선]; 수도권: 교대(법원·검찰청)[2호선]/교대(법원·검찰청)[3호선] | 교대#1(2개 레코드), 교대#3(2개 레코드) | 경인교대입구 |
| 시청 | **참** (차수 3) | 부산: 시청(연제)[부산 도시철도 1호선]; 대전: 시청[대전 도시철도 1호선]; 수도권: 시청[1호선]/시청[2호선] | 시청#3(2개 레코드) | 김해시청, 부천시청, 수원시청역, 시청·용인대, 시흥시청역, 의정부시청, 인천시청, 하남시청(덕풍∙신장) |
| 용산 | **참** (차수 2) | 대구: 용산(서부법원․검찰청입구)[대구 도시철도 2호선]; 수도권: 용산역[경부선]/용산역[경원선] | 용산#2(2개 레코드) | 신용산 |
| 송정 | **참** (차수 2) | 부산: 송정역[동해선]; 수도권: 송정[5호선] | - | 광주송정역, 송정공원 |
| 양정 | **참** (차수 2) | 부산: 양정[부산 도시철도 1호선]; 수도권: 양정역[경의중앙선] | - | - |
| 용문 | **참** (차수 2) | 대전: 용문[대전 도시철도 1호선]; 수도권: 용문역[경의중앙선] | - | - |
| 화정 | **참** (차수 2) | 광주: 화정[광주도시철도 1호선]; 수도권: 화정역[일산선] | - | - |
| 중앙 | **참** (차수 2) | 부산: 중앙[부산 도시철도 1호선]; 수도권: 중앙역[수인선]/중앙역[안산과천선] | 중앙#2(2개 레코드) | 가정중앙시장, 광교중앙(아주대), 동두천중앙역, 삼성중앙, 신검단중앙, 용인중앙시장(용인예술과학대), 의정부중앙, 중앙로 … |
| 중동 | **참** (차수 2) | 부산: 중동[부산 도시철도 2호선]; 수도권: 중동역[경인선] | - | 신중동 |
| 신흥 | **참** (차수 2) | 대전: 신흥[대전 도시철도 1호선]; 수도권: 신흥[8호선] | - | - |
| 금곡 | **참** (차수 2) | 부산: 금곡[부산 도시철도 2호선]; 수도권: 금곡역[경춘선] | - | - |
| 양평 | **참** (차수 2) | 수도권: 양평역[경의중앙선]; 수도권: 양평[5호선] | - | - |

### M5 — 길찾기 CLI

- `metro_portal/route.py` (multi-source/target 0-1 BFS, 비용이 0/1이 아니면 Dijkstra 자동 전환), CLI `pipeline/05_route.py 강남 "부산 동래"`
- 같은 이름 역이 여러 개면 오류로 후보를 보여주고 도시 접두어로 고르게 한다 ("부산 동래", "광주 녹동")
- 테스트: 0-1 BFS vs Dijkstra 랜덤 그래프 20개 대조, 실데이터 경로 회귀 7개
- 예시 (`docs/reports/route_examples_strict.md`):

```
목동 → 부산 동래 (워프 허용)
  총비용 12 = 승차 9역 + 워프 3회 (환승 비용 0)
  [5호선] 목동 → 양평 (2역)
    ⇢ 워프 T1 [양평]: 수도권 양평 ⇢ 수도권 양평역
  [경의·중앙선] 양평역 → 용문역 (2역)
    ⇢ 워프 T1 [용문]: 수도권 용문역 ⇢ 대전 용문
  [대전 1호선] 용문 → 시청 (2역)
    ⇢ 워프 T1 [시청]: 대전 시청 ⇢ 부산 시청(연제)
  [부산 1호선] 시청(연제) → 동래 (3역)
```

```
목동 → 부산 동래 (워프 없음)
  연결 안 됨: 목동#1 와 동래#1 는 같은 컴포넌트가 아니다
```

```
강남 → 부산 동래 (워프 허용)
  총비용 3 = 승차 2역 + 워프 1회 (환승 비용 0)
  [2호선] 강남 → 교대(법원·검찰청) (1역)
    ⇢ 워프 T1 [교대]: 수도권 교대(법원·검찰청) ⇢ 부산 교대
  [부산 1호선] 교대 → 동래 (1역)
```

```
강남 → 부산 동래 (워프 없음)
  연결 안 됨: 강남#1 와 동래#1 는 같은 컴포넌트가 아니다
```

```
개화 → 광주 녹동 (워프 허용)
  총비용 15 = 승차 14역 + 워프 1회 (환승 비용 0)
  [9호선] 개화 → 김포공항 (1역)
    환승: 김포공항(서울 도시철도 9호선) → 김포공항역(서해선)
  [서해선] 김포공항역 → 대곡역 (2역)
    환승: 대곡역(서해선) → 대곡역(일산선)
  [3호선 일산선] 대곡역 → 화정역 (1역)
    ⇢ 워프 T1 [화정]: 수도권 화정역 ⇢ 광주 화정
  [광주 1호선] 화정 → 녹동 (10역)
```

```
개화 → 광주 녹동 (워프 없음)
  연결 안 됨: 개화#1 와 녹동#1 는 같은 컴포넌트가 아니다
```

## 2. M6 — 정적 웹 MVP: 완료 (배포만 사용자 조치 필요)

- `web/index.html` + `app.js` + `style.css`: Leaflet 지도에 노선(46개 색), 역(941), 워프 아크(포탈 클러스터 쌍마다 보라색 점선 곡선). 출발·도착은 입력(자동완성) 또는 지도에서 역 클릭. 워프 허용 토글, 예시 버튼, URL 해시 공유(`#from=강남&to=부산 동래`)
- 데이터: `pipeline/06_build_web_data.py` → `web/data/kr_strict.json` (299KB). Python 라우팅 그래프를 인접 리스트 순서까지 그대로 내보낸다
- 경로 로직: `web/route.js` (브라우저·node 공용). **node 테스트 7개 통과, Python 결과 86건(예시 3 + 시드 고정 랜덤 40, 워프 유무)과 비용·경로 노드열까지 일치**

```
ok 1 - JS 길찾기 비용·경로가 Python 결과와 같다
ok 2 - 강남 → 부산 동래 = 교대 워프 1회, 비용 3
ok 3 - 워프 없이는 서울에서 부산에 못 간다
ok 4 - 0-1 BFS와 Dijkstra 비용 일치 (랜덤 쌍)
ok 5 - 경로 구간 묶기: 승차는 노선별로 연속, 워프는 in/out 한 쌍
ok 6 - 데이터 무결성: 엣지 인덱스·포탈 노드
ok 7 - 입력 해석: 도시 접두어, 동명역, 라벨
# tests 7
# pass 7
# fail 0
```

- 브라우저 확인: Playwright로 데스크톱(1280×800)·모바일(390×844) 렌더, 예시 버튼, 워프 끄기, 동명역 오류 메시지까지 동작 확인. 스크린샷 `docs/reports/evidence/m6_desktop.png`, `m6_mobile.png`. 세션에서는 타일 호스트가 막혀 배경 지도가 회색으로 나온다 (사용자 브라우저에서는 정상일 것, 검증 못 함)
- Leaflet 1.9.4는 npm registry에서 받아 `web/vendor/`에 번들 (CDN이 세션에서 막혀 있었고, 배포본도 외부 스크립트 의존이 없어진다)
- 배포 워크플로우 `.github/workflows/pages.yml`: **push는 권한 문제 없이 성공**. main 푸시 때만 돈다. CI 워크플로우 `ci.yml`(pytest + node)은 이 PR에서 이미 success
- **실제 배포가 안 된 이유**: (1) main 머지가 필요한데 금지 조건이라 하지 않았다. (2) 저장소 Settings → Pages → Source를 "GitHub Actions"로 바꿔야 한다 (내 권한으로 확인·변경 못 함)

## 3. 가정·판단

| # | 상황 | 판단 | 근거·영향 |
| -: | :- | :- | :- |
| 1 | data.go.kr 표준데이터 다운로드가 JS XHR 구조, OpenAPI는 키 필요 | 같은 데이터의 제공 시스템인 레일포털 공개 다운로드 URL 사용 | 로그인·키 불필요, 공개 다운로드 버튼과 같은 URL. 헤더 위장 요청은 하지 않았다 (분류기도 거부) |
| 2 | Overpass 접근 불가 | OSM route relation 대신 표준데이터 노선정보 '정거장구성' + 설정 보정으로 순서 생성 | 목표의 "OSM으로 정차 순서" 조건은 대체 경로로 수행. OSM 교차검증은 다음 할 일 |
| 3 | Station 단위 | 표준데이터 1행(노선별 역)을 Station으로, 물리적 역은 StationCluster로 | DESIGN 4장의 Station.노선 목록은 클러스터 수준에서 성립 |
| 4 | Phase 0 범위 | 표준데이터 수록 범위 그대로 (경전철·자기부상 포함, GTX-A 미포함) | DESIGN 10장 기본값. GTX-A는 다국어 파일에만 있음 |
| 5 | 노선 보정 20건 | 작성자 지식으로 순서를 고치고, 인접역 거리 검증으로 확인 | 공식 노선도와 대조하지 않았다 (검증 못 함). 특히 경춘선 광운대-중랑-상봉 구간 |
| 6 | 좌표 오류 3건 | 다국어 파일 좌표로 교체 | 인접역 거리 이상(190km, 7m, 14m)으로 발견 |
| 7 | 이름이 다른 환승역 | 괄호 부역명 별칭 + 데이터 별칭 + 거리 D 조건 | 표준데이터 '환승노선명'은 표기가 제각각이라 안 씀. 품질 점검상 환승 누락 의심 3건(전부 설명 가능) |
| 8 | 별칭은 포탈 매칭에 쓰지 않음 | 부역명·로마자는 T1에서 제외 (ruleset kinds/scripts) | 허브 폭발 방지. 쓰고 싶으면 ruleset 한 줄로 켤 수 있게 둠 |
| 9 | 환승 비용 | DESIGN 기본값 0 유지 | 열린 질문. 0이라 경로에 "불필요한 환승"이 섞여도 비용 차이가 없다 |
| 10 | 워프 비용 모델 | 역→포탈 = 등급 비용, 포탈→역 = 0 방향 엣지 | 워프 1회에 비용이 정확히 1번 붙음 |
| 11 | 지표 수준 | 클러스터(물리적 역) 기준으로 계산 | 노선별 레코드 기준이면 환승역이 중복 집계됨 |
| 12 | 같은 이름 역이 여러 개일 때 CLI 입력 | 오류로 후보를 보여주고 도시 접두어("부산 동래")로 고르게 함 | 임의 선택은 결과를 오해하게 만든다 |
| 13 | 신촌(2호선) vs 신촌(경의중앙) | D=500m 밖이라 포탈로 둠 | DESIGN이 애매한 케이스로 이미 지목. 질문 목록 2번 |
| 14 | 자기부상철도 | 표준데이터에 있어 포함 | 운행 중단 상태로 알고 있음 (검증 못 함). 질문 목록 4번 |
| 15 | YAML 키 `no:` | `line_no:`로 변경 | YAML 1.1에서 `no`가 False로 파싱되는 함정 |
| 16 | 웹 지도 타일 | OSM 표준 타일 + 출처 표기 | 트래픽이 커지면 OSM 타일 정책상 다른 타일로 바꿔야 함 |

DESIGN.md 결정 로그에 같은 내용을 2026-11-05 항목으로 남겼다.

## 4. 네가 결정해야 할 것

1. **GitHub Pages 켜기**: Settings → Pages → Source = GitHub Actions. 그리고 이 PR을 머지할지. 머지하면 `pages.yml`이 배포한다.
2. **신촌 처리**: 2호선 신촌 ↔ 경의중앙 신촌이 지금은 워프(포탈)다. 같은 도시 안 동명역을 워프로 둘지, D를 늘리거나 예외로 환승 처리할지. (양평·신촌처럼 같은 권역 포탈은 지금 2개)
3. **환승 비용 0 vs 1**: 0이면 "환승 많은 경로"와 "환승 적은 경로"가 같은 비용이다. 게임 재미 기준으로 정해 줘.
4. **자기부상철도·경전철 포함 여부**: 표준데이터 범위 그대로 넣었다. 운행 중단 노선은 빼는 게 맞는지.
5. **노선 보정 검수**: `config/kr_lines.yaml` 보정 20건 중 특히 경춘선 광운대-중랑-상봉 연결, 경의중앙 광운대 레코드 제외가 실제 운행과 맞는지.
6. **GTX-A 등 표준데이터 밖 노선**: 다국어 파일에는 GTX-A가 있다. 범위를 "표준데이터 그대로"로 유지할지, 보조 소스로 넣을지.
7. **Overpass 허용**: 네트워크 허용 목록에 overpass-api.de가 있는데 TLS 단계에서 끊긴다. OSM 교차검증을 원하면 환경 네트워크 설정을 다시 봐 줘. 원인은 검증 못 함.
8. **다국어 파일 라이선스**: 레일포털 '전국 도시광역철도 역사정보'의 이용 조건 문구를 확인하지 못했다. 이름 보강에만 쓰는데 괜찮은지.

## 5. 다음 할 일

1. Pages 활성화 후 배포 확인 (모바일 실기기 포함)
2. 위 질문 답에 따라 ruleset 추가: `strict`(현재), `loose`(D 조정, 같은 도시 포탈 예외 등) 두 개로 지표 비교
3. Overpass가 열리면 `pipeline/02b_fetch_osm_routes.py`로 OSM route relation을 받아 노선 순서를 교차검증하고 `kr_lines.yaml` 보정을 줄이기
4. 웹: 포탈 목록 패널(눌러서 지도 이동), 워프 없는 경로와 비교 표시, 다크 모드 지도 타일
5. 게임 모드 첫 실험: "워프 없는 경로 대비 단축 폭이 크고 최적해가 적은" 출발·도착 쌍 자동 추천 (DESIGN 7장 지표). 지금 그래프로 바로 계산 가능
6. Phase 1 준비: T2(한자 이체자) 매칭에 쓸 한자 역명은 이미 1097개 모두 있다

## 부록: 산출물 위치

| 경로 | 내용 |
| :- | :- |
| `data/processed/kr/stations.json` | 역 1097 (이름·좌표·노선·운영기관·출처) |
| `data/processed/kr/lines.json`, `ride_edges.json` | 노선 시퀀스, 승차 엣지 |
| `data/processed/kr/strict/` | clusters, portals, graph, metrics |
| `docs/reports/m2_lines_validation.md` | 노선 검증 리포트 |
| `docs/reports/graph_strict.md` | 그래프 지표·포탈·후보 판정·클러스터 품질 |
| `docs/reports/route_examples_strict.md` | 경로 예시 |
| `docs/reports/network_check.md` | 네트워크 점검 |
| `web/` | 정적 MVP |
