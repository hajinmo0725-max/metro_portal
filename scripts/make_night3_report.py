#!/usr/bin/env python3
# 사용: python3 scripts/make_night3_report.py <작성 시각 UTC>. 표는 생성 리포트에서 잘라 붙인다
"""phase0_night3.md 조립: 서술은 여기 문자열, 표는 생성 리포트·산출물에서 가져온다 (옮겨 적기 오류 방지)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REP = ROOT / "docs" / "reports"
PROC = ROOT / "data" / "processed"
written_at = sys.argv[1]


def section(md_path, start, stop=None):
    txt = (REP / md_path).read_text(encoding="utf-8")
    i = txt.index(start)
    j = txt.index(stop, i + len(start)) if stop else len(txt)
    return txt[i:j].strip()


def demote(s, n=2):
    return re.sub(r"^(#+)", lambda m: m.group(1) + "#" * n, s, flags=re.M)


def jl(p):
    return json.loads((PROC / p).read_text(encoding="utf-8"))


pyt = (REP / "evidence" / "pytest_night3.txt").read_text(encoding="utf-8")
node = (REP / "evidence" / "node_test_night3.txt").read_text(encoding="utf-8")
per_file = {}
for line in pyt.splitlines():
    m = re.match(r"(tests/\S+?)::\S+ (PASSED|FAILED|SKIPPED)", line)
    if m:
        per_file.setdefault(m.group(1), {}).setdefault(m.group(2), 0)
        per_file[m.group(1)][m.group(2)] += 1
py_sum = [l for l in pyt.splitlines() if re.search(r"\d+ passed", l)][-1].strip("= ")
node_ok = [l for l in node.splitlines() if re.match(r"^(ok|not ok) \d+", l)]
node_sum = [l for l in node.splitlines() if re.match(r"^# (tests|pass|fail) ", l)]

aud = jl("kr/transfer_audit.json")
cmpj = jl("kr/night3_compare.json")
chk = jl("kr/lines_check.json")
edges = [e for r in chk["sequences"] for e in r["edges"]]
n_adj = sum(e["wikidata"] == "adjacent" for e in edges)
st_meta = jl("kr/stations.json")["meta"]
pz = jl("puzzles.json")
ns = jl("n_stops_max.json")
ff = jl("fun_facts.json")
m = jl("kr/strict/metrics.json")


def crow(item):
    r = next(x for x in cmpj["rows"] if x["group"] == "그래프 `strict`" and x["item"] == item)
    return r["before"], r["after"]


L = []
A = L.append
A("# Phase 0 야간 작업 3차 보고서 — 한국 데이터 보정 (A1~A7)")
A("")
A(f"- 시작: 2026-11-05T15:19:17Z (UTC, 세션 시작 직후 `date` 기록) · 보고서 작성: {written_at}")
A("- 브랜치: `kr-fixes` (main = PR #1·#2 머지본에서 분기) · PR #3 (base `main`, draft). main push·머지 안 함")
A("- 재현: `scripts/build_all.sh` (수집 → 역 → 노선 → 그래프 → 경로 → 웹 → Wikidata → 검증 → ruleset 비교 → 게임 → fun facts → 환승 감사 → pytest → node). 약 1.5분. 2차 대비 비교: `python3 scripts/compare_night2_night3.py`")
A("- 이번 세션 한정 지시에 따라 '계획 먼저 제시'와 '실행 전 지적'은 이 보고서 기록으로 대체했다 (3·4장).")
A("")
A("## 요약")
A("")
A("- **A1·A2·A3·A4·A6·A7 완료. A5는 미완으로 종료** — Geofabrik이 허용 목록에 있는데도 egress에서 TLS 단계 터널 종료. 시작 8시간(23:19Z)까지 같은 호스트에 간격을 두고 재시도했지만 한 번도 열리지 않아(아래 A5), 지시의 8시간 조항에 따라 그때까지의 결과로 보고서를 확정했다. 우회 없이 파서·판정·보고서 생성 도구와 합성 데이터 테스트까지 준비했다.")
A("- A1 경춘선: 광운대–상봉 직결(본선) + 청량리–회기–중랑–상봉(지선). 실제로 없던 광운대–중랑 엣지 제거.")
A("- A2 응암순환: 단방향 유향 엣지 6개. 대칭을 가정하던 코드 6곳(그래프·클러스터 지표·게임 그래프·퍼즐 쌍 열거·fun facts 쌍 열거·매개 중심성 /2)을 고쳤다. 예: 워프 없이 응암 → 역촌 1수, 역촌 → 응암 4수.")
b, n = crow("T1 포탈 / 포탈 연결")
A(f"- A3 공식 환승 우선: D=500 대비 클러스터가 바뀐 이름은 **부전 하나**(동해선 ↔ 부산 1호선 342m, 표준데이터상 둘 다 일반역 → 분리, 같은 도시 T1 포탈 추가). T1 포탈 {b} → {n}.")
A(f"- A4 좌표 복사: 이름 같음 + 20m 미만 + 공식 환승 아님 = {len(aud['coord_copy']['pairs'])}쌍, 전부 같은 노선 레코드(직결 경계) 또는 정보 불완전. **좌표 복사 의심 0건.** 2차에서 고친 동해선 동래를 원래 좌표로 되돌리면 이 검사가 잡는다(검출력 확인).")
A("- A6 누락 노선: 표준데이터(2026-06-30)에 빠진 개통 노선은 **GTX-A 하나**. 근거 2개(레일포털 다국어 파일 신설일자 + Wikidata P1619)가 맞는 운정중앙–서울역·수서–동탄 9역만 추가. 서울역–수서는 개통 확인 못 해 제외.")
b2, n2 = crow("워프 有 지름 (양 끝)")
A(f"- A7 재생성: 역 1091 → 1100, 클러스터 937 → 941, 승차 엣지 1056 → 1065, 워프 有 지름 {b2.split(' ')[0]} → {n2.split(' ')[0]}. 13정류장 대권거리 1위는 그대로 371.4km, 구간 거리 합 1위는 GTX-A 덕에 63.9km → {ns['with_warp']['track'][0]['value_m'] / 1000:.1f}km.")
A(f"- 테스트: **pytest {py_sum}**, **node {node_sum[1].split()[-1]} pass / {node_sum[2].split()[-1]} fail**. 재빌드 2회 산출물(json·md 39개) md5 동일.")
A("")
A("## 1. 단계별 완료 증거")
A("")
A("### A1 — 경춘선 운행계통 분리 (커밋 `c067678`)")
A("")
A("- `config/kr_lines.yaml` 경춘선: 본선 `광운대 → 상봉 → 망우 → 신내 → … → 춘천`, 지선 `cheongnyangni: 청량리 → 회기 → 중랑 → 상봉`")
A("- 근거: 사용자 지시 + Wikidata P197 (광운대–상봉 인접, 중랑–상봉·중랑–회기 '경춘선' 한정자). 2차 의심 목록 1번")
A("- 결과: 승차 엣지 순증 +2 (광운대–중랑 삭제, 광운대–상봉·청량리–회기·회기–중랑·중랑–상봉 추가). Wikidata 인접 확인 1040 → 1043 (A1 직후), 08 기하 검사에서 경춘선 본선 길이 비율 1.000")
A("- 노선 PNG: `docs/reports/lines/gyeongchun__main.png`, `gyeongchun__cheongnyangni.png` (직접 열어 확인)")
A("")
A("### A2 — 응암순환 단방향 (커밋 `b38af96`)")
A("")
A("- `kr_lines.yaml` 시퀀스 옵션 `directed: true` → 03 단계가 운행 방향 엣지만 만든다. `ride_edges.json`에 `directed: true` 6개 (응암→역촌→불광→독바위→연신내→구산→응암)")
A("- 대칭 가정 점검 결과 (전수):")
A("")
A("| 위치 | 대칭 가정 | 조치 |")
A("| :- | :- | :- |")
A("| `metro_portal/graph.py` build_graph (역 수준 라우팅) | 승차 엣지 양방향 추가 | 유향이면 a→b만 |")
A("| `metro_portal/metrics.py` cluster_graph (지표) | 양방향 추가 | 유향이면 a→b만. 강연결 컴포넌트(Tarjan) 지표 추가, 지름·평균은 순서쌍 기준 명시 |")
A("| `metro_portal/metrics.py` diameter / diameter_station_level | 이미 모든 (s, t) 순서쌍을 계산 | 그대로 (double-sweep 근사는 대칭 전제라 유향이면 하한임을 주석, 현재는 정확값 범위) |")
A("| `metro_portal/game.py` ClusterGraph (퍼즐·13정류장·fun facts) | 양방향 추가 | 유향이면 a→b만. `ride_len`(구간 거리)은 물리 거리라 무향 유지 |")
A("| `pipeline/10_build_game_data.py` 퍼즐 쌍 | `t in range(s+1, C)` (무순서쌍) | 순서쌍 열거 + 같은 두 역의 정·역방향 퍼즐은 하나만 |")
A("| `pipeline/11_fun_facts.py` | `s<t` 열거 9곳, 매개 중심성 `/2` | 순서쌍 열거, `/2` 제거 (비중은 같은 의미) |")
A("| `metro_portal/route.py`, `web/route.js` 길찾기 | 없음 (인접 리스트 그대로) | 변경 불필요. Python 인접 리스트를 웹이 그대로 쓰므로 자동 반영 |")
A("| `web/puzzle.js` buildMoves·clusterDistances | 없음 (내보낸 유향 엣지에서 이동 생성) | 변경 불필요. node 테스트로 고정 |")
A("| `web/app.js` 지도 | - | 단방향 시퀀스 점선 + 방향 툴팁 |")
A("| 13정류장 n_stops | 출발역마다 경로 전수, 쌍 키는 무순서 | 경로 자체가 유향 그래프를 따르므로 그대로 (최댓값만 쌍별로 남김) |")
A("")
A("- 검증: `tests/test_directed.py` 6개 (합성 순환 그래프에서 C→A 불가·지름이 순서쌍 3, 강연결, n_stops 방향, 실데이터 유향 엣지 6개, 응암→역촌 1·역촌→응암 4), node 1개 (퍼즐 이동·길찾기 역방향 불가)")
A("- 역촌 → 응암이 5가 아니라 4인 이유: 역촌→불광, 3호선 불광→연신내, 6호선 연신내→구산→응암 (3호선 병행)")
A("")
A("### A3 — 공식 환승 정보 우선 (커밋 `d134de0`, GTX-A 반영은 `c1cea31`)")
A("")
A("규칙: `metro_portal/transfer.py` + `graph.transfer_decision`, ruleset `strict` `cluster.transfer_rule: official_first`. 상세: `docs/reports/a3_transfer_rules.md`")
A("")
A("- 표준데이터 '환승노선번호'는 대부분 우리 노선번호와 같지만 다른 체계 코드 16종(I41K4=경의중앙, I41K1=분당, S11S1=9호선, S0129=대구 1호선 등)이 섞여 있어 `config/kr_transfer_codes.yaml`에 별칭과 근거(같은 행의 환승노선명 텍스트)를 적었다")
A("- 노선 패밀리(1호선 경부·경인·경원, 2호선 본선·지선, 3호선·일산선, 4호선·안산과천·진접, 경의중앙·경원 그룹 등): 같은 패밀리 레코드끼리는 '환승'이 아니라 같은 역이라 공식 정보가 말할 수 없으므로 거리 D로 판정. 1호선 신설동이 2호선을 본선 코드(S1102)로 적었는데 우리 레코드는 성수지선(S1121)인 경우도 패밀리 확장으로 해결")
A("- 판정 근거별 쌍 수: " + ", ".join(f"{k} {v}" for k, v in sorted(aud["basis_counts"].items())) + "; 역 레코드 공식 정보 상태: " + ", ".join(f"{k} {v}" for k, v in sorted(aud["status_counts"].items())))
A("")
A(demote(section("a3_transfer_rules.md", "## 판정이 바뀐 쌍", "## 거리 판정으로 넘어간"), 1))
A("")
A("판정이 바뀐 쌍 중 서울·수서·신설동은 다른 공식 yes 경로(예: GTX-A 서울역 ↔ 1호선 서울역 ↔ 공항철도)로 전이적으로 묶여 클러스터는 그대로다. 실제로 클러스터가 바뀐 건 부전뿐.")
A("")
A("### A4 — 좌표 복사 전수 점검 (커밋 `d134de0`)")
A("")
A(demote(section("a4_coord_copy.md", "결과:"), 1))
A("")
A("- 논현(신분당선 ↔ 7호선 1.9m): 신분당선 논현은 '환승역'인데 노선 목록이 자기 노선뿐, 7호선 논현은 일반역으로 적혀 있어 공식 관계 불완전 → 거리 D로 환승 처리. 2022년 신분당선 연장으로 생긴 실제 환승역이라 표준데이터 7호선 쪽 환승 표기가 갱신 안 된 것으로 판단 (검증 못 함)")
A("")
import pathlib as _pl
_log = (_pl.Path(__file__).resolve().parent.parent / "docs" / "reports" / "evidence" / "geofabrik_attempts.log").read_text(encoding="utf-8").splitlines()
_tries = sum(int(l.split("시도 ")[1].split("회")[0]) for l in _log)
_open = sum("열림" in l for l in _log)
A("### A5 — OSM 교차검증 (미완, 커밋 `3f46c1d`·`85b8a27`)")
A("")
A("- 시도: `download.geofabrik.de` (환경 허용 목록에 있음). 15:20Z·15:42Z·15:56Z·16:39Z 수동 시도 모두 프록시 CONNECT 200 뒤 TLS ClientHello 직후 egress 터널 종료 (`ws_closed_mid_exchange`, code 1006, 517B 송신·39B 수신). `pipeline/13_validate_osm.py --fetch`도 `ConnectionResetError(104)`")
A(f"- 재시도 (`scripts/retry_geofabrik.sh`, 같은 URL에 1~2분 간격, 위장·미러 없음): {_log[0].split(' ~ ')[0]} ~ {_log[-1].split(' ~ ')[1].split(' ')[0]}, {len(_log)}회차 {_tries}번 시도, 열린 적 {_open}번. 모든 시도가 `curl: (35) Recv failure: Connection reset by peer`. 전체 기록 `docs/reports/evidence/geofabrik_attempts.log`")
A("- 판단: 정책 거부(403)가 아니라 업스트림/egress 실패 증상이고 설정으로 고칠 수 없다. CLAUDE.md 규칙대로 미러·다른 OSM 배포처·다른 경로로 우회하지 않았다. Overpass도 같은 증상(2차와 동일)")
A("- 한 것: `metro_portal/osm.py`(pyosmium 2패스 파서, 정차 순서·좌표·이름), `pipeline/13_validate_osm.py`(이름+거리 매칭 → 우리 엣지별 OSM 판정 '인접 / 같은 노선에 둘 다 있는데 비인접 / 정보 없음', OSM에만 있는 인접은 급행 패턴·근거 2개·OSM만으로 분류, 좌표는 OSM 거리 중앙값 300m 초과 + Wikidata 1km 초과면 수정 후보, `docs/reports/a5_osm_check.md` 자동 생성, 보정 파일은 건드리지 않음), 테스트 3개(합성 .osm 파서 2, 실데이터 2호선으로 만든 합성 OSM에서 두 역 순서를 바꾸면 '비인접 → 의심'으로 잡히는지 1). 파일만 생기면 `python3 pipeline/13_validate_osm.py --fetch`로 바로 돌릴 수 있다")
A("")
A("### A6 — 누락 노선 (커밋 `c1cea31`)")
A("")
A(f"- 상세: `docs/reports/a6_missing_lines.md`. 보충 역 {st_meta['counts'].get('supplemented', 0)}개: " + ", ".join(f"{x['name']}({x['opened']})" for x in st_meta.get("supplemented", [])))
A("- 근거 대조: 다국어 파일 신설일자 2023-06 이후 행 전수(GTX-A 외 전부 표준데이터에 있음), Wikidata P1619 ≥ 2024 한국 역 17개(GTX-A 운정중앙·킨텍스 외 전부 있음, 중부내륙선 2역은 스코프 밖), Wikidata GTX-A 역 P1619·P197, 표준데이터 환승노선명의 'GTX-A' 기재")
A("- 동탄의 신설일자 2016-11-15는 SRT 동탄역 기준이다. GTX-A 동탄 근거는 성남 행 하행거리 22.1km(구성 신설 전 성남→동탄)와 Wikidata 동탄 P81 = GTX-A")
A("- 순서: 레일포털 역번호 X101~X111 (X104 창릉·X107 삼성 결번 = 미개통)과 일치, 역간 직선거리가 다국어 파일 상·하행 선로 거리보다 약간 짧아 정합. Wikidata는 구성–동탄 인접 정보가 없어 '비인접(약)' (구성 2024-06 신설 반영 안 됨)")
A("- 제외(의심 목록): GTX-A 서울역–수서 (2026-05 '하반기 목표' 보도뿐), 창릉·삼성, 위례선(2026-12 예정), 동북선, 신안산선(2028~ 연기 보도), 수인선 학익역")
A("")
A("### A7 — 재생성과 2차 대비 비교 (커밋 `ab3cbe9`)")
A("")
A(demote(section("night3_compare.md", "| 구분 | 항목 |", "## 13정류장 대권거리"), 1))
A("")
A("- 지름이 68 → 67로 줄어든 건 A1(광운대–상봉 직결)·GTX-A 등의 단축 효과이고, 응암순환 단방향은 지름 양 끝(신창 → 연천)에 영향이 없다. 평균 최단 비용 18.37 → 17.77은 GTX-A(장거리 급행 구간)가 크다")
A("- 퍼즐: 쌍 수는 순서쌍이라 약 2배. 선정 104개 중 2차와 (출발, 도착, 최적 비용)이 같은 퍼즐 59개. 데일리 순서는 퍼즐 목록이 바뀌어 달라졌다 (데일리 1번이 바뀜 — 배포 시 기존 사용자의 '오늘의 퍼즐'이 달라진다)")
A(f"- 13정류장 구간 거리 합 1위: {ns['with_warp']['track'][0]['start_label']} → {ns['with_warp']['track'][0]['end_label']} {ns['with_warp']['track'][0]['value_m'] / 1000:.1f}km (공항철도 + GTX-A, 워프 0)")
A(f"- fun facts: 매개 중심성 1위 포탈 교대 → {ff['portal_hubs'][0]['portal']}, 전국 중심역 부산 시청 → {ff['center_with_warp'][0]['station']}")
A("- 결정성: `scripts/build_all.sh`를 두 번 돌려 `data/processed`·`web/data`·`docs/reports`의 json·md 39개 md5가 같음을 확인")
A("")
A("### 테스트 출력")
A("")
A(f"- pytest: `{py_sum}` (전문 `docs/reports/evidence/pytest_night3.txt`)")
A("")
A("| 파일 | passed |")
A("| :- | -: |")
for f_, c in sorted(per_file.items()):
    A(f"| {f_} | {c.get('PASSED', 0)} |")
A("")
A(f"- node (`npm test`): " + ", ".join(x.lstrip("# ") for x in node_sum) + " (전문 `docs/reports/evidence/node_test_night3.txt`)")
A("")
A("```")
A("\n".join(node_ok))
A("```")
A("")
A("## 2. 미완 단계와 사유")
A("")
A("| 단계 | 상태 | 사유 | 남은 일 |")
A("| :- | :- | :- | :- |")
A(f"| A5 OSM 교차검증 | 도구·테스트만, 8시간 조항으로 종료 | `download.geofabrik.de` egress TLS 단계 차단 (허용 목록에는 있음). 23:18Z까지 {_tries}번 재시도 전부 실패. 우회 금지 | 접속이 되는 환경에서 `python3 pipeline/13_validate_osm.py --fetch` 실행 → `docs/reports/a5_osm_check.md` 판정표 검토 |")
A("")
A("## 3. 가정·판단 (이번 세션은 '실행 전 지적' 대신 여기 기록)")
A("")
A("- A1·A2는 지시대로 반영했다. 지시의 전제(경춘선 운행계통, 응암순환 방향)는 Wikidata·기존 기하 검증과 모순이 없었다.")
A("- A3 '정보가 없을 때'의 정의: 해석 못 하는 코드가 있거나, '환승역'인데 노선 목록이 비었거나, 정보 필드 자체가 없는 경우. '일반역'은 완전한 정보(= 환승 없음)로 봤다. 그래서 둘 다 일반역인 부전이 분리됐다.")
A("- A3 같은 노선 패밀리(직결 경계)는 공식 '환승'의 대상이 아니라서 거리 판정으로 넘겼다. 이걸 공식 no로 보면 지축(3호선↔일산선 4m)·광운대·상봉·중랑·용산이 가짜 포탈로 쪼개진다.")
A("- A3 공식 yes는 한쪽만 적어도 인정했다 (표준데이터는 한쪽만 적은 경우가 흔하다: 우이신설 성신여대입구 등). 공식 yes 상한 1500m는 좌표·코드 오류 방어용 임의값이고 현재 데이터에서 상한에 걸린 쌍은 없다.")
A("- A3 union-find라 공식 no인 두 레코드도 제3의 레코드를 거쳐 공식 yes로 이어지면 같은 클러스터가 된다 (신설동 우이신설 ↔ 2호선은 1호선 경유). 환승 동선상 맞다고 판단.")
A("- A6 GTX-A 색상(#9A6292)은 표시용 임의값이다. GTX-A 역 레코드의 공식 환승 정보는 다국어 파일 '환승노선명' 텍스트를 코드로 옮긴 것이라 표준데이터보다 근거가 약하다.")
A("- A6 '개통 확인'은 레일포털(정부 데이터) 신설일자 + Wikidata 개통일 두 근거가 맞을 때로 정했다. 웹 검색은 '미개통/미확인' 판단에만 썼고, 기사 본문은 가져오지 않았다.")
A("- A2 이후 퍼즐·fun facts의 쌍 단위가 무순서 → 순서쌍으로 바뀌어 쌍 수 통계는 2차와 직접 비교하면 안 된다 (비중·평균은 비교 가능).")
A("- 지시 범위 밖이지만 고친 것: requirements.txt에 08 단계용 matplotlib·koreanize-matplotlib가 빠져 있어 추가 (2차 세션은 수동 설치로 돌린 것으로 보임). fun facts의 '같은 도시 포탈' 문장이 하드코딩이라 데이터 기반으로 바꿨다(부전 반영).")
A("- 작업 브랜치: 시스템 지정 브랜치(`claude/sweet-hamilton-t0wy2t`) 대신 사용자 지시대로 `kr-fixes`·`tw-phase1`을 썼다. 지정 브랜치는 건드리지 않았다.")
A("")
A("## 4. 결정하거나 확인할 것")
A("")
A("1. **부전 분리 수용 여부**: 표준데이터는 동해선 부전·부산 1호선 부전 둘 다 '일반역'이다. 2차 보고서는 부전을 '공식 환승역'이라고 썼지만 근거 없이 쓴 표현이었다. 실제 환승 인정 여부를 확인해 주면, 맞으면 공식 정보 예외(데이터 보정)로 다시 묶는다. (검증 못 함)")
A("2. **공식 우선 규칙의 '일반역 = 완전한 정보' 해석**: 이 해석을 바꾸면(일반역도 정보 없음으로 보면) 부전은 다시 묶이고 차이가 사라진다.")
A("3. **GTX-A 추가 확정**과 서울역–수서 개통 여부. 개통됐다면 `config/kr_supplement.yaml`에 한 시퀀스로 합치면 된다.")
A("4. **데일리 퍼즐 순서 변경**: 퍼즐 목록이 바뀌어 같은 날짜의 데일리 퍼즐이 2차와 다르다. 이미 공개 배포 중이면 기존 순서를 고정하는 방식이 필요하다.")
A("5. **Geofabrik 접속**: 환경 허용 목록에는 있는데 TLS 단계에서 끊긴다. 네트워크 쪽 문제라 사용자 쪽에서 확인 필요 (다른 환경에서 받은 .osm.pbf를 `data/raw/osm/`에 두면 13 단계가 바로 돈다. 단 수 백 MB라 레포 커밋 대상은 아님).")
A("6. 논현(7호선) 등 표준데이터 공식 환승 표기 누락 의심 — 공식 정보 오류를 보정 파일로 고칠지, 표준데이터를 그대로 믿을지.")
A("")
A("## 5. 다음 할 일")
A("")
A("- A5: OSM 추출본 확보 후 13 단계 실행 → 근거 2개 일치분만 보정, 나머지 의심 목록")
A("- 부전·논현 등 공식 환승 정보 예외 처리 방식 결정 후 반영")
A("- GTX-A 서울역–수서 개통 확인되면 시퀀스 연결")
A("- 데일리 퍼즐 순서 고정 방식 (예: 이미 지난 날짜의 퍼즐 id를 기록해 두고 새 퍼즐은 뒤에 붙이기)")
A("- Phase 1 타이베이는 PR #4 (`docs/reports/phase1_taipei.md`)")
(REP / "phase0_night3.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"wrote {REP / 'phase0_night3.md'} ({len(L)} lines)")
