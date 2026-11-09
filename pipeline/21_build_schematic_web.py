#!/usr/bin/env python3
"""5차 R3. 도식 노선도 웹 번들·SVG 빌드 — 커밋된 풀이 캐시만 읽는다 (MIP를 풀지 않는다, 결정적).

캐시(data/processed/schematic/<권역>.json)는 20 단계(pipeline/20_solve_schematic.py)가 만든다.
권역마다 지금 그래프로 입력 지문을 다시 계산해 캐시의 지문과 비교한다. 다르면(그래프·모델 파라미터가 바뀜) 멈추고
다시 풀어야 할 권역을 알려 준다 (낡은 도식을 조용히 내보내지 않는다).

입력: config/schematic.yaml, data/processed/schematic/<region>.json, data/processed/{kr,tw}
출력: web/data/schematic.json, docs/reports/schematic/<region>.svg, docs/reports/schematic/<region>_geo.svg
사용: python3 pipeline/21_build_schematic_web.py [--no-svg]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal import schematic as S  # noqa: E402
from metro_portal.names import world_display_names  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base, load_multi  # noqa: E402

CACHE = ROOT / "data" / "processed" / "schematic"
REP = ROOT / "docs" / "reports" / "schematic"
WEB = ROOT / "web" / "data" / "schematic.json"


def region_note(city, engine, st, st_geo):
    """웹 패널 안내 문구. 교차는 지리 좌표에도 있는 입체 교차(역 없는 교차)와 도식이 새로 만든 교차를 나눠 말한다."""
    if engine == "snap-lp":
        return f"{city}: MIP가 시간 제한 안에 해를 못 찾아 근사 배치(snap-lp)로 보여 준다. 일부 엣지는 8방향이 아니고 교차가 있다."
    if engine == "geo-fallback":
        return f"{city}: 시간 제한 안에 도식 해를 못 찾아 지리 좌표로 보여 준다."
    extra = st["crossings"] - st_geo["crossings"]
    if st["crossings"] and extra <= 0:
        return f"{city}: 선 교차 {st['crossings']}곳. 지리 좌표에도 역 없이 입체 교차하는 곳이 {st_geo['crossings']}곳 있어서 그 수준이다."
    if extra > 0:
        return f"{city}: 지리 좌표보다 교차가 {extra}곳 많다 (도식 {st['crossings']}, 지리 {st_geo['crossings']}). 평면성 제약을 다 풀지 못했다."
    return ""


def check_cache(reg, rcfg, g, cg, doc):
    """캐시가 지금 그래프에 맞는지. 문제 목록 반환 (빈 목록 = 통과)."""
    errs = []
    if "fingerprint" not in doc:
        errs.append("캐시에 지문이 없다 (4차 형식) — 20_solve_schematic.py --adopt 또는 재풀이")
    elif doc["fingerprint"] != S.fingerprint(g, cg, rcfg):
        errs.append(f"지문 불일치 (캐시 {doc['fingerprint']} ≠ 지금 {S.fingerprint(g, cg, rcfg)}) — 그래프나 모델 파라미터가 바뀜")
    if set(doc["schematic"]) != set(g["nodes"]):
        miss = sorted(set(g["nodes"]) - set(doc["schematic"]))[:5]
        extra = sorted(set(doc["schematic"]) - set(g["nodes"]))[:5]
        errs.append(f"정점 집합이 다르다 (캐시에 없음 {miss}, 그래프에 없음 {extra})")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-svg", action="store_true", help="웹 번들만 쓴다")
    ap.add_argument("--out", default=str(WEB), help="웹 번들 경로 (테스트용)")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "config" / "schematic.yaml", encoding="utf-8"))
    worlds = {}

    def world(country):
        if country not in worlds:
            worlds[country] = (build_world(*load_multi(("KR", "TW")), load_ruleset("tw_t12")) if country == "TW"
                               else build_world(*load_base(), load_ruleset(cfg["ruleset"])))
        return worlds[country]
    web = {"regions": []}
    problems = {}
    REP.mkdir(parents=True, exist_ok=True)
    for reg in cfg["regions"]:
        path = CACHE / f"{reg['id']}.json"
        if not path.exists():
            problems[reg["id"]] = ["캐시 파일 없음 — python3 pipeline/20_solve_schematic.py --regions " + reg["id"]]
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        g = S.region_graph(world(reg["country"]), reg["city"])
        cg = S.contract(g, keep_every=reg.get("keep_every", 2))
        rcfg = S.region_params(cfg, reg)
        errs = check_cache(reg, rcfg, g, cg, doc)
        if errs:
            problems[reg["id"]] = errs
            continue
        pos = {k: tuple(v) for k, v in doc["schematic"].items()}
        note = region_note(reg["city"], doc["engine"], doc["stats"], doc["stats_geo"])
        web["regions"].append({"id": reg["id"], "city": reg["city"], "country": reg["country"], "engine": doc["engine"], "note": note,
                               "s": doc["schematic"], "g": doc["geo"], "e": doc["edges"], "lines": doc["lines"]})
        if not a.no_svg:
            # 5차 R2: SVG 라벨도 웹과 같은 표시 이름 ('서울역', '동래역' 등)
            names = world_display_names(world(reg["country"]))
            (REP / f"{reg['id']}.svg").write_text(S.render_svg(g, pos, f"{reg['city']} — 자동 도식 (octilinear MIP)", size=1100, names=names), encoding="utf-8")
            (REP / f"{reg['id']}_geo.svg").write_text(S.render_svg(g, g["pos"], f"{reg['city']} — 지리 좌표 (비교용)", size=1100, names=names), encoding="utf-8")
        print(f"[21] {reg['id']}: 캐시 사용 (지문 {doc['fingerprint']}, {'재현 가능' if doc['reproducibility']['deterministic'] else '재현 불가 해(시간 제한)'})")
    if problems:
        for k, v in problems.items():
            for e in v:
                print(f"[21] {k}: {e}", file=sys.stderr)
        print(f"[21] 캐시가 지금 그래프와 안 맞는 권역: {', '.join(problems)} → python3 pipeline/20_solve_schematic.py --regions {','.join(problems)}",
              file=sys.stderr)
        return 1
    Path(a.out).write_text(json.dumps(web, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"[21] wrote {Path(a.out).relative_to(ROOT) if Path(a.out).is_relative_to(ROOT) else a.out}: 권역 {len(web['regions'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
