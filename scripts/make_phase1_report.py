#!/usr/bin/env python3
# 사용: python3 scripts/make_phase1_report.py <작성 시각 UTC>
"""phase1_taipei.md 조립: 서술은 여기 문자열, 표는 생성 리포트·산출물에서 가져온다 (옮겨 적기 오류 방지)."""
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


def demote(s, n=1):
    return re.sub(r"^(#+)", lambda m: m.group(1) + "#" * n, s, flags=re.M)


def jl(p):
    return json.loads((PROC / p).read_text(encoding="utf-8"))


pyt = (REP / "evidence" / "pytest_phase1.txt").read_text(encoding="utf-8")
node = (REP / "evidence" / "node_test_phase1.txt").read_text(encoding="utf-8")
e2e = (REP / "evidence" / "b4_browser.txt").read_text(encoding="utf-8").strip()
py_sum = [l for l in pyt.splitlines() if re.search(r"\d+ passed", l)][-1].strip("= ")
per_file = {}
for line in pyt.splitlines():
    m = re.match(r"(tests/\S+?)::\S+ (PASSED|FAILED|SKIPPED)", line)
    if m:
        per_file.setdefault(m.group(1), {}).setdefault(m.group(2), 0)
        per_file[m.group(1)][m.group(2)] += 1
node_ok = [l for l in node.splitlines() if re.match(r"^(ok|not ok) \d+", l)]
node_sum = [l for l in node.splitlines() if re.match(r"^# (tests|pass|fail) ", l)]
tw = jl("tw/stations.json")["meta"]
cmp_ = jl("world/compare.json")["results"]
c = tw["counts"]
lab = cmp_["tw_t12_label"]
cross_lab = sorted({(p["tier"], " / ".join(p["texts"]), "; ".join(p["stations"])) for p in lab["portals"] if p["cross_country"]})

L = []
A = L.append
A("# Phase 1 착수 보고서 — 타이베이 (B1~B4)")
A("")
A(f"- 시작: 2026-11-05T15:19:17Z (UTC, 세션 시작 직후 `date` 기록) · 보고서 작성: {written_at}")
A("- 브랜치: `tw-phase1` (`kr-fixes`에서 분기, `kr-fixes` 병합) · PR #4 (base `kr-fixes`, draft). main push·머지 안 함")
A("- 재현: `scripts/build_all.sh` (한국 파이프라인 뒤에 14 타이베이 수집 → 15 정제 → 16 Unihan → 17 ruleset 비교 → 06 웹 번들 5종)")
A("- 이번 세션 한정 지시에 따라 '계획 먼저 제시'와 '실행 전 지적'은 이 보고서 기록으로 대체했다 (3·4장).")
A("")
A("## 요약")
A("")
A("- **B1~B4 모두 돌아가는 상태까지 했지만, 핵심 전제 하나가 막혔다: 타이베이 공식명을 확보하지 못했다.** Geofabrik은 시작 8시간(23:19Z)까지 재시도해도 안 열려서, 지시의 8시간 조항에 따라 그때까지의 결과로 확정했다.")
A("  - Geofabrik 대만 추출본(OSM)은 한국과 같은 TLS 단계 차단. 대만 공식 오픈데이터·운영사 사이트(data.taipei, data.gov.tw, TDX, metro.taipei, 신베이·타오위안 운영사)는 허용 목록 밖. 우회 안 했다.")
A(f"  - 대체로 Wikidata(허용)에서 구조를 받았다: 물리 역 {c['physical_items']}, 노선별 레코드 {c['stations']}, 노선 {c['lines']}, 승차 엣지 {c['ride_edges']}. 순서는 인접(P197)+역번호로 만들고 좌표 기하로 교차검증(전 시퀀스 최적 순서와 동일).")
A(f"  - 그러나 Wikidata 공식명(P1448)이 범위 내 **{c['official_names']}건**이라 이름은 라벨(커뮤니티 표기)뿐이다. 지시대로 공식명만 쓰는 ruleset 3종에서는 타이베이 이름이 매칭에 안 들어가 **국가 간 포탈 0개**.")
A("- B2: T2(OpenCC `t2s` + Unihan 7개 필드 union-find)와 T3(대소문자 접기 + ' station' 꼬리 제거 후 정확 일치) 구현, 규칙은 전부 ruleset. 한국 쪽은 표준데이터 한자·영문 역명.")
A("- B3: 공식명 3종 — 국가 간 0, 국내 T2 **大峙**(서울 대치 ↔ 부산 대티, 같은 한자 다른 독음), T3 **seongnam**(성남 ↔ 석남, 로마자 동음). 참고(라벨 허용) — T2 국가 간 6개: " + ", ".join(t.split(" / ")[0] for _, t, _ in cross_lab) + ". **허브 폭발 없음** (T2·T3 최대 차수 2).")
A(f"- 부작용 발견: 국가 간·국내 T2/T3 포탈이 생기면 한국 내 최단 경로가 짧아진다 (한국 내 순서쌍 중 단축 비율: 공식 T1+T2 {cmp_['tw_t12']['kr_shortened']['shortened'] / cmp_['tw_t12']['kr_shortened']['pairs']:.1%}, 참고 T1+T2+T3 {cmp_['tw_t123_label']['kr_shortened']['shortened'] / cmp_['tw_t123_label']['kr_shortened']['pairs']:.1%} — 타이베이 경유 포함).")
A("- 데이터 오류 발견: 표준데이터 대구 6개 역의 한자역사명이 문자 그대로 '한자가없음' → 차수 6짜리 가짜 T2 포탈이 생겼었다. 문자 체계 검사(`script_check`)로 차단.")
A("- B4: 웹에 ruleset 선택(한국만 / 공식명 3종 / 참고 2종), 나라 표시, 국가 간 워프 아크(주황 실선). node 테스트로 번들 5종의 JS 경로 = Python 경로 고정, Playwright 데스크톱·모바일 콘솔 에러 0.")
A(f"- 테스트: **pytest {py_sum}**, **node " + " / ".join(x.lstrip('# ') for x in node_sum) + "**.")
A("")
A("## 1. 단계별 완료 증거")
A("")
A("### B1 — 타이베이 역·노선·다국어명 (커밋 `1788a1e`)")
A("")
A("- 소스 결정: Geofabrik 대만 추출본 `download.geofabrik.de/asia/taiwan-latest.osm.pbf` → 한국과 같은 egress TLS 단계 종료. 대만 공식 호스트 9곳(운영사 3, data.taipei, data.gov.tw, TDX, 교통부, zh.wikipedia 등)은 프록시 CONNECT 403(허용 목록 밖). 점검 기록 `docs/reports/evidence/network_check_phase1.md` (2026-11-05T16:27:47Z). Wikidata SPARQL은 정상 → 구조 데이터 대체 소스로 사용 (`pipeline/14_fetch_tw_wikidata.py`, 쿼리 4회, 요청 간 3초, UA에 프로젝트명, 원문 캐시)")
A("- 범위(`config/tw_scope.yaml`): 臺北捷運 문후·단수이신이(+신베이터우 지선·신이선 연장)·쑹산신뎬(+샤오비탄 지선)·중허신루·반난·환상선, 桃園機場捷運, 新北捷運 단하이·안컹·싼잉. 사용 중(P5817) + bbox + 개통일 ≤ 2026-11-05. 노선 아이템 하나를 잘못 넣었다가(우루무치 공항철도 Q134099943) 좌표로 발견해 뺐다")
A("- 정제(`pipeline/15_build_tw.py`): 노선별 레코드(id `tw:<노선>:<역번호>`), 순서는 P197 중 노선 한정자가 맞는 진술 + 한정자 없는 진술은 역번호가 이어질 때만. 순환은 역번호 비연속부터 끊는다(七張–新店 옛 철도선 진술). 본선 = 가장 긴 경로, 나머지 지선 (`metro_portal/lineseq.py`)")
A("")
A(demote(section("b1_taipei_data.md", "## 노선", "## 다른 노선 한정자라"), 2))
A("")
A(demote(section("b1_taipei_data.md", "## 같은 노선에서 역번호가", "zh 라벨 없는"), 2))
A("")
A("- 위 두 쌍의 실제 역번호는 板新 Y15·板橋 Y16, 頭前庄 Y18·幸福 Y19로 알고 있다 (작성자 지식, 검증 못 함). 순서는 P197로 맞게 나와서 그래프에는 영향이 없다")
A(demote(section("b1_taipei_data.md", "## 최근 개통 표기", "## 제외한 아이템"), 2))
A("")
A("- 다국어명: zh-Hant 라벨 193, en 라벨 193 (전부 `source: wikidata_label`, `official: false`). 공식명 0")
A("")
A("### B2 — T2·T3 (커밋 `2263560`)")
A("")
A("- `metro_portal/variants.py`: OpenCC 변환 사슬(설정 순서대로) → 글자마다 Unihan 이체자 클래스의 대표 글자(최소 코드포인트). Unihan 18.0 (`pipeline/16_fetch_unihan.py`, unicode.org 허용 호스트). 7개 필드로 1.65만 자, 크기 > 8인 클래스 7개는 접지 않음")
A("- `graph.build_portals`: 등급별 정규화 덮어쓰기, 이름 출처 허용 목록, 문자 체계 검사, 비싼 등급 중복 생략(`dedupe_subsumed`), 포탈 원문 기록")
A("- ruleset (`config/rulesets/tw_t1.yaml` → `tw_t12.yaml` → `tw_t123.yaml`, 참고 `*_label.yaml`). T2 핵심 설정:")
A("")
A("```yaml")
t12 = (ROOT / "config" / "rulesets" / "tw_t12.yaml").read_text(encoding="utf-8")
A(t12[t12.index("  T2:"):].rstrip())
A("```")
A("")
A("- 접기 예: 敎大 = 教大, 市廳 = 市庁 = 市厅, 驛 = 駅, 臺北 = 台北, 回龙 = 迴龍. 과병합 예: 發 = 髮, 乾 = 幹 = 干 (간체화가 다대일)")
A("- 테스트(`tests/test_tiers.py`): 이체자 매칭, 부분 일치 금지(市廳 ≠ 仁川市廳), 괄호 부역명·'站' 제거, '한자가없음'·'-'·한글 섞인 한자명 무시, 공식명만 ruleset은 라벨 제외·참고 ruleset은 포함, T3 대소문자·꼬리·부분 일치 금지, 중복 생략")
A("")
A("### B3 — 통합 그래프 ruleset 비교 (커밋 `9484200`)")
A("")
A(demote(section("b3_world_rulesets.md", "## 지표 (DESIGN 6장)", "## 국가 내부 T2"), 2))
A("")
A(demote(section("b3_world_rulesets.md", "## 국가 내부 T2", "## 더 싼 등급과"), 2))
A("")
A("- 허브 폭발 판정: 6종 모두 **정상**. 같은 범위(한국+타이베이 분리 상태)에서 지름 변화 없음, T2·T3 최대 차수 2. Phase 1 규모에선 T3(영문 정확 일치)도 폭발하지 않는다 — 한국 RR 로마자와 대만 병음이 거의 겹치지 않고, 번역형 영문명(City Hall 등)은 'Taipei City Hall'처럼 접두어가 달라 정확 일치가 안 된다")
A("- 참고 ruleset 지름이 67 → 63으로 줄어든 건 범위가 한국+타이베이 전체로 넓어진 결과라 같은 범위 비교가 아니다 (판정 기준에서 제외)")
A("")
A("### B4 — 웹 (커밋 `7d1cb4b`)")
A("")
A("- `pipeline/06_build_web_data.py --countries KR,TW` → `web/data/world_<rs>.json` (약 380KB × 5) + 기대 경로. 역에 나라(`co`), 포탈에 국가 간 플래그(`x`)·원문")
A("- `web/world.js`: ruleset 번들 목록, 나라 표기, 워프 스타일 (국가 간 = 주황 실선, 같은 나라 = 보라 점선, T2·T3 점선 간격 구분). `web/app.js`: ruleset 선택 시 번들 재로딩, 역 팝업·툴팁에 나라, 국가 간 워프 결과 표시, URL 해시 `rs`, 지도 한국/타이베이 이동, 공식명 번들에는 '국가 간 포탈 없음' 안내, 참고 번들에는 '공식명 아님' 안내")
A("- 브라우저 E2E (`scripts/e2e_world.cjs`, 전문 `docs/reports/evidence/b4_browser.txt`):")
A("")
A("```")
A(e2e)
A("```")
A("")
A("- 스크린샷: `docs/reports/evidence/b4_world_desktop.png`, `b4_world_mobile.png` (지도 타일은 세션에서 tile.openstreetmap.org가 막혀 안 보인다. 2차와 같음). 데일리 퍼즐 페이지 회귀 E2E도 에러 0")
A("")
A("### 테스트 출력")
A("")
A(f"- pytest: `{py_sum}` (전문 `docs/reports/evidence/pytest_phase1.txt`). Phase 1 관련: "
  + ", ".join(f"{f_.split('/')[-1]} {cnt.get('PASSED', 0)}" for f_, cnt in sorted(per_file.items()) if any(k in f_ for k in ("lineseq", "tiers", "world_compare"))))
A(f"- node: " + ", ".join(x.lstrip("# ") for x in node_sum) + " (전문 `docs/reports/evidence/node_test_phase1.txt`)")
A("")
A("```")
A("\n".join(node_ok))
A("```")
A("")
pz = jl("puzzles.json")
cal = pz["stats"].get("calibration", {})
A("### 추가 작업 (시간이 남아서, 지시 순서대로)")
A("")
A("1. **도쿄권 데이터 소스 조사** (커밋 `247ff37`): `docs/reports/tokyo_sources.md`, 재현 `python3 scripts/survey_tokyo.py`. ODPT·운영사·국토수치정보 403, Geofabrik 간토 TLS 리셋 → 세션에선 Wikidata만. Wikidata 실측 운행 중 역 1,592 (인접 98%, 역번호 90%, 공식명 23%), 노선 168. 국가 간 T2 충돌 추정 도쿄↔한국 4(三田·太田·板橋·田浦), 도쿄↔타이베이 3(中山·府中·板橋), 板橋는 세 나라 공통. T3 국가 간 0. 결론: ODPT 접근 허용이 선행 조건")
A("2. **테스트 보강** (커밋 `33c6075`, `209d3d8`): 퍼즐 정·역방향 중복 금지, 이체자 클래스 상한, casefold·char_map 옵션 격리, 문자 체계 검사, 다국가 로더(국가 간 클러스터 혼합 없음), 직관 탐색 결정성")
A(f"3. **퍼즐 난이도 보정** (커밋 `209d3d8`): 지리 감각 플레이어를 흉내 낸 최선 우선 탐색(`metro_portal/game.intuition_search`)으로 퍼즐 104개를 풀어 '최적 / 찾은 비용' 점수와 펼친 역 수를 기록하고 보정 등급을 주석으로 달았다 (선정·데일리 순서는 그대로). "
  f"규칙 등급별 펼친 역 중앙값 {', '.join(f'{k} {v}' for k, v in pz['stats'].get('calibration_expanded_median', {}).items())}. "
  f"규칙=보정 일치 {sum(cal.get(f'{a}->{a}', 0) for a in ('easy', 'normal', 'hard'))}/{sum(cal.values())}. 규칙상 easy인 도시 횡단 퍼즐 상당수가 지리 감각과 반대 방향 포탈을 요구한다. 표: `docs/reports/n5_game_data.md` '난이도 보정'. 처음 시도한 재방문 금지 탐욕 플레이어는 대부분 막다른 길에 갇혀 버렸다")
A("")
A("## 2. 미완 단계와 사유")
A("")
A("| 단계 | 상태 | 사유 | 남은 일 |")
A("| :- | :- | :- | :- |")
_log = (ROOT / "docs" / "reports" / "evidence" / "geofabrik_attempts.log").read_text(encoding="utf-8").splitlines()
_tries = sum(int(l.split("시도 ")[1].split("회")[0]) for l in _log)
A(f"| B1 OSM(Geofabrik 대만) 추출 | 대체 (Wikidata), 8시간 조항으로 종료 | Geofabrik egress TLS 단계 차단. 같은 호스트(download.geofabrik.de)에 23:18Z까지 {_tries}번 재시도했지만 한 번도 안 열림 (`docs/reports/evidence/geofabrik_attempts.log`, A5와 공유) | 접속되면 `metro_portal/osm.py`로 같은 스키마 추출 가능 (파서는 A5에서 준비) |")
A("| B1 공식명 | **미확보** | Wikidata P1448 0건, 대만 공식 호스트 허용 목록 밖 | 공식 소스 결정(4장 1번) 후 이름만 교체하면 B3·B4는 그대로 재생성된다 |")
A("| B3 공식명 기준 국가 간 포탈 | 0개 (전제 미충족) | 위와 같음 | 참고 ruleset으로 엔진 동작은 확인함 |")
A("")
A("## 3. 가정·판단")
A("")
A("- '공식 이름만 쓰고 출처 기록' 지시를 지키려고 Wikidata 라벨은 official=False로만 저장하고, 기본 비교 3종에서는 매칭에 쓰지 않았다. 라벨 허용 결과는 '참고'로 분리해서 웹에서도 그렇게 표시했다. 라벨을 공식명처럼 써서 국가 간 포탈을 만드는 쪽을 택하지 않은 이유: 지시 위반이고, DESIGN 3장도 Wikidata 일반 라벨을 매칭에 쓰지 말라고 한다.")
A("- 순서·구조 데이터는 이름과 달리 Wikidata를 썼다. 역번호(P296)는 운영사 번호라 공식 성격이 있고, 인접(P197)과 좌표 기하 두 근거가 전부 일치했다.")
A("- 범위: 사용자가 말한 세 운영 주체의 '사용 중' 노선 전부. 신베이 메트로 싼잉선과 신이선 연장(R01 廣慈/奉天宮)은 Wikidata상 2026-06-30·2026-08-30 개통 표기라 넣었지만 단일 근거다(검증 못 함). 타오위안 그린선·완다선·민성시즈선 등 공사 중은 뺐다.")
A("- 타이베이에는 공식 환승 정보가 없어 3차 환승 규칙이 자동으로 거리 D=500 판정이 된다. 환승역은 Wikidata 아이템 하나가 여러 노선 역번호를 가지는 구조라 대부분 같은 좌표로 묶인다.")
A("- T2 한국 쪽은 지시대로 표준데이터 한자역사명만 썼다. 레일포털 다국어 파일의 중국어 번체명(예: 판교 板橋)은 공식 번역이지만 '한자 역명'이 아니라서 T2에 넣지 않았다. 넣으면 T1(같은 언어·문자 정확 일치)과 T2 경계가 흐려진다.")
A("- T2 변환은 OpenCC `t2s`(번체→간체 접기)를 기본으로 했다. 다대일 과병합이 생기지만, 실험해 보니 Unihan Z/의미 이체자만 쓰면 참고 ruleset의 국가 간 포탈 6개 중 迴龍(의정부 회룡)을 잃는다 — 표준데이터 회룡 한자명이 간체 '回龙'으로 적혀 있어 번체·간체 대응이 필요하다. 나머지 5개(板橋·中和·土城·明德·松山)와 국내 大峙는 같다.")
A("- T3 정규화의 ' station' 꼬리 제거는 Wikidata 영문 라벨 관행 때문에 넣었다. 공식 영문명이 들어오면 다시 볼 값이다.")
A("- `dedupe_subsumed`: T3 'city hall'처럼 T1이 이미 잇는 클러스터 집합을 비싼 등급이 또 잇는 포탈은 만들지 않았다(공식 T1+T2+T3에서 39개 생략). 경로 비용에는 영향이 없고 포탈 수·지표만 깔끔해진다.")
A("- 허브 폭발 기준값(차수 5, ×2, 20%)은 작성자 판단이다.")
A("- 지도 표시명은 번체 라벨에서 끝의 '站'만 뗐다(台北車站의 '車站'은 둔다). 한국어 표기는 없다.")
A("")
A("## 4. 결정하거나 확인할 것")
A("")
A("1. **타이베이 공식명 소스**: (a) data.taipei / TDX / metro.taipei 같은 공식 호스트를 환경 허용 목록에 추가, (b) 수동으로 받은 공식 역명표를 `data/raw/manual/`에 커밋, (c) Wikidata 원어(zh-Hant) 라벨을 준공식으로 인정 중 하나. (c)면 참고 ruleset 결과가 곧 본 결과가 된다.")
A("2. Geofabrik 접속 문제 (한국 A5와 같은 원인). 풀리면 OSM 이름 태그(name:zh, name:en)가 공식명 대용이 될 수 있는지도 같이 판단 필요.")
A("3. T2 과병합 정책: OpenCC `t2s` 유지(중국 대비, 迴龍 같은 간체 표기 대응) vs Unihan Z/의미 이체자만(과병합은 줄지만 迴龍을 잃음).")
A("4. **국가 간 워프의 국내 우회 효과**: 판교 → 부산 토성은 공식 T1+T2에서 11수(GTX-A·大峙 경유), 참고 T1+T2에서 8수(판교 ⇢ 板橋 → 板南線 4역 → 土城 ⇢ 토성)로 타이베이를 거친다. 밈으로는 재밌지만 국내 퍼즐에서 허용할지.")
A("5. 국내 T2·T3 포탈 (大峙: 대치↔대티, seongnam: 성남↔석남)을 '재밌는 발견'으로 둘지, 독음이 다른 한자 일치는 별도 등급으로 뺄지.")
A("8. 퍼즐 보정 등급을 실제 난이도 라벨로 쓸지 (지금은 주석만. 쓰면 선정·데일리 순서가 바뀐다).")
A("6. 싼잉선·신이선 R01 개통 표기 (Wikidata 단일 근거) 확인.")
A("7. 표준데이터 한자역사명 표기 오류('한자가없음' 6건, '-' 등) 원천 신고 여부.")
A("")
A("## 5. 다음 할 일")
A("")
A("- 공식명 소스 결정 → 타이베이 이름 교체 → 14·15·17·06 재생성 (코드 변경 없이 데이터만)")
A("- 도쿄권: 조사 문서 `docs/reports/tokyo_sources.md` 작성함 (ODPT·Geofabrik·운영사 전부 차단, Wikidata 실측 역 1,592·공식명 23%, 국가 간 T2 충돌 추정 도쿄↔한국 4·도쿄↔타이베이 3, 板橋는 세 나라 공통). ODPT 접근 허용 여부가 선행 결정")
A("- 국가 간 워프의 게임 규칙 (국내 퍼즐에서 국가 간 워프 금지 옵션 등)")
A("- Phase 1 지도: 도시별 패널 + 패널 간 포탈 스타일 검토 (DESIGN 8장)")
(REP / "phase1_taipei.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"wrote {REP / 'phase1_taipei.md'} ({len(L)} lines)")
