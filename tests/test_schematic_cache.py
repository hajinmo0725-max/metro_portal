"""5차 R3: 도식 풀이 캐시와 웹 빌드 분리 — 지문, 캐시 검증, 결정성."""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from metro_portal import schematic as S

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("w21", ROOT / "pipeline" / "21_build_schematic_web.py")
w21 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w21)


def toy_graph():
    """ㄱ자 노선 하나 + 가지 하나 (정점 6)."""
    nodes = ["a", "b", "c", "d", "e", "f"]
    pos = {"a": (0.0, 0.0), "b": (1.0, 0.1), "c": (2.0, 0.0), "d": (2.1, 1.0), "e": (2.0, 2.0), "f": (3.0, 0.0)}
    edges = {("a", "b"): ["L1"], ("b", "c"): ["L1"], ("c", "d"): ["L1"], ("d", "e"): ["L1"], ("c", "f"): ["L2"]}
    seqs = [{"line": "L1", "nodes": ["a", "b", "c", "d", "e"], "circular": False}, {"line": "L2", "nodes": ["c", "f"], "circular": False}]
    return {"city": "toy", "nodes": nodes, "pos": pos, "edges": edges, "seqs": seqs,
            "lines": {"L1": {"name": "1", "color": "#f00"}, "L2": {"name": "2", "color": "#00f"}},
            "names": {v: v.upper() for v in nodes}, "origin": (0, 0)}


CFG = {"grid_edge": 4.0, "min_edge": 2.0, "chain_len_factor": 0.6, "w_bend": 1.0, "w_dir": 2.0, "w_len": 0.05, "min_sep": 1.5,
       "time_limit_s": 30, "max_iterations": 6, "mip_rel_gap": 0.0, "order": "hard", "w_order": 20.0, "span_factor": 1.0,
       "scale_by": "mean", "mip_heuristic_effort": 0.05, "pos_window": None, "geo_len_factor": 0.5}


def test_fingerprint_changes_with_graph_and_model_not_budget():
    g = toy_graph()
    cg = S.contract(g, keep_every=2)
    fp = S.fingerprint(g, cg, CFG)
    assert fp == S.fingerprint(copy.deepcopy(g), S.contract(copy.deepcopy(g), keep_every=2), dict(CFG))
    # 예산 키(시간 제한·반복 수·갭·노드 제한)는 문제 정의가 아니라서 지문이 같다
    assert fp == S.fingerprint(g, cg, {**CFG, "time_limit_s": 999, "max_iterations": 2, "mip_rel_gap": 0.3, "mip_max_nodes": 100})
    # 모델 파라미터가 바뀌면 다르다
    assert fp != S.fingerprint(g, cg, {**CFG, "w_dir": 4.0})
    # 엣지가 하나 빠지면 다르다
    g2 = copy.deepcopy(g)
    del g2["edges"][("c", "f")]
    assert fp != S.fingerprint(g2, S.contract(g2, keep_every=2), CFG)
    # 역 이름은 표시용이라 지문에 안 들어간다 (5차 R2 표기 변경이 캐시를 깨지 않게)
    g3 = copy.deepcopy(g)
    g3["names"]["a"] = "다른이름"
    assert fp == S.fingerprint(g3, cg, CFG)


def test_toy_solve_is_reproducible():
    g = toy_graph()
    cg = S.contract(g, keep_every=2)
    r1 = S.solve_octilinear(g, cg, CFG)
    r2 = S.solve_octilinear(copy.deepcopy(g), S.contract(copy.deepcopy(g), keep_every=2), dict(CFG))
    assert r1["pos"] and r1["pos"] == r2["pos"]
    assert not r1["time_limited"]
    assert S.layout_stats(g, S.expand(g, cg, r1["pos"]))["non_octilinear_edges"] == 0


def test_check_cache_detects_stale():
    g = toy_graph()
    cg = S.contract(g, keep_every=2)
    doc = {"fingerprint": S.fingerprint(g, cg, CFG), "schematic": {v: [0, 0] for v in g["nodes"]}}
    assert w21.check_cache({}, CFG, g, cg, doc) == []
    g2 = copy.deepcopy(g)
    g2["nodes"].append("z")
    g2["pos"]["z"] = (5.0, 5.0)
    g2["edges"][("f", "z")] = ["L2"]
    errs = w21.check_cache({}, CFG, g2, S.contract(g2, keep_every=2), doc)
    assert any("지문 불일치" in e for e in errs) and any("정점 집합" in e for e in errs)
    assert any("지문이 없다" in e for e in w21.check_cache({}, CFG, g, cg, {"schematic": doc["schematic"]}))


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "kr" / "stations.json").exists(), reason="processed 데이터 없음")
def test_web_bundle_from_cache_matches_committed(tmp_path):
    """21 단계는 캐시만 읽으므로 두 번 돌려도, 커밋된 번들과도 바이트 단위로 같다."""
    out1, out2 = tmp_path / "a.json", tmp_path / "b.json"
    for out in (out1, out2):
        subprocess.run([sys.executable, str(ROOT / "pipeline" / "21_build_schematic_web.py"), "--no-svg", "--out", str(out)],
                       check=True, capture_output=True, cwd=ROOT)
    assert out1.read_bytes() == out2.read_bytes() == (ROOT / "web" / "data" / "schematic.json").read_bytes()


def test_cache_files_carry_fingerprint_and_repro_flag():
    cfg = yaml.safe_load(open(ROOT / "config" / "schematic.yaml", encoding="utf-8"))
    for reg in cfg["regions"]:
        doc = json.loads((ROOT / "data" / "processed" / "schematic" / f"{reg['id']}.json").read_text(encoding="utf-8"))
        assert len(doc["fingerprint"]) == 16
        rp = doc["reproducibility"]
        assert rp["threads"] == 1 and isinstance(rp["deterministic"], bool)
        # 시간 제한에 걸린 반복이 있으면 재현 불가로 표시돼야 한다
        if any("Time limit" in s for s in rp["iteration_status"]):
            assert rp["deterministic"] is False
