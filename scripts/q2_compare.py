#!/usr/bin/env python3
"""4차 Q2: 데일리 순서 전후 비교와 제약 민감도 → docs/reports/q2_daily_order.md, data/processed/daily_order_compare.json

버전: 2차(QA가 플레이한 배포본, git 72e7e38) / 3차(main) / 4차 구방식(같은 그래프에 3차 선정 + 시드 셔플) / 4차 신방식 / 4차 유일성 완화판.
같은 제약 정의(config/game.yaml daily_order)로 위반을 센다. 2차는 보정 난이도가 없어 규칙 난이도로 요일 제약을 잰다.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal.daily_order import WEEKDAYS, Planner, ranked, summarize  # noqa: E402

GIT_VERSIONS = [("2차 (QA 배포본)", "72e7e38"), ("3차 (main)", "origin/main")]


def git_json(rev, path):
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def pool_share(puzzles):
    n = len(puzzles)
    c = Counter(x for p in puzzles for x in set(p["warp_portals"]))
    return n, c


def first_days(pz_by, order, epoch, k=7):
    out = []
    for t, pid in enumerate(order[:k]):
        p = pz_by[pid]
        out.append({"day": t + 1, "date": (epoch + timedelta(days=t)).isoformat(), "wd": WEEKDAYS[(epoch + timedelta(days=t)).weekday()],
                    "from": p.get("from_label", p["from"]), "to": p.get("to_label", p["to"]), "sig": "+".join(p["warp_portals"]) or "-",
                    "level": p.get("difficulty_calibrated") or p["difficulty"], "h": round(1 - p.get("intuition_score", 0), 2) if "intuition_score" in p else None})
    return out


def main() -> int:
    oc = yaml.safe_load(open(ROOT / "config" / "game.yaml", encoding="utf-8"))["puzzles"]["daily_order"]
    cur = json.loads((ROOT / "data" / "processed" / "puzzles.json").read_text(encoding="utf-8"))
    epoch = date.fromisoformat(cur["definition"]["epoch"])
    rows, firsts = [], {}
    for label, rev in GIT_VERSIONS:
        pz = git_json(rev, "data/processed/puzzles.json")
        ps = pz["puzzles"]
        order = pz["daily_order"]
        pl = Planner(ps, {**oc, "days": len(order)}, date.fromisoformat(git_json(rev, "web/data/puzzles.json")["daily_epoch"]))
        sm = summarize(pl, order)
        n, sh = pool_share(ps)
        rows.append({"version": label, "pool": n, "days": len(order), **sm, "pool_share": ranked(sh, 6),
                     "calibrated": "difficulty_calibrated" in ps[0]})
        firsts[label] = first_days({p["id"]: p for p in ps}, order, pl.epoch)
    by = {p["id"]: p for p in cur["puzzles"]}
    leg = cur["compare"]["legacy_same_graph"]
    rows.append({"version": "4차 구방식 (같은 그래프, 3차 선정+셔플)", "pool": leg["pool"], **{k: v for k, v in leg.items() if k != "pool"},
                 "pool_share": None, "calibrated": True})
    sched = [by[i] for i in cur["daily_order"]]
    n, sh = pool_share(sched)
    rows.append({"version": "4차 신방식 (제약 일정)", "pool": cur["stats"]["pool_size"], **cur["stats"]["daily_order"],
                 "pool_share": ranked(sh, 6), "calibrated": True})
    rel = cur["compare"]["relaxed_unique"]
    rows.append({"version": f"4차 유일성 완화판 (최적 경로 ≤ {oc['relaxed_max_optimal_paths']})", **rel, "pool_share": None, "calibrated": True})
    firsts["4차 신방식"] = first_days(by, cur["daily_order"], epoch, 14)

    # 민감도: 같은 4차 풀로 상한만 바꿔 다시 짠다
    pool = cur["puzzles"]
    sens = []
    for name, over in [("기본", {}), ("창 상한 3", {"max_portal_per_window": 3}), ("창 상한 5", {"max_portal_per_window": 5}),
                       ("자카드 0.5", {"max_jaccard": 0.5}), ("시그니처 간격 28", {"signature_gap_days": 28}),
                       ("일정 364일 (탐욕만)", {"days": 364})]:
        cfg = {**oc, **over}
        pl = Planner(pool, cfg, epoch)
        try:
            o = pl.greedy()
            if cfg["days"] == oc["days"]:   # 364일은 풀(374개)을 거의 다 써서 국소탐색이 오래 걸린다 → 탐욕 결과만
                o = pl.local_search(o)
            sm = summarize(pl, o)
            sens.append({"variant": name, "days": cfg["days"], "violations": sm["violations"], "distinct_signatures": sm["distinct_signatures"],
                         "top_portal": next(iter(sm["portal_counts"].items())), "weekday_mean_h": sm["weekday_mean_h"]})
        except ValueError as e:
            sens.append({"variant": name, "days": cfg["days"], "error": str(e)})
        print(f"[q2] {name}: {sens[-1].get('violations', sens[-1].get('error'))}")

    out = {"rows": rows, "first_days": firsts, "sensitivity": sens}
    (ROOT / "data" / "processed" / "daily_order_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(oc, cur, rows, firsts, sens)
    return 0


def write_report(oc, cur, rows, firsts, sens):
    L = ["# Q2 데일리 퍼즐 다양성 — daily_order 재구성", "",
         "생성: `python3 pipeline/10_build_game_data.py` (일정) → `python3 scripts/q2_compare.py` (이 비교표). 설정 `config/game.yaml` puzzles.daily_order", "",
         "## 정의", "",
         "- **풀이 시그니처**: 최적 경로에 쓰인 포탈 순서 (예: `중동+동백`). 포탈 집합은 순서를 뺀 것.",
         "- **보정 난이도** (3차 직관 탐색): 점수 = 최적 비용 / 지리 감각 최선 우선 탐색(역의 가치 = 그 역이나 그 역의 워프 도착지에서 목적지까지 대권거리의 최솟값)이 찾은 경로 비용. "
         "1.0 = easy, 0.4 이상 = normal, 그 밖 = hard. **난이도 지수 h = 1 − 점수** (0 = 지리 감각대로 가면 최적, 1에 가까울수록 감각과 반대로 가야 함).",
         f"- 제약 (전부 {oc['days']}일 순환 일정 기준, 마지막 날 다음은 첫날): "
         f"(i) 같은 시그니처 간격 ≥ {oc['signature_gap_days']}일, (ii) 연속한 두 날 포탈 집합 자카드 ≤ {oc['max_jaccard']}, "
         f"(iii) {oc['window_days']}일 창마다 포탈별 등장 ≤ {oc['max_portal_per_window']}, (iv) 요일별 허용 보정 난이도:",
         "", "| 요일 | 허용 등급 | 목표 h |", "| :- | :- | -: |"]
    ko = dict(zip(WEEKDAYS, "월화수목금토일"))
    L += [f"| {ko[d]} | {', '.join(oc['weekday'][d]['levels'])} | {oc['weekday'][d]['target_h']} |" for d in WEEKDAYS]
    L += ["", "- 풀이: 탐욕 배치(날마다 하드 제약을 지키는 후보 중 소프트 비용 최소 — 목표 h 차이, 30일 안 같은 포탈 재사용의 거리 역수 합, 흥미도) → "
          "국소탐색(위반 난 날을 미사용 후보로 교체하거나 다른 날과 교환, (위반 수, 소프트 비용) 사전식 감소). ILP는 쓰지 않았다 (탐욕+국소탐색으로 위반 0).",
          f"- 풀: 종류(shortcut/crosscity) × 규칙 난이도마다 흥미도 순 {oc['pool_per_kind_per_difficulty']}, 같은 시그니처 등급마다 {oc['pool_max_per_warp_signature']}개, "
          f"같은 출발/도착 역 {oc['pool_max_per_endpoint']}번까지 → {cur['stats']['pool_size']}개 중 {oc['days']}개를 일정에 쓴다.", "",
          "## 전후 비교", "",
          "| 버전 | 풀 | 일정 | (i) 시그니처 위반 | (ii) 자카드 위반 | (iii) 창 위반 | (iv) 요일 위반 | 시그니처 최소 간격 | 서로 다른 시그니처 | 연속일 자카드 최대/평균 | 30일 창 포탈 최다 |",
          "| :- | -: | -: | -: | -: | -: | -: | -: | -: | :- | :- |"]
    for r in rows:
        v = r["violations"]
        top = next(iter(r["portal_max_in_window"].items())) if r.get("portal_max_in_window") else ("-", "-")
        L.append(f"| {r['version']} | {r['pool']} | {r['days']} | {v['signature']} | {v['jaccard']} | {v['window']} | {v['weekday']}"
                 f"{'' if r.get('calibrated', True) else '¹'} | {r.get('min_signature_gap')} | {r['distinct_signatures']} | "
                 f"{r['max_jaccard_consecutive']} / {r['mean_jaccard_consecutive']} | {top[0]} {top[1]} |")
    L += ["", "¹ 2차 데이터에는 보정 난이도가 없어 규칙 난이도로 셌다. 위반 수는 쌍(시그니처)·날(자카드·요일)·(창 시작일, 포탈)(창) 단위.", "",
          "### 요일별 평균 난이도 지수 h", "", "| 버전 | " + " | ".join(ko[d] for d in WEEKDAYS) + " |", "| :- | " + " | ".join("-:" for _ in WEEKDAYS) + " |"]
    for r in rows:
        h = r.get("weekday_mean_h") or {}
        if r.get("calibrated", True) and h:
            L.append(f"| {r['version']} | " + " | ".join(str(h.get(d, "-")) for d in WEEKDAYS) + " |")
    L += ["", "### 포탈 분포 — 일정 전체에서 포탈별 등장 횟수 (상위 10)", ""]
    for r in rows:
        pc = list((r.get("portal_counts") or {}).items())[:10]
        L.append(f"- {r['version']} ({r['days']}일): " + ", ".join(f"{k} {v}" for k, v in pc))
    L += ["", "QA 지적(2차: 101개 중 동백 33·송정 30개)과 같은 방식으로 센 '최적 경로에 그 포탈을 쓰는 퍼즐 수 / 일정 길이':", ""]
    for r in rows:
        if r.get("pool_share"):
            L.append(f"- {r['version']}: " + ", ".join(f"{k} {v}/{r['days']} ({v / r['days']:.0%})" for k, v in r["pool_share"]))
    L += ["", "2차 수치는 저장된 유일 최적 경로 기준이라 QA(동률이면 자체 계산 경로)와 1~2개 다를 수 있다.", "",
          "## 처음 며칠", ""]
    for k, days in firsts.items():
        L += [f"### {k}", "", "| 일 | 날짜 | 요일 | 출발 → 도착 | 시그니처 | 등급 | h |", "| -: | :- | :- | :- | :- | :- | -: |"]
        L += [f"| {d['day']} | {d['date']} | {ko[d['wd']]} | {d['from']} → {d['to']} | {d['sig']} | {d['level']} | {d['h'] if d['h'] is not None else '-'} |" for d in days]
        L.append("")
    rel = next(r for r in rows if r["version"].startswith("4차 유일성"))
    share = cur["compare"]["pool_portal_share"]
    L += ["## Q2-5 최적해 유일성 완화 비교", "",
          f"- 유일 최적해만: 후보 shortcut {cur['stats']['candidates_shortcut']:,} / crosscity {cur['stats']['candidates_crosscity']:,}. "
          f"완화(최적 경로 ≤ {oc['relaxed_max_optimal_paths']}): {rel['candidates_shortcut']:,} / {rel['candidates_crosscity']:,}.",
          "- 같은 선정 규칙으로 뽑은 풀에서 포탈별 '그 포탈을 쓰는 퍼즐 수' 상위:",
          "  - 유일: " + ", ".join(f"{k} {v}" for k, v in share["unique"].items()),
          "  - 완화: " + ", ".join(f"{k} {v}" for k, v in share["relaxed"].items()),
          "- 판단: 완화해도 상위 포탈(송정·시청·화정)의 쏠림은 거의 같다. 쏠림의 주원인은 유일성 조건이 아니라 '단축 폭(흥미도) 순 선정'이다 — 큰 단축은 "
          "수도권 ↔ 부산·대구를 잇는 소수의 다리 포탈에서만 나온다. 그래서 기본은 유일 최적해를 유지하고, 다양성은 풀 확대 + 일정 제약으로 확보했다. "
          (f"완화판 일정도 위반 0건이라 기본과 차이가 없다 → 유일성을 완화할 이유가 없다." if sum(rel["violations"].values()) == 0
           else f"완화판 일정은 위반 {sum(rel['violations'].values())}건."), "",
          "## 제약 민감도 (같은 4차 풀로 상한만 바꿔 다시 짬)", "",
          "| 변형 | 일정 | 위반 (i/ii/iii/iv) | 서로 다른 시그니처 | 최다 포탈 | 요일 h (월 → 일) |", "| :- | -: | :- | -: | :- | :- |"]
    for s in sens:
        if "error" in s:
            L.append(f"| {s['variant']} | {s['days']} | 실패: {s['error']} | - | - | - |")
            continue
        v = s["violations"]
        L.append(f"| {s['variant']} | {s['days']} | {v['signature']}/{v['jaccard']}/{v['window']}/{v['weekday']} | {s['distinct_signatures']} | "
                 f"{s['top_portal'][0]} {s['top_portal'][1]} | {' → '.join(str(s['weekday_mean_h'].get(d)) for d in WEEKDAYS)} |")
    (ROOT / "docs" / "reports" / "q2_daily_order.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
