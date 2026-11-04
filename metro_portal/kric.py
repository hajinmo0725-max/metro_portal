"""레일포털 표준데이터 XLSX 리더. 열 이름으로 읽어서 열 순서 변경에 덜 민감하게 한다."""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import openpyxl


def read_sheet(path: Path, sheet_index: int = 0) -> list[dict]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[sheet_index]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else f"_col{i}" for i, h in enumerate(next(rows))]
    out = []
    for r in rows:
        if r is None or all(v is None for v in r):
            continue
        out.append({h: v for h, v in zip(header, r)})
    wb.close()
    return out


def clean_text(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


_CODE = re.compile(r"^([A-Za-z]*)0*(\d+)((?:-\d+)*)$")


def code_key(code: str) -> str:
    """역번호 비교 키. 'D007'·'D07' → 'D7', '0522'·'522' → '522', '211-1' → '211-1'."""
    c = clean_text(code).upper()
    m = _CODE.match(c)
    if not m:
        return c
    return f"{m.group(1)}{int(m.group(2))}{m.group(3)}"


def region_of(address: str) -> str:
    a = clean_text(address)
    return a.split(" ")[0] if a else ""
