#!/usr/bin/env python3
"""4차 S3·S5, 5차 R3. 권역별 도식 노선도 (octilinear) 풀이 = 재계산 스크립트.

5차 R3부터 풀이와 웹 빌드를 나눴다. 이 단계는 MIP를 풀어 캐시(data/processed/schematic/<권역>.json)를 쓰고,
웹 번들·SVG는 21 단계(pipeline/21_build_schematic_web.py)가 이 캐시만 읽어서 만든다. build_all.sh는 21만 돈다.
이유: 수도권처럼 시간 제한(벽시계)에 걸린 해는 기계 속도에 따라 달라서 재현되지 않는다. 그래서 풀이 결과를 커밋해 둔다.

결정성: HiGHS 단일 스레드·고정 시드(random_seed). 시간 제한에 안 걸리고 끝난 권역(최적·갭·노드 제한 도달)은 같은 HiGHS 버전에서
재현된다. 걸린 권역은 캐시의 reproducibility.deterministic = false로 표시한다.
캐시마다 입력 지문(fingerprint: 그래프 + 모델 파라미터)을 넣는다. 그래프가 바뀌면 21이 지문 불일치로 멈춘다 → 이 스크립트로 다시 푼다.

엔진: 자체 MIP (metro_portal/schematic.py, Nöllenburg & Wolff 2011식, HiGHS). 공식 노선도·역 배치는 쓰지 않는다.

입력: config/schematic.yaml, data/processed/{kr,tw}
출력: data/processed/schematic/<region>.json, data/processed/schematic/summary.json, data/processed/schematic/build_log.txt
      (수도권 파라미터 비교 변형: data/processed/schematic/variant_seoul_<X>.json, docs/reports/schematic/seoul_<X>.svg)
사용: python3 pipeline/20_solve_schematic.py [--regions seoul,busan] [--skip-variants] [--time-limit S]
      python3 pipeline/20_solve_schematic.py --adopt seoul   # 기존 캐시 좌표가 지금 그래프와 맞는지 확인하고 지문만 찍는다
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metro_portal import ROOT  # noqa: E402
from metro_portal import schematic as S  # noqa: E402
from metro_portal.ruleset import load_ruleset  # noqa: E402
from metro_portal.world import build_world, load_base, load_multi  # noqa: E402

OUT = ROOT / "data" / "processed" / "schematic"
REP = ROOT / "docs" / "reports" / "schematic"


def region_cfg(cfg: dict, reg: dict) -> dict:
    return S.region_params(cfg, reg)


def worlds(cfg):
    """권역 country별 그래프 (한국 = strict, 타이베이 = tw_t12의 KR+TW 그래프). 필요할 때 만든다."""
    cache = {}

    def get(country):
        if country not in cache:
            if country == "TW":
                cache[country] = build_world(*load_multi(("KR", "TW")), load_ruleset("tw_t12"))
            else:
                cache[country] = build_world(*load_base(), load_ruleset(cfg["ruleset"]))
        return cache[country]
    return get


def checkpointer(ckdir: Path, g, cg, log, offset: int = 0):
    """5차 R4 중간 저장: 반복마다 iter_<k>.json, 반복 안 개선해마다 incumbent.json (data/raw 아래, gitignore).
    offset: 이어 풀기면 앞 실행의 마지막 반복 번호 (번호를 이어서 매겨 앞 체크포인트를 덮어쓰지 않는다)."""
    ckdir.mkdir(parents=True, exist_ok=True)
    best = {"key": None}

    def dump(name, it, pos_kept, status, obj, added=None, dirs=None, violations=None):
        pos = S.expand(g, cg, pos_kept)
        st = S.layout_stats(g, pos)
        doc = {"iteration": it, "status": status, "objective": obj, "stats": st, "violations": violations,
               "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               # 5차: 남긴 정점 좌표는 원래 정밀도로 (반올림하면 8방향 검사 허용오차 1e-6을 넘는다)
               "pos_kept": {k: [v[0], v[1]] for k, v in sorted(pos_kept.items())},
               "added": [[list(a), list(b)] for a, b in (added or [])],
               "dirs": [[list(e), i] for e, i in sorted((dirs or {}).items())],
               "pos": {k: [round(v[0], 4), round(v[1], 4)] for k, v in sorted(pos.items())}}
        (ckdir / name).write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
        return st

    def on_iteration(it, pos_kept, added, status, obj, dirs, violations=None):
        it += offset
        st = dump(f"iter_{it:02d}.json", it, pos_kept, status, obj, added, dirs, violations)
        key = (st["crossings"], st["bend_units_45deg"])
        log(f"    [중간 저장] iter_{it:02d}.json: 교차 {st['crossings']}, 굴곡 {st['bend_units_45deg']}, 목적 {obj:.2f}")
        if best["key"] is None or key < best["key"]:
            best["key"] = key

    def on_incumbent(it, pos_kept, obj):
        it += offset
        st = dump("incumbent.json", it, pos_kept, f"반복 {it} 진행 중 개선해", obj)
        log(f"    [중간 저장] incumbent.json (반복 {it}): 목적 {obj:.2f}, 교차 {st['crossings']}, 굴곡 {st['bend_units_45deg']}")
    return on_iteration, on_incumbent


def load_resume(ckdir: Path):
    """가장 마지막 iter_<k>.json에서 교차 제약 쌍과 방향을 읽는다."""
    its = sorted(ckdir.glob("iter_*.json"))
    if not its:
        return None, None
    doc = json.loads(its[-1].read_text(encoding="utf-8"))
    added = [(tuple(a), tuple(b)) for a, b in doc["added"]]
    return {"dirs": {tuple(e): i for e, i in doc["dirs"]}}, added


def best_iteration(ckdir: Path, g):
    """체크포인트 반복 중 (교차, 남은 평면성·간격 위반 쌍, 굴곡) 사전식 최소 해. 위반 쌍 기록이 없으면(5차 초기 체크포인트) 큰 값으로 본다."""
    cands = []
    for p in sorted(ckdir.glob("iter_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        v = d.get("violations")
        cands.append(((d["stats"]["crossings"], 10 ** 6 if v is None else v, d["stats"]["bend_units_45deg"], -d["iteration"]), p.name, d))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    return cands[0][2]


def polish(g, cg, rcfg, ck, log):
    """체크포인트 반복의 엣지 방향과 교차 제약을 고정하고 좌표만 다시 푼다 (정확한 8방향 좌표 복원).
    방향이 다 정해져 있어 남는 정수변수는 순환 순서 β·교차 분리 γ뿐이라 빨리 끝난다."""
    allowed = {tuple(e): [i] for e, i in ck["dirs"]}
    added = [(tuple(a), tuple(b)) for a, b in ck["added"]]
    cfg = {**rcfg, "allowed": allowed, "max_iterations": 1, "warm_start": None, "time_limit_s": max(300, rcfg.get("time_limit_s", 60))}
    r = S.solve_octilinear(g, cg, cfg, log=log, init_added=added)
    if r["pos"]:
        r["status"] = f"반복 {ck['iteration']} 방향 고정 다듬기 ({r['status']}; 원래 {ck['status']})"
    return r


def run_region(w, reg, rcfg, log, ckdir: Path | None = None, resume=False):
    g = S.region_graph(w, reg["city"])
    cg = S.contract(g, keep_every=reg.get("keep_every", 2))
    t = time.time()
    log(f"[20] {reg['id']} ({reg['city']}): 역 {len(g['nodes'])}, 엣지 {len(g['edges'])} → 축약 {len(cg['nodes'])}/{len(cg['edges'])}")
    kw = {}
    if ckdir is not None:
        its = sorted(ckdir.glob("iter_*.json")) if resume else []
        offset = json.loads(its[-1].read_text(encoding="utf-8"))["iteration"] if its else 0
        kw["on_iteration"], kw["on_incumbent"] = checkpointer(ckdir, g, cg, log, offset)
        if resume:
            kw["start"], kw["init_added"] = load_resume(ckdir)
            if kw["start"]:
                log(f"[20] 이어 풀기: {ckdir} 마지막 반복의 방향 {len(kw['start']['dirs'])}개, 교차 제약 {len(kw['init_added'])}쌍")
    r = S.solve_octilinear(g, cg, rcfg, log=log, **kw)
    if ckdir is not None and r["pos"]:
        b = best_iteration(ckdir, g)
        last = S.layout_stats(g, S.expand(g, cg, r["pos"]))
        last_v = r.get("last_violations", 10 ** 6)
        if b and (b["stats"]["crossings"], b.get("violations") if b.get("violations") is not None else 10 ** 6, b["stats"]["bend_units_45deg"]) < (last["crossings"], last_v, last["bend_units_45deg"]):
            log(f"[20] 마지막 반복보다 체크포인트 반복 {b['iteration']}이 낫다 (교차 {b['stats']['crossings']}, 굴곡 {b['stats']['bend_units_45deg']}) → 그 방향으로 다듬는다")
            rp = polish(g, cg, rcfg, b, log)
            if rp["pos"]:
                rp["iteration_status"] = r.get("iteration_status", []) + rp.get("iteration_status", [])
                rp["time_limited"] = r.get("time_limited") or rp.get("time_limited")
                rp["iterations"], rp["crossing_constraints"] = r["iterations"], max(r["crossing_constraints"], rp["crossing_constraints"])
                r = rp
    if r["pos"]:
        pos = S.expand(g, cg, r["pos"])
        r["engine"] = "mip"
    elif reg.get("fallback", "snap-lp") == "snap-lp":
        # 시간 안에 MIP 실행 가능해를 못 찾음 → 방향 고정 LP 반복(snap-lp)으로 대체하고 표시 (octilinear·평면성 보장 없음)
        mip = r
        r = S.solve_snap_lp(g, cg, rcfg, log=log)
        r["status"] = f"MIP: {mip['status']} → snap-lp"
        r["iteration_status"], r["time_limited"] = mip.get("iteration_status", []), mip.get("time_limited", False)
        pos = S.expand(g, cg, r["pos"])
        r["engine"] = "snap-lp"
    else:
        pos = dict(g["pos"])
        r["engine"] = "geo-fallback"
    st = S.layout_stats(g, pos)
    st_geo = S.layout_stats(g, g["pos"])
    sec = round(time.time() - t, 1)
    log(f"[20] {reg['id']}: {r['status']} {sec}s 반복 {r['iterations']} 교차제약 {r['crossing_constraints']} → {st}")
    return g, cg, pos, r, st, st_geo, sec


def reproducibility(r, rcfg, adopted_note=None):
    limited = bool(r.get("time_limited"))
    return {"deterministic": not limited and not adopted_note,
            "reason": adopted_note or ("반복 중 시간 제한(벽시계)에 걸림 → 기계 속도에 따라 다를 수 있다" if limited
                                       else "시간 제한 전에 끝남 (최적·갭·노드 제한) → 같은 HiGHS 버전·설정이면 재현"),
            "iteration_status": r.get("iteration_status", []), "highs": S.highs_version(), "threads": 1,
            "random_seed": int(rcfg.get("random_seed", 7)), "time_limit_s": rcfg.get("time_limit_s"),
            "mip_max_nodes": rcfg.get("mip_max_nodes")}


def region_doc(reg, rcfg, g, cg, pos, r, st, st_geo, sec, fp, repro):
    return {"region": reg["id"], "city": reg["city"], "country": reg["country"], "params": rcfg, "keep_every": reg.get("keep_every", 2),
            "fingerprint": fp, "reproducibility": repro,
            "engine": r["engine"], "status": r["status"], "seconds": sec, "iterations": r["iterations"],
            "crossing_constraints": r["crossing_constraints"], "objective": r["objective"], "stats": st, "stats_geo": st_geo,
            "schematic": {k: [round(v[0], 3), round(v[1], 3)] for k, v in sorted(pos.items())},
            "geo": {k: [round(g["pos"][k][0], 4), round(g["pos"][k][1], 4)] for k in sorted(pos)},
            "edges": [[a_, b_, ls] for (a_, b_), ls in g["edges"].items()],
            "lines": g["lines"], "names": g["names"], "kept": cg["nodes"]}


def write_region(doc):
    (OUT / f"{doc['region']}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def summary_entry(doc):
    return {k: doc[k] for k in ("city", "country", "keep_every", "engine", "status", "seconds", "iterations", "crossing_constraints",
                                "objective", "stats", "stats_geo", "fingerprint", "reproducibility")}


def adopt(cfg, ids, log):
    """기존 캐시 좌표를 지금 그래프로 검증하고 지문을 찍는다 (재풀이 없이). 정점·엣지 집합이 다르면 거부."""
    get = worlds(cfg)
    out = {}
    for reg in cfg["regions"]:
        if reg["id"] not in ids:
            continue
        old = json.loads((OUT / f"{reg['id']}.json").read_text(encoding="utf-8"))
        g = S.region_graph(get(reg["country"]), reg["city"])
        cg = S.contract(g, keep_every=reg.get("keep_every", 2))
        rcfg = region_cfg(cfg, reg)
        if set(old["schematic"]) != set(g["nodes"]):
            raise SystemExit(f"[20] adopt {reg['id']}: 캐시 정점과 지금 그래프 정점이 다르다 — 다시 풀어야 한다")
        if sorted(tuple(e[:2]) for e in old["edges"]) != sorted(g["edges"]):
            raise SystemExit(f"[20] adopt {reg['id']}: 캐시 엣지와 지금 그래프 엣지가 다르다 — 다시 풀어야 한다")
        if sorted(old["kept"]) != sorted(cg["nodes"]):
            raise SystemExit(f"[20] adopt {reg['id']}: 축약 결과가 다르다 — 다시 풀어야 한다")
        old["params"] = {**old.get("params", {}), **{k: v for k, v in rcfg.items() if k in S.BUDGET_KEYS and k not in old.get("params", {})}}
        old["fingerprint"] = S.fingerprint(g, cg, rcfg)
        old.setdefault("reproducibility", reproducibility({"time_limited": "Time limit" in old["status"]}, rcfg,
                                                          adopted_note="이전 세션 풀이 결과를 채택 (재풀이 없이 지문만 찍음)"))
        old["reproducibility"]["iteration_status"] = old["reproducibility"].get("iteration_status") or [old["status"]]
        write_region(old)
        out[reg["id"]] = old
        log(f"[20] adopt {reg['id']}: 지문 {old['fingerprint']} (정점 {len(g['nodes'])}, 엣지 {len(g['edges'])})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default=None)
    ap.add_argument("--skip-variants", action="store_true")
    ap.add_argument("--time-limit", type=float, default=None, help="모든 권역의 반복당 시간 제한 덮어쓰기 (빠른 시험용)")
    ap.add_argument("--only-variant", default=None, help="수도권 비교 변형 하나만 (이름 앞글자, 예: A). 권역 산출물은 건드리지 않는다")
    ap.add_argument("--merge-variants", action="store_true", help="variant_*.json을 summary.json에 합치기만 한다")
    ap.add_argument("--adopt", default=None, help="쉼표 구분 권역: 재풀이 없이 기존 캐시를 검증하고 지문만 찍는다")
    # 5차 R4: 장시간 풀이 (수도권). 예산 키만 바꾸므로 입력 지문은 그대로다
    ap.add_argument("--long", action="store_true", help="config/schematic.yaml long_run 예산(반복당 시간·반복 수·갭)과 웜스타트를 쓴다")
    ap.add_argument("--max-iterations", type=int, default=None)
    ap.add_argument("--gap", type=float, default=None, help="mip_rel_gap 덮어쓰기")
    ap.add_argument("--warm-start", default=None, help="geo-snap / none")
    ap.add_argument("--checkpoint", action="store_true", help="data/raw/schematic_runs/<권역>/에 반복·개선해마다 중간 저장")
    ap.add_argument("--resume", action="store_true", help="체크포인트 마지막 반복의 교차 제약·방향에서 이어 푼다 (--checkpoint 포함)")
    ap.add_argument("--tag", default=None, help="실험 실행 이름: 체크포인트를 schematic_runs/<권역>_<tag>/에 두고 결과도 거기 result.json에만 쓴다 (캐시 안 건드림)")
    ap.add_argument("--promote", default=None, help="<권역>:<tag> — 실험 실행 결과(result.json)를 캐시로 올린다")
    ap.add_argument("--polish", default=None, help="<권역>:<tag>:<반복> — 그 실험 실행의 반복 체크포인트 방향으로 좌표만 다시 풀어 result.json에 쓴다")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "config" / "schematic.yaml", encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    REP.mkdir(parents=True, exist_ok=True)
    logs = []

    def log(m):
        logs.append(m)
        print(m, flush=True)
    summ_path = OUT / "summary.json"
    olds = json.loads(summ_path.read_text(encoding="utf-8")) if summ_path.exists() else {}
    if a.merge_variants:
        olds["seoul_variants"] = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT.glob("variant_*.json"))]
        summ_path.write_text(json.dumps(olds, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"[20] merged {len(olds['seoul_variants'])} variants")
        return 0
    summary = {"engine": "own octilinear MIP (Nöllenburg & Wolff 2011 style, HiGHS via highspy)", "solver": cfg["solver"], "regions": {}}
    runs = ROOT / "data" / "raw" / "schematic_runs"
    if a.polish:
        rid, tag, itn = a.polish.split(":")
        reg = next(r for r in cfg["regions"] if r["id"] == rid)
        rcfg = region_cfg(cfg, reg)
        rcfg.update(reg.get("long_run") or {})
        d = runs / f"{rid}_{tag}"
        ck = json.loads((d / f"iter_{int(itn):02d}.json").read_text(encoding="utf-8"))
        w = worlds(cfg)(reg["country"])
        g = S.region_graph(w, reg["city"])
        cg = S.contract(g, keep_every=reg.get("keep_every", 2))
        t = time.time()
        r = polish(g, cg, rcfg, ck, log)
        if not r["pos"]:
            raise SystemExit(f"[20] polish 실패: {r['status']}")
        r["engine"] = "mip"
        old = json.loads((d / "result.json").read_text(encoding="utf-8")) if (d / "result.json").exists() else {}
        r["iteration_status"] = (old.get("reproducibility") or {}).get("iteration_status", []) + r.get("iteration_status", [])
        r["time_limited"] = True
        r["iterations"] = old.get("iterations", r["iterations"])
        pos = S.expand(g, cg, r["pos"])
        st, st_geo = S.layout_stats(g, pos), S.layout_stats(g, g["pos"])
        sec = round(time.time() - t + (old.get("seconds") or 0), 1)
        doc = region_doc(reg, rcfg, g, cg, pos, r, st, st_geo, sec, S.fingerprint(g, cg, rcfg), reproducibility(r, rcfg))
        (d / "result.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        log(f"[20] polish {rid}:{tag}:{itn} → {st}")
        return 0
    if a.promote:
        rid, tag = a.promote.split(":")
        doc = json.loads((runs / f"{rid}_{tag}" / "result.json").read_text(encoding="utf-8"))
        write_region(doc)
        summary["regions"][rid] = summary_entry(doc)
        log(f"[20] promote {rid}:{tag} → 캐시 (교차 {doc['stats']['crossings']}, 굴곡 {doc['stats']['bend_units_45deg']}, 지문 {doc['fingerprint']})")
        want = {rid}
        a.skip_variants = True
    elif a.adopt:
        for k, doc in adopt(cfg, set(a.adopt.split(",")), log).items():
            summary["regions"][k] = summary_entry(doc)
        want = set(a.adopt.split(","))
        a.skip_variants = True
    else:
        if a.only_variant:
            a.regions = "__none__"
        if a.time_limit:
            cfg["solver"]["time_limit_s"] = a.time_limit
            for r in cfg["regions"]:
                r.pop("time_limit_s", None)
        want = set(a.regions.split(",")) if a.regions else None
        get = worlds(cfg)
        for reg in cfg["regions"]:
            if want and reg["id"] not in want:
                continue
            rcfg = region_cfg(cfg, reg)
            if a.long:
                rcfg.update(reg.get("long_run") or {})
            for k, v in (("max_iterations", a.max_iterations), ("mip_rel_gap", a.gap)):
                if v is not None:
                    rcfg[k] = v
            if a.warm_start:
                rcfg["warm_start"] = None if a.warm_start == "none" else a.warm_start
            name = reg["id"] + (f"_{a.tag}" if a.tag else "")
            ckdir = (runs / name) if (a.checkpoint or a.resume or a.tag) else None
            g, cg, pos, r, st, st_geo, sec = run_region(get(reg["country"]), reg, rcfg, log, ckdir, a.resume)
            doc = region_doc(reg, rcfg, g, cg, pos, r, st, st_geo, sec, S.fingerprint(g, cg, rcfg), reproducibility(r, rcfg))
            if a.tag:   # 실험 실행: 캐시를 건드리지 않는다 (--promote로 올린다)
                (ckdir / "result.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                log(f"[20] {name}: 결과 {ckdir / 'result.json'} (캐시는 그대로)")
                continue
            write_region(doc)
            summary["regions"][reg["id"]] = summary_entry(doc)
    if a.only_variant or (not a.skip_variants and (not want or "seoul" in want)):
        reg0 = next(r for r in cfg["regions"] if r["id"] == "seoul")
        summary["seoul_variants"] = []
        for v in cfg.get("seoul_variants", []):
            if a.only_variant and not v["name"].startswith(a.only_variant):
                continue
            reg = {**reg0, **{k: x for k, x in v.items() if k != "name"}, "id": "seoul_" + v["name"].split()[0]}
            rcfg = region_cfg(cfg, reg)
            g, cg, pos, r, st, st_geo, sec = run_region(worlds(cfg)("KR"), reg, rcfg, log)
            (REP / f"{reg['id']}.svg").write_text(S.render_svg(g, pos, f"수도권 비교 {v['name']} (keep={reg['keep_every']}, bend={rcfg['w_bend']}, dir={rcfg['w_dir']})", size=1100), encoding="utf-8")
            summary["seoul_variants"].append({"name": v["name"], "id": reg["id"], "params": {k: rcfg[k] for k in ("w_bend", "w_dir")},
                                              "keep_every": reg["keep_every"], "status": r["status"], "seconds": sec, "engine": r["engine"],
                                              "iterations": r["iterations"], "stats": st})
            (OUT / f"variant_{reg['id']}.json").write_text(json.dumps(summary["seoul_variants"][-1], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.only_variant or (a.tag and not a.promote):
        with open(runs / "run_log.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(logs) + "\n")
        return 0
    # 일부 권역만 다시 풀었으면 기존 요약과 합친다
    for k, v in olds.get("regions", {}).items():
        summary["regions"].setdefault(k, v)
    if "seoul_variants" not in summary and "seoul_variants" in olds:
        summary["seoul_variants"] = olds["seoul_variants"]
    order = [r["id"] for r in cfg["regions"]]
    summary["regions"] = {k: summary["regions"][k] for k in order if k in summary["regions"]}
    summ_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(OUT / "build_log.txt", "a", encoding="utf-8") as f:
        f.write("\n".join(logs) + "\n")
    print("[20] 캐시 갱신 완료 → 웹 번들은 python3 pipeline/21_build_schematic_web.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
