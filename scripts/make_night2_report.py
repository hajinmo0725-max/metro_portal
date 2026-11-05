# 사용: python3 scripts/make_night2_report.py <작성 시각 UTC>. 표는 생성 리포트에서 잘라 붙인다
"""phase0_night2.md 조립: 서술은 여기 문자열, 표는 생성 리포트에서 잘라 붙인다 (옮겨 적기 오류 방지)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/user/metro_portal")
REP = ROOT / "docs" / "reports"
written_at = sys.argv[1]


def section(md_path, start, stop=None):
    txt = (REP / md_path).read_text(encoding="utf-8")
    i = txt.index(start)
    j = txt.index(stop, i + len(start)) if stop else len(txt)
    return txt[i:j].strip()


def demote(s, n=1):
    return re.sub(r"^(#+)", lambda m: m.group(1) + "#" * n, s, flags=re.M)


pyt = (REP / "evidence" / "pytest_night2.txt").read_text(encoding="utf-8")
node = (REP / "evidence" / "node_test_night2.txt").read_text(encoding="utf-8")
per_file = {}
for line in pyt.splitlines():
    m = re.match(r"(tests/\S+?)::\S+ (PASSED|FAILED|SKIPPED)", line)
    if m:
        per_file.setdefault(m.group(1), {}).setdefault(m.group(2), 0)
        per_file[m.group(1)][m.group(2)] += 1
summary_line = [l for l in pyt.splitlines() if re.search(r"\d+ passed", l)][-1].strip("= ")
node_ok = [l for l in node.splitlines() if re.match(r"^(ok|not ok) \d+", l)]
node_sum = [l for l in node.splitlines() if re.match(r"^# (tests|pass|fail) ", l)]

pz = json.loads((ROOT / "data" / "processed" / "puzzles.json").read_text(encoding="utf-8"))
st = pz["stats"]
chk = json.loads((ROOT / "data" / "processed" / "kr" / "lines_check.json").read_text(encoding="utf-8"))
edges = [e for r in chk["sequences"] for e in r["edges"]]
n_adj = sum(e["wikidata"] == "adjacent" for e in edges)
n_na = sum(e["wikidata"].startswith("not_adjacent") for e in edges)
n_um = len(edges) - n_adj - n_na


def fmt_steps(steps, start):
    out = [start]
    for x in steps:
        n = x["to"].split("#")[0]
        out.append(f"⇢[{x['portal']}]⇢ {n}" if x["type"] == "warp" else f"→ {n}")
    return " ".join(out)


seen = {}
pz_rows = []
for p in pz["puzzles"]:
    k = (p["kind"], p["difficulty"])
    if seen.get(k, 0) >= 2:
        continue
    seen[k] = seen.get(k, 0) + 1
    pz_rows.append(f"| {p['id']} | {p['kind']} | {p['difficulty']} | {p['from_label']} → {p['to_label']} | {p['cost_warp']} | "
                   f"{p['cost_no_warp'] if p['cost_no_warp'] is not None else '불가'} | {p['warps']} | "
                   f"{fmt_steps(p['optimal'], p['from_label'].split(' ', 1)[1])} |")
from collections import Counter
cnt = Counter((p["kind"], p["difficulty"]) for p in pz["puzzles"])

L = []
A = L.append
A("# Phase 0 야간 작업 2차 보고서")
A("")
A(f"- 시작: 2026-11-05T06:26:30Z (UTC, 세션 시작 직후 `date` 기록) · 보고서 작성: {written_at}")
A("- 브랜치: `claude/inspiring-fermat-n0mp7n` (PR #1 브랜치 `claude/relaxed-rubin-uc43ep`에서 분기)")
A("- draft PR #2: https://github.com/hajinmo0725-max/metro_portal/pull/2 (base = PR #1 브랜치). main push·머지 안 함")
A("- 재현: `scripts/build_all.sh` (수집 → 역 → 노선 → 그래프 → 경로 → 웹 데이터 → Wikidata → 검증 → ruleset 비교 → 게임 데이터 → fun facts → pytest → node test). 전체 약 1.5분")
A("")
A("## 요약")
A("")
A("- **N1~N7 전부 완료.** 막힌 단계 없음. 남은 시간에 N2 의심 목록 재검토와 테스트 보강까지 했다.")
A("- 네트워크: `query.wikidata.org` 정상(200)이라 Wikidata 교차검증을 했다. Overpass(TLS 리셋)·Geofabrik(프록시 거부)은 지시대로 쓰지 않았고 우회 시도도 하지 않았다.")
A("- **노선 수정 1건, 좌표 수정 1건.** 둘 다 독립 근거 2개(좌표 기하 + Wikidata)가 일치한 경우만 고쳤다.")
A("  - 6호선: 응암순환을 순환 지선으로 분리. 원본 순서가 실제로 없는 **구산–새절 엣지**를 만들고 있었다.")
A("  - 동해선 동래: 표준데이터 좌표가 **4호선 동래 좌표 복사(7m)**였다. Wikidata 좌표로 고쳤더니 1·4호선 동래와 분리돼서 같은 도시 포탈 '동래'가 새로 생겼다 (T1 포탈 28 → 29).")
A(f"- Wikidata P197로 승차 엣지 {len(edges)}개 중 **{n_adj}개 인접 확인**. 비인접 {n_na}개 중 12개는 Wikidata 쪽 공백(해당 노선 아이템 없음, 대경선 신규 개통 미반영), 1개는 Wikidata의 학익역(미개통 추정), **1개(경춘선 광운대–중랑)는 우리 쪽 의심**이다. 매칭 불가 {n_um}개(영종역 아이템 없음).")
A("- ruleset 비교: **D=500 유지 추천.** D=300이면 노원·잠실·서울역·부전·벡스코 같은 공식 환승역이 가짜 포탈로 쪼개지고, D=1000이면 신촌 포탈이 사라진다. 환승 비용 1은 포탈 목록을 안 바꾸고 지름만 68→71로 늘린다.")
A(f"- 게임 데이터: 클러스터 쌍 {st['pairs']:,}개 전수 계산, 퍼즐 {len(pz['puzzles'])}개. 13정류장 대권거리 1위 **371.4km** (부산 동백 → 수도권 임진강, 워프 3번).")
A("- 웹: `web/daily.html` 데일리 퍼즐 (서울 시간 날짜 시드, 최적 대비 점수, 🚇/🌀 이모지 복사). Playwright로 데스크톱·모바일 끝까지 플레이해 봤고 콘솔 에러 0.")
A(f"- 테스트: **pytest {summary_line}** (1차 82개 → 128개), **node {node_sum[1].split()[-1]} pass / {node_sum[2].split()[-1]} fail** (1차 7개 → 14개). 전체 빌드 2회 산출물 md5 동일 (결정성).")
A("")
A("## 1. 단계별 완료 증거")
A("")
A("### N1 — 정리 (커밋 `f4cf34b`)")
A("")
A("- CLAUDE.md '실행 환경'에 접근 제한 우회 금지 규칙 추가: 헤더·User-Agent 위장, 브라우저 흉내, 다른 미러·프록시·캐시·번역 서비스 경유 금지. 막히면 호스트·증상 기록 후 보고, 허용된 소스로 할 수 있는 대체 작업만 한다.")
A("- 인천공항 자기부상철도 스코프 제외: `config/kr_scope.yaml`(신규) → `02_build_kr_stations.py`가 역 6개를 빼고 `stations.json` meta에 제외 내역을 남긴다. `kr_lines.yaml`의 해당 노선은 `skip`, 데이터 별칭(인천국제공항역 ↔ 인천공항1터미널)과 장거리 구간 예외도 삭제. 결과: 역 1097 → 1091, 클러스터 941 → 936, 노선 46 → 45")
A("- 환승 비용 1짜리 ruleset `config/rulesets/strict_transfer1.yaml` 추가. ruleset에 `extends`(부모 상속, deep merge) 기능을 넣어서 바뀐 값(`costs.transfer: 1`)만 적는다.")
A("- **발견해서 같이 고친 버그**: 지표 계산이 클러스터 접힘 그래프를 써서 환승 비용을 항상 0으로 취급했다. 환승 비용이 0이 아니면 역 수준 그래프에서 클러스터 multi-source로 지름·평균을 계산하게 바꿨다 (환승 0일 때는 두 방식 값이 같은지 실데이터 테스트로 확인).")
A("- DESIGN.md 결정 로그에 '추천 반영, 사용자 확인 필요'로 기록.")
A("")
A("### N2 — 노선 순서 검증 (커밋 `5eab5de`, 보강 `7460c1e`)")
A("")
A("방법 (`pipeline/08_validate_lines.py`, 임계값 `config/validation.yaml`):")
A("")
A("- (a) 기하: 시퀀스(지선별) 50개마다 현재 순서 길이를 좌표 기반 경로 최적화(최근접 이웃 시작해 여러 개 → 2-opt → or-opt, 순환선은 닫힌 경로)와 비교. 연속 3역 가운데 각도 35° 미만 = 되돌아감, 연속 4역에서 가운데 두 역을 바꾸면 300m 이상·15% 이상 짧아지면 스왑 의심, 최적해에 없는 현재 엣지 표시")
A("- (b) 노선별 PNG 50장 `docs/reports/lines/` (현재 순서, 최적 경로가 다르면 회색 점선, 의심 엣지 색 표시). **50장 전부 직접 열어서 확인했다.**")
A("- (c) Wikidata: `pipeline/07_fetch_wikidata.py`로 P197(인접역)·P625(좌표)·P81(노선)·P296(역번호) 수집 (SPARQL 7회, 요청 간 3초, 캐시, CC0). 역 매칭은 좌표 검증에도 쓰므로 거리보다 '시퀀스 이웃 역과 P197 인접'을 우선한다. 이름 후보가 없을 때만 200m 이내 아이템을 대체 매칭(라벨 차이: 건대입구 ↔ 건국대역 등)하고 그 매칭은 좌표 검사에서 뺀다")
A("")
A("결과:")
A("")
A("| 항목 | 값 |")
A("| :- | -: |")
A("| 시퀀스 | 50 |")
A("| 길이 비율(현재/최적) 1.02 초과 | 0 (보정 전 6호선 1.043) |")
A(f"| 승차 엣지 | {len(edges)} |")
A(f"| Wikidata 인접 확인 | {n_adj} ({n_adj / len(edges):.1%}) |")
A(f"| Wikidata 비인접 | {n_na} (Wikidata 공백 12, 학익역 1, 우리 쪽 의심 1 — 아래 의심 목록) |")
A(f"| Wikidata 매칭 불가 | {n_um} (영종역 아이템 없음) |")
A("| 기하 + Wikidata 둘 다 걸린 엣지 | 보정 전 1 (6호선 구산–새절) → 보정 후 0 |")
A("| 기하만 걸린 엣지 | 2 (응암순환 안쪽 각도, 실제 순환 형태라 정상) |")
A("| Wikidata에는 인접인데 시퀀스에서 비연속 | 85 (급행 정차·신설역 이전 정보. 기하로는 전부 정상) |")
A("")
A("Wikidata 매칭 방법별 역 레코드 수: " + ", ".join(f"{k} {v}" for k, v in chk["match_stats"].items()))
A("")
A("**수정 목록 (`config/kr_lines.yaml`)**")
A("")
A("| 노선 | 수정 | 근거 1 (기하) | 근거 2 (Wikidata) |")
A("| :- | :- | :- | :- |")
A("| 6호선 | 응암·역촌·불광·독바위·연신내·구산을 순환 지선 `eungam-loop`로 분리, 본선은 응암 → 새절 → … → 신내 | 구산–새절 엣지가 최적 경로에 없음, 노선 길이 비율 1.043 | 구산–새절 비인접, 응암–구산·응암–새절 인접 |")
A("")
A("**의심 목록 (수정 안 함)**")
A("")
A("| # | 대상 | 증상 | 판단 |")
A("| -: | :- | :- | :- |")
A("| 1 | 경춘선 광운대–중랑 | Wikidata는 광운대–상봉 인접, 중랑–상봉·중랑–회기를 '경춘선' 한정자로 기록. 광운대–중랑은 비인접 | 1차 세션이 원본 순서 없이 추정으로 넣은 연결. 광운대발 열차는 상봉 직결이고 중랑은 청량리발 계통이라는 해석이 맞아 보이지만 근거가 Wikidata 하나뿐이고 기하는 중립(오히려 현재 쪽이 짧음). 확인되면 `광운대–상봉` 지선으로 바꾸는 걸 추천 |")
A("| 2 | 수인선 송도–인하대 | Wikidata는 사이에 학익역을 둠 | 표준데이터(2026-06-30)에 학익역 없음. 미개통 신설역으로 추정 (검증 못 함) |")
A("| 3 | 6호선 응암순환 방향 | 실제는 단방향 순환 | 그래프는 무방향이라 역방향 이동도 허용된다. 게임에서 문제 되면 방향 엣지 지원 필요 |")
A("| 4 | 대경선 왜관–서대구 | Wikidata 비인접 | 대경선(2024 개통) 정보가 Wikidata에 아직 반영 안 됨. 표준데이터 순서·기하 정상 |")
A("| 5 | 분당선 매교–수원, 수인선 수원–고색 | 비인접(약) | Wikidata 수원역 아이템에 경부선 인접만 있음. 데이터 공백 |")
A("| 6 | 의정부경전철 발곡–회룡–범골 | 비인접(약) | Wikidata 회룡역 아이템이 1호선용뿐. 데이터 공백 |")
A("| 7 | 부산김해경전철 사상–괘법르네시떼, 등구–대저–평강 | 비인접(약) | 사상·대저 아이템이 도시철도용뿐. 데이터 공백 |")
A("| 8 | 부산 1호선 연산–교대–동래 | 비인접 | Wikidata에 부산 1호선 교대 아이템이 없고 동해선 교대만 있음 |")
A("| 9 | 부산 3호선 연산–거제–종합운동장 | 비인접(약) | 거제 아이템이 동해선용뿐 |")
A("")
A("PNG 육안 확인 결과: 순서가 꼬여 보이는 노선은 보정 전 6호선뿐이었다. 동해선은 보정 전 4번 동래역이 북서쪽으로 튀어나와 있었다(→ N3에서 수정). 경춘선 시작부 광운대–중랑 구간은 위 의심 1번. 범례가 역 라벨을 가리던 문제(8호선 별내, 서해선 일산)는 범례를 축 아래로 옮겨 고쳤다.")
A("")
A("### N3 — 좌표 검증 (커밋 `5eab5de`)")
A("")
A("- 노선 내 스파이크(이웃 두 역과 모두 3km 이상, 이웃끼리 거리의 2.5배 이상): 1건(경춘선 광운대 끝점 3.4km vs 다음 구간 0.86km) → N2 의심 1번과 같은 구간. 좌표 자체는 다국어 파일·Wikidata와 일치해서 좌표 문제는 아님")
A("- 다른 클러스터인데 30m 이내 좌표: 0건")
A("- 검출력 확인: 1차 세션에서 고친 좌표 3건을 원래 값으로 되돌려 돌리면 **전부 잡힌다** — 양원(190km, 스파이크 + Wikidata 둘 다), 마곡(발산과 7m)·이촌(신용산과 14m)은 근접 중복 검사")
A("- **동해선 동래 수정** (`config/kr_station_fixes.yaml`): 표준데이터 좌표가 4호선 동래와 7m(복사 패턴). Wikidata 좌표는 1.4km 동남쪽(4호선 낙민역에서 303m)이고, 그 좌표면 이웃 교대 1037m·안락 1021m로 노선이 매끄럽다(기존 1230m·2362m로 북서쪽으로 튐). Wikidata 원문이 `Point(129.09 35.1976)`이라 경도 정밀도는 0.01°(약 ±450m)")
A("- 그 결과 길찾기에서 '부산 동래'가 두 곳이 돼서, **도시 접두어까지 줬는데 같은 도시에 같은 이름이 여럿이면 전부를 출발/도착 후보로 쓰게** Python·JS 둘 다 바꿨다. 밈 경로 강남 → 부산 동래는 그대로 3수")
A("- Wikidata 좌표와 1km 넘게 다른 나머지 8건은 **Wikidata 쪽 오류로 판정**: 원흥·서동·등구는 Wikidata 좌표가 이웃역(원당·명장·덕두) 좌표와 10m 이내(복사), 신갈은 Wikidata 좌표가 북쪽으로 3.3km 떨어져 있어 이웃 기흥과 4.5km가 된다(우리 좌표 = 다국어 파일 좌표), 경춘선 4역(가평·굴봉산·백양리·강촌)은 우리 좌표 = 다국어 파일 좌표이고 Wikidata는 2010년 복선전철 이전 옛 역 위치로 보임(검증 못 함)")
A("")
A(demote(section("n3_coords_check.md", "## 2. Wikidata 좌표", "## 3."), 1).replace("### 2. Wikidata 좌표(P625)와 비교", "#### Wikidata 좌표(P625)와 1km 넘게 다른 역 (전부 Wikidata 쪽 오류로 판정)"))
A("")
A("### N4 — ruleset 비교 (커밋 `62d3d6e`)")
A("")
A("`config/ruleset_grid.yaml` (base strict, 환승 0/1 × D 300/500/1000) → `pipeline/09_compare_rulesets.py` → `docs/reports/n4_ruleset_compare.md`")
A("")
A(demote(section("n4_ruleset_compare.md", "## 1. 그래프 지표", "지름 양 끝"), 2).replace("#### 1. 그래프 지표", "#### 그래프 지표"))
A("")
A(demote(section("n4_ruleset_compare.md", "## 2. 포탈 목록 차이", "## 3."), 2).replace("#### 2. 포탈", "#### 포탈"))
A("")
A(demote(section("n4_ruleset_compare.md", "## 4. D에 따라", None), 2).replace("#### 4. D에", "#### D에"))
A("")
A("해석: 노원(4·7호선 306m)·잠실(2·8호선 394m)·서울역(1·4호선·공항철도·경의중앙)·부전·벡스코는 실제 환승역이라 D=300은 틀린 설정이다. 신촌(2호선 ↔ 경의중앙 701m)은 공식 환승역이 아니라서 D=500(포탈)이 맞다고 본다. 환승 비용은 포탈을 안 바꾸고 비용만 늘린다(지름 +3, 평균 +2.1). 지름 양 끝은 모든 조합에서 신창 ↔ 연천.")
A("")
A("### N5 — 게임 데이터 사전 계산 (커밋 `6063c57`, `72e7e38`에서 최대 24수 제한)")
A("")
A("`pipeline/10_build_game_data.py` + `config/game.yaml`. 클러스터(물리적 역) 수준, 환승 0으로 접힌 그래프.")
A("")
A("**(a) 최단 루트 퍼즐** → `data/processed/puzzles.json` (웹용 축약본 `web/data/puzzles.json`)")
A("")
A("| 항목 | 값 |")
A("| :- | -: |")
for k in ("pairs", "pairs_reachable_without_warp", "pairs_warp_shortens", "pairs_cross_component", "pairs_unique_optimum",
          "candidates_shortcut", "candidates_crosscity"):
    A(f"| {k} | {st[k]:,} |")
A("| 최적 경로 개수 분포 (10 = 10개 이상) | " + ", ".join(f"{k}: {v:,}" for k, v in st["optimal_count_hist"].items()) + " |")
A("")
A("- 최적 경로 개수 = 물리적 역 순서(+워프)가 다른 최단 경로 수. 같은 두 역 사이를 다른 노선으로 가는 건 같은 경로로 셌다. 작은 랜덤 그래프 12개에서 전수 열거와 일치하는지 테스트로 확인")
A("- 선정: 최적해 유일 + (같은 권역이면 워프 단축 3수 이상, 단축 폭 큰 순) 또는 (워프 없이 못 가는 도시 횡단, 워프 수·비용 큰 순). 출발·도착 이름이 같은 쌍(양평→양평)과 3수 미만·25수 이상은 제외. 같은 워프 조합은 등급마다 3개, 같은 역은 전체 2번까지")
A("- 난이도: easy = 워프 1번 이하·8수 이하, normal = 워프 2번 이하·14수 이하, hard = 나머지")
A("- 선정 결과: " + ", ".join(f"{k[0]}/{k[1]} {v}" for k, v in sorted(cnt.items())) + f" (총 {len(pz['puzzles'])}개). shortcut easy가 6개뿐인 건 워프 1번으로 크게 줄어드는 같은 권역 쌍이 양평·좌천 포탈 정도밖에 없어서다")
A("")
A("등급별 예시 (각 2개, 전체 목록은 `docs/reports/n5_game_data.md`):")
A("")
A("| id | 종류 | 난이도 | 출발 → 도착 | 워프 有 | 워프 無 | 워프 | 최적 경로 (유일) |")
A("| :- | :- | :- | :- | -: | -: | -: | :- |")
L.extend(pz_rows)
A("")
A("**(b) 13정류장 최대 거리** → `data/processed/n_stops_max.json`")
A("")
A("정의(잠정): 정확히 13턴, 승차 1역 = 1턴, 워프 1번 = 1턴, 환승은 턴 아님, 같은 물리적 역 재방문 금지. 구간 거리는 인접역 좌표 직선거리 합(실제 선로 길이 아님). 전 출발역에서 단순 경로를 전수 탐색했다 (약 10초).")
A("")
A(demote(section("n5_game_data.md", "### 시작-끝 대권거리 최대", "### 탑승 구간 거리 합 최대"), 1))
A("")
A(demote(section("n5_game_data.md", "### 탑승 구간 거리 합 최대", None), 1))
A("")
A("구간 거리 합 상위는 거의 워프 0번이다. 워프는 턴을 쓰는데 탑승 거리는 0이라 손해고, 경강선·경춘선 장거리 구간이 그냥 길다.")
A("")
A("### 테스트 출력")
A("")
A("pytest (`docs/reports/evidence/pytest_night2.txt`, 파일별 통과 수):")
A("")
A("| 파일 | 통과 | 실패 |")
A("| :- | -: | -: |")
for f, d in sorted(per_file.items()):
    A(f"| {f} | {d.get('PASSED', 0)} | {d.get('FAILED', 0)} |")
A("")
A("```")
A(summary_line)
A("```")
A("")
A("이번 세션 신규 테스트 파일: `test_ruleset_scope.py`(extends·스코프 제외·환승 비용 반영 지름·D 경계 사례·비교표 일관성), `test_lineval.py`(2-opt·급반전·스왑·스파이크·Wikidata 매칭·6호선/동래 회귀), `test_game_data.py`(경로 개수 브루트포스 대조·N정류장·퍼즐 비용 대조·Brandes 대조·fun facts 일관성). 기존 `test_route.py`는 동래 분리 후에도 그대로 통과.")
A("")
A("node (`docs/reports/evidence/node_test_night2.txt`):")
A("")
A("```")
L.extend(node_ok)
L.extend(node_sum)
A("```")
A("")
A("## 2. N6·N7")
A("")
A("### N6 데일리 퍼즐 웹 — 완료 (커밋 `72e7e38`)")
A("")
A("- `web/daily.html` + `daily.js`(화면) + `puzzle.js`(로직, node 테스트 대상). 메인 페이지에서 '오늘의 퍼즐' 링크")
A("- 서울 시간 날짜 → `daily_order`(시드 고정 셔플) 순환. 1회차 = 2026-11-05. `daily.html#d=YYYY-MM-DD`로 다른 날 퍼즐")
A("- 한 수 = 인접역 승차 1개 또는 같은 이름 역으로 워프 1번(환승은 공짜). 지도에서 갈 수 있는 역을 눌러도 되고 목록 버튼을 눌러도 된다. 되돌리기, 포기, 최적의 3배+10수 넘으면 자동 종료")
A("- 점수 = 최적 수 / 내 수 × 100, 메달 💯/🥇/🥈/🥉. 완료하면 최적 경로(유일해)를 지도와 글로 공개. 결과 복사(클립보드, 실패 시 textarea 폴백). 진행 상황은 날짜별 localStorage (막혀 있으면 생략)")
A("- 공유 텍스트 예 (2026-11-05 퍼즐):")
A("")
A("```")
A("지하철 워프 데일리 #1 (보통)")
A("수도권 부개 → 수도권 삼가")
A("🚇🚇🌀🚇🚇🌀🚇🚇 8수 / 최적 8수 💯 100점")
A("워프 없으면 36수")
A("```")
A("")
A("- 검증: node 테스트 7개(날짜 경계, 주기 중복 없음, 퍼즐 101개 비용을 route.js 길찾기와 전수 대조, 100점 경로, 감점, 수 제한). Playwright E2E(`scripts/e2e_daily.cjs`)로 데스크톱 1280×800·모바일 390×844에서 헛걸음 → 되돌리기 → 최적 경로 완주 → 새로고침 후 결과 유지 → 다른 날짜 포기까지 확인, 콘솔 에러 0 (`docs/reports/evidence/n6_browser.txt`). 스크린샷: `docs/reports/evidence/daily_start_desktop.png`, `daily_done_desktop.png`, `daily_done_mobile.png` (세션에서 지도 타일 호스트가 막혀 배경이 회색)")
A("")
A("### N7 fun facts — 완료 (커밋 `c0a73ad`)")
A("")
A("`docs/reports/fun_facts.md` (`pipeline/11_fun_facts.py`). 주요 소재:")
A("")
ff = json.loads((ROOT / "data" / "processed" / "fun_facts.json").read_text(encoding="utf-8"))
d = ff["diameter"]
A(f"- 그래프 지름: **{d['from']} → {d['to']} {d['cost']}수**인데 최단 경로가 부산을 찍고 온다 (워프 없이 {d['cost_no_warp']}수)")
h = ff["portal_hubs"]
A(f"- 포탈 허브(매개 중심성, 가중 Brandes): 1위 {h[0]['portal']} {h[0]['betweenness_share']:.1%}, 2위 {h[1]['portal']} {h[1]['betweenness_share']:.1%}, 3위 {h[2]['portal']} {h[2]['betweenness_share']:.1%}. 꼴찌 {h[-1]['portal']} {h[-1]['betweenness_share']:.2%}")
x = ff["same_city_via_other_city"][0]
A(f"- 같은 도시 안 이동인데 다른 도시 경유가 최단: {x['from']} → {x['to']} {x['cost']}수 (워프 없으면 {x['cost_no_warp']}수), {', '.join(x['via_cities'])} 경유")
mw = ff["most_warps"]
A(f"- 워프를 가장 많이 타야 하는 최단 경로: 워프 {mw['warps']}번 ({mw['pairs']}쌍), 예: {mw['example']['from']} → {mw['example']['to']}")
A(f"- 전국 중심역(평균 수 최소): {ff['center_with_warp'][0]['station']} {ff['center_with_warp'][0]['mean_cost']}수. 가장 외진 역: {ff['edge_with_warp'][0]['station']}")
A(f"- 가장 먼 동명역 포탈: {ff['portal_span']['farthest'][0]['portal']} {ff['portal_span']['farthest'][0]['max_span_km']}km, 가장 가까운 포탈: {ff['portal_span']['nearest'][0]['portal']} {ff['portal_span']['nearest'][0]['max_span_km']}km (걸어가도 되는 워프)")
A("")
A("## 3. 가정·판단 목록")
A("")
A("| # | 상황 | 판단 | 근거·영향 |")
A("| -: | :- | :- | :- |")
rows = [
    ("PR #1 브랜치 위에서 작업", "지정 브랜치 `claude/inspiring-fermat-n0mp7n`을 `claude/relaxed-rubin-uc43ep`(PR #1 head) 위로 다시 만들었다", "원격에 같은 이름 브랜치가 없었고 로컬 브랜치는 main과 같은 커밋이라 버린 커밋이 없다"),
    ("Wikidata 접근 가능", "검증용으로만 사용 (P197·P625·P81·P296). 한국어 라벨은 Wikidata 아이템을 우리 역에 붙이는 데만 쓰고 포탈 매칭에는 안 씀", "DESIGN 3장 'Wikidata 일반 라벨 매칭 금지' 유지. CC0. SOURCES.md 기록"),
    ("'독립 근거 2개' 기준", "좌표 기하(우리 좌표)와 Wikidata(P197 또는 P625)를 독립 근거로 봤다. 내 배경지식은 근거로 세지 않았다", "그래서 경춘선 광운대 건은 수정 안 함"),
    ("좌표 수정에도 같은 기준", "N3 좌표 수정도 kr_lines.yaml과 같은 '근거 2개' 기준을 적용", "동해선 동래 1건만 수정"),
    ("동래 좌표 값", "Wikidata 값(정밀도 낮음)을 그대로 사용", "더 정확한 공개 좌표가 세션 소스에 없음. 클러스터 분리 판단(1.4km ≫ 500m)에는 충분"),
    ("같은 도시 동명역 입력", "'부산 동래'처럼 도시 접두어가 있으면 그 도시의 같은 이름 역 전부를 후보로", "접두어 없이 '동래'만 치면 기존처럼 후보 목록 오류"),
    ("N2·N3 커밋", "한 커밋으로 묶음", "같은 검증 스크립트·같은 재빌드 산출물을 공유해서 나누면 중간 커밋이 테스트를 깨뜨린다"),
    ("환승 비용 1과 지표", "환승 비용이 0이 아니면 역 수준 그래프로 지름 계산", "1차 코드는 환승 비용을 무시하고 있었다(버그 수정)"),
    ("퍼즐 그래프 수준", "클러스터 수준(환승 0 접힘), strict ruleset", "웹 데이터가 strict라 일치. 환승 1 ruleset용 퍼즐은 만들지 않음"),
    ("최적 경로 개수 정의", "물리적 역 순서 + 워프가 다른 경로만 다른 경로로 셈", "같은 구간 다른 노선(1호선/경의중앙 병행 등)은 한 경로"),
    ("퍼즐 제외 규칙", "출발·도착 이름 같은 쌍, 3수 미만, 25수 이상 제외", "양평→양평 같은 워프 1번짜리와 30수 넘는 지루한 퍼즐 방지"),
    ("N정류장 정의", "정확히 13턴(승차·워프 각 1턴), 환승 0턴, 역 재방문 금지", "'13정류장'을 '13번 이동'으로 해석. '13개 역 방문(12번 이동)'일 수도 있음"),
    ("선로 거리", "인접역 좌표 직선거리 합으로 근사", "실제 선로 km 데이터 없음. 곡선 구간은 과소평가"),
    ("데일리 날짜 기준", "서울 시간(UTC+9) 자정에 바뀜, 1회차 2026-11-05", "config/game.yaml daily_epoch로 변경 가능"),
    ("데일리 퍼즐 공유 텍스트", "출발·도착 역 이름은 노출, 경로는 이모지만", "모두에게 같은 문제라 이름은 스포일러가 아님"),
    ("웹 진행 저장", "localStorage, 실패해도 동작", "브라우저별·기기별 저장. 서버 없음"),
    ("matplotlib 한글 폰트", "PyPI `koreanize-matplotlib`의 NanumGothic 사용 (requirements에는 안 넣음, 08 단계는 폰트 없으면 기본 폰트)", "세션 OS에 한글 폰트가 없었다"),
]
for i, (a, b, c) in enumerate(rows, 1):
    A(f"| {i} | {a} | {b} | {c} |")
A("")
A("## 4. 네가 결정하거나 눈으로 확인할 것")
A("")
A("1. **자기부상철도 제외** (N1, 추천 반영): 궤도운송시설 전환 정보는 네가 준 걸 그대로 썼다. 공식 자료는 세션에서 확인 못 했다.")
A("2. **6호선 응암순환 분리** (N2, 수정함): `docs/reports/lines/seoul-6__main.png`, `seoul-6__eungam-loop.png` 확인. 단방향 순환을 무방향으로 둔 게 괜찮은지.")
A("3. **동해선 동래 좌표·환승 해제** (N3, 수정함): 동해선 동래역과 1·4호선 동래역이 실제로 환승역이 아닌지(약 1.4km 떨어진 별개 역인지) 확인해 줘. 맞으면 부산 안에 같은 도시 포탈 '동래'가 생기는 게 의도대로다. `docs/reports/lines/donghae__main.png`에서 4번 동래가 이제 교대·안락 사이에 있다.")
A("4. **경춘선 광운대 연결** (N2 의심 1): 광운대발 경춘선이 중랑을 거치는지, 상봉으로 바로 가는지. 상봉 직결이면 `config/kr_lines.yaml` gyeongchun의 prepend를 `광운대–상봉` 지선으로 바꾸면 된다.")
A("5. **환승 비용 0 vs 1**: 지표상 차이는 지름 +3·평균 +2.1뿐이고 포탈은 같다. 퍼즐 관점에선 1이 최적해 개수를 줄여서 유일해 퍼즐이 늘 가능성이 크다(이번엔 측정 안 함). 게임 재미로 골라 줘.")
A("6. **D 값**: 500m 유지 추천 (300은 공식 환승역을 쪼개고, 1000은 신촌 포탈을 없앤다). 신촌을 포탈로 둘지가 사실상 결정 포인트.")
A("7. **N정류장 정의**: '13턴'이 맞는지 '13개 역'이 맞는지, 워프를 턴으로 셀지.")
A("8. **데일리 퍼즐 플레이 감**: `cd web && python3 -m http.server 8000` → http://localhost:8000/daily.html. 난이도 기준(config/game.yaml)과 '워프 없으면 N수' 힌트를 처음부터 보여 주는 게 맞는지.")
A("9. **노선 PNG 50장 훑어보기**: `docs/reports/lines/`. 나는 6호선·동해선 외에 이상을 못 찾았다.")
A("10. 1차 보고서의 미결 사항(Pages 활성화, GTX-A, 다국어 파일 라이선스, Overpass 허용)은 그대로 남아 있다.")
A("")
A("## 5. 다음 할 일")
A("")
A("1. 위 4장 답에 따라: 경춘선 광운대 지선화, 환승 비용·D 기본값 확정, N정류장 정의 확정")
A("2. 환승 비용 1 ruleset으로 퍼즐 후보를 다시 뽑아 유일해 개수·난이도 분포 비교 (게임용 기본 ruleset 결정 근거)")
A("3. 데일리 퍼즐: 실제 플레이 피드백 반영(힌트 단계, 연속 기록 streak), N정류장 모드 화면 추가")
A("4. 6호선 응암순환 같은 단방향 구간을 위해 방향 엣지 지원 검토")
A("5. Overpass가 열리면 OSM route relation으로 3차 교차검증 (지금은 기하 + Wikidata 2개)")
A("6. Pages 배포 후 모바일 실기기에서 데일리 퍼즐 확인")
A("7. Phase 1 준비: T2(한자 이체자) 매칭")
A("")
A("## 부록: 커밋·산출물")
A("")
A("| 커밋 | 내용 |")
A("| :- | :- |")
for c, t in [("f4cf34b", "N1 우회 금지 규칙·자기부상 제외·환승 1 ruleset·지름 환승 비용 반영"),
             ("5eab5de", "N2·N3 노선·좌표 검증, 6호선·동래 보정, 동명역 다중 후보"),
             ("62d3d6e", "N4 ruleset 비교"), ("6063c57", "N5 게임 데이터"), ("72e7e38", "N6 데일리 퍼즐"),
             ("c0a73ad", "N7 fun facts"), ("7460c1e", "N2 재검토(라벨 차이 대체 매칭)·테스트 보강")]:
    A(f"| `{c}` | {t} |")
A("| (이 커밋) | 이 보고서 |")
A("")
A("| 경로 | 내용 |")
A("| :- | :- |")
for p_, t in [("config/kr_scope.yaml", "스코프 제외 (자기부상철도)"), ("config/rulesets/strict_transfer1.yaml", "환승 비용 1 ruleset"),
              ("config/ruleset_grid.yaml", "N4 비교 격자"), ("config/game.yaml", "퍼즐·N정류장 설정"),
              ("pipeline/07_fetch_wikidata.py", "Wikidata 수집"), ("pipeline/08_validate_lines.py", "노선·좌표 검증 + PNG"),
              ("pipeline/09_compare_rulesets.py", "ruleset 비교"), ("pipeline/10_build_game_data.py", "퍼즐·N정류장"),
              ("pipeline/11_fun_facts.py", "fun facts"), ("docs/reports/n2_lines_check.md", "N2 상세"),
              ("docs/reports/n3_coords_check.md", "N3 상세"), ("docs/reports/lines/", "노선별 PNG 50장"),
              ("docs/reports/n4_ruleset_compare.md", "N4 상세"), ("docs/reports/n5_game_data.md", "N5 상세 (퍼즐 전체 목록)"),
              ("docs/reports/fun_facts.md", "N7"), ("data/processed/puzzles.json", "퍼즐 101개"),
              ("data/processed/n_stops_max.json", "13정류장 상위 20"), ("data/processed/kr/wikidata_stations.json", "Wikidata 역 1650"),
              ("data/processed/kr/lines_check.json", "검증 원자료"), ("web/daily.html", "데일리 퍼즐")]:
    A(f"| `{p_}` | {t} |")
(REP / "phase0_night2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("ok", len(L))
