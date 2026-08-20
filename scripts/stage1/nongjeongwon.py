# -*- coding: utf-8 -*-
"""농정원 원천 데이터 1단계 정제 규칙.

판단이 들어가는 작업(표준화·주재료 판정·분류)은 여기서 하지 않는다.
"""
import re

GROUP_HEADER_RE = re.compile(r"^\[\s*(.+?)\s*\]\s*(.*)$")

# 명백한 오탈자만 교정한다. 이 목록 밖은 손대지 않는다.
TYPO_MAP = {
    "돼기고기": "돼지고기",
    "고추가루": "고춧가루",
    "다진생각": "다진생강",
    "다진식파": "다진실파",
}

# 한 칸에 여러 재료가 들어간 행. 원천 스냅샷에서 관측된 8종만 명시적으로 분해한다.
# 구분자 일반 규칙으로 처리하면 '노랑/빨강 파프리카'가 '노랑'으로 잘리므로 표로 고정한다.
MULTI_INGREDIENT_MAP = {
    "식용유/소금/참기름/잣가루": ["식용유", "소금", "참기름", "잣가루"],
    "빨강파프리카·노랑 파프리카·청피망": ["빨강파프리카", "노랑 파프리카", "청피망"],
    "후추, 식용유": ["후추", "식용유"],
    "무,래디쉬": ["무", "래디쉬"],
    "홍피망, 청피망 각각": ["홍피망", "청피망"],
    "노랑/빨강 파프리카": ["노랑 파프리카", "빨강 파프리카"],
    "굵은소금·후춧가루": ["굵은소금", "후춧가루"],
    "소금, 후추": ["소금", "후추"],
}

DELIMITER_RE = re.compile(r"[/,·]")


def split_group_header(name):
    """'[쇠고기양념] 다진파' -> ('쇠고기양념', '다진파')"""
    m = GROUP_HEADER_RE.match(name.strip())
    if not m:
        return (None, name)
    return (m.group(1), m.group(2))


def fix_typo(name):
    """(교정된 이름, 적용된 오탈자 키 or None)"""
    if name in TYPO_MAP:
        return (TYPO_MAP[name], name)
    return (name, None)


def split_multi_ingredient(name):
    """표에 있는 복수 재료 행만 분해한다. 그 외는 원본 1행 그대로."""
    if name in MULTI_INGREDIENT_MAP:
        return list(MULTI_INGREDIENT_MAP[name])
    return [name]


def has_unhandled_delimiter(name):
    """표에 없는데 구분자를 품은 재료명 — 원천이 갱신되면 보고서에 드러나야 한다."""
    return name not in MULTI_INGREDIENT_MAP and bool(DELIMITER_RE.search(name))


def trim_name(name):
    """앞뒤 공백만 제거한다. 내부 공백은 표준화 영역이므로 건드리지 않는다."""
    return name.strip()


def expand_ingredient_row(row):
    """원천 재료 1행 -> 정제된 재료 행 목록 (복수 재료면 여러 행)."""
    group_name, rest = split_group_header(trim_name(row["IRDNT_NM"]))
    qty = trim_name(row.get("IRDNT_CPCTY") or "") or None
    role = trim_name(row.get("IRDNT_TY_NM") or "") or None

    out = []
    for name in split_multi_ingredient(trim_name(rest)):
        fixed, typo_from = fix_typo(trim_name(name))
        out.append({
            "group_name": group_name,
            "name_raw": fixed,
            "qty_raw": qty,
            "role_raw": role,
            "typo_from": typo_from,
        })
    return out
