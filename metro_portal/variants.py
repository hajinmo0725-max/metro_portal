"""T2 이체자 정규화 (DESIGN 5.3). 3차 B2. 규칙 값은 전부 ruleset의 tier 설정(variant_fold)에서 받는다.

fold(text) = OpenCC 변환 사슬(설정 순서대로) → 글자마다 Unihan 이체자 클래스의 대표 글자.
- Unihan: 설정한 필드(kTraditionalVariant 등)의 관계로 union-find를 만들고 대표는 클래스에서 가장 작은 코드포인트.
- 과병합 방어: 클래스 크기가 max_class_size를 넘으면 그 클래스는 접지 않는다 (글자 그대로).
- 결정적이다 (파일 순서와 무관하게 대표 = 최소 코드포인트).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from . import ROOT

_CP = re.compile(r"U\+([0-9A-F]{4,6})")


def load_unihan_pairs(path: Path, fields: list[str]) -> list[tuple[str, str, str]]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            cp, field, value = line.rstrip("\n").split("\t", 2)
            if field not in fields:
                continue
            a = chr(int(cp[2:], 16))
            for m in _CP.finditer(value):
                out.append((a, chr(int(m.group(1), 16)), field))
    return out


class VariantFolder:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.chain = []
        if cfg.get("opencc"):
            import opencc
            self.chain = [opencc.OpenCC(c) for c in cfg["opencc"]]
        path = ROOT / cfg.get("unihan_file", "data/raw/unihan/Unihan_Variants.txt")
        fields = cfg.get("unihan_fields", [])
        parent: dict[str, str] = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        if fields:
            if not path.exists():
                raise FileNotFoundError(f"{path} 없음 — pipeline/16_fetch_unihan.py 먼저")
            for a, b, _ in load_unihan_pairs(path, fields):
                ra, rb = find(a), find(b)
                if ra != rb:
                    if rb < ra:
                        ra, rb = rb, ra
                    parent[rb] = ra
        classes: dict[str, list[str]] = {}
        for ch in list(parent):
            classes.setdefault(find(ch), []).append(ch)
        cap = cfg.get("max_class_size")
        self.rep, self.class_size, self.skipped_classes = {}, {}, []
        for root, members in classes.items():
            members.sort()
            if cap and len(members) > cap:
                self.skipped_classes.append("".join(members))
                continue
            for ch in members:
                self.rep[ch] = members[0]
                self.class_size[ch] = len(members)

    def convert(self, text: str) -> str:
        for c in self.chain:
            text = c.convert(text)
        return text

    def fold(self, text: str) -> str:
        return "".join(self.rep.get(ch, ch) for ch in self.convert(text))


@lru_cache(maxsize=8)
def _cached(key):
    import json
    return VariantFolder(json.loads(key))


def folder_for(cfg: dict) -> VariantFolder:
    import json
    return _cached(json.dumps(cfg, sort_keys=True, ensure_ascii=False))
