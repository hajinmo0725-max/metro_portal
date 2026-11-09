"""5차 R4: 도식 라벨 배치가 노선 선분을 피한다 (web/schematic_core.js placeLabels와 같은 규칙의 Python 판)."""
from metro_portal import schematic as S


def test_label_avoids_segments():
    st = [{"p": (100, 100), "dir": (1, 0), "text": "가나다라마", "size": 10, "big": False}]
    segs = [(0, 100, 300, 100), (0, 86, 300, 86), (0, 114, 300, 114), (100, 95, 160, 35)]
    out = S.place_labels(st, segments=segs)
    assert S.label_stats(out, segs)["on_line"] == 0
    old = S.place_labels(st)          # 선분 비용 없이 → 선 위에 걸친다
    assert any(S.seg_in_label(old[0], sg) > 2 for sg in segs)


def test_seg_in_label_rotated():
    c = {"ox": 0, "oy": 0, "rot": -45, "r": (0, -2, 40, 2)}
    assert S.seg_in_label(c, (0, 0, 40, -40)) > 39
    assert S.seg_in_label(c, (0, 10, 40, 10)) == 0


def test_python_js_same_candidates_order():
    """두 구현의 후보 순서가 같아 같은 입력에서 같은 앵커·회전을 고른다 (node 테스트와 같은 입력)."""
    st = [{"p": (100, 100), "dir": (0, 1), "text": "가나다라", "size": 10, "big": False},
          {"p": (100, 104), "dir": (0, 1), "text": "마바사아", "size": 10, "big": False}]
    out = S.place_labels(st)
    ov = lambda a, b: max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))  # noqa: E731
    assert ov(out[0]["box"], out[1]["box"]) == 0


def test_python_and_js_label_placement_agree():
    """웹(schematic_core.js placeLabels)과 SVG(schematic.py place_labels)가 같은 입력에서 같은 앵커·회전·위치를 고른다."""
    import json
    import shutil
    import subprocess
    from pathlib import Path
    import pytest
    if not shutil.which("node"):
        pytest.skip("node 없음")
    root = Path(__file__).resolve().parent.parent
    st = [{"p": [100 + 23 * (i % 7), 100 + 17 * (i // 7)], "dir": [1, 0] if i % 3 else [0.7071, 0.7071], "text": "역" * (2 + i % 4),
           "size": 10 if i % 2 else 12, "big": i % 5 == 0} for i in range(28)]
    segs = [[90, 100 + 17 * k, 260, 100 + 17 * k] for k in range(4)] + [[100 + 23 * k, 90, 100 + 23 * k, 170] for k in range(0, 7, 2)]
    js = f"""import('{(root / 'web' / 'schematic_core.js').as_uri()}').then(m => {{
      const out = m.placeLabels({json.dumps(st)}, {{segments: {json.dumps(segs)}}});
      console.log(JSON.stringify(out.map(o => [o.anchor, o.rot, Math.round(o.x * 100) / 100, Math.round(o.y * 100) / 100])));
    }})"""
    res = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    py = S.place_labels([{**x, "p": tuple(x["p"]), "dir": tuple(x["dir"])} for x in st], segments=[tuple(s) for s in segs])
    assert [[o["anchor"], o["rot"], round(o["x"], 2), round(o["y"], 2)] for o in py] == res
