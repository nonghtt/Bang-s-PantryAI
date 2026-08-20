# -*- coding: utf-8 -*-
"""재고 커버리지 측정 — 상비 재료만으로, 또는 하나만 더 사면 만들 수 있는 레시피 수.

정규화 전후를 **같은 자로** 재기 위한 스크립트다. 기존 기준선(7.4%)은
1,725건 코퍼스에 부분문자열 매칭으로 일회성 계산한 값이라 정규화 후
수치와 직접 비교할 수 없다. 코퍼스와 방법을 고정하고 매칭 방식만 바꾼다.

    python scripts/measure_coverage.py                    # 정규화 전 (원본 표기)
    python scripts/measure_coverage.py --normalized FILE  # 정규화 후

`--normalized` 는 `source,source_id,seq,name_raw,표준명` 컬럼을 가진 CSV를 받는다.
파일에 없는 행은 정답 세트의 이름 단위 매핑으로 보충한다.

표준 라이브러리만 사용한다.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANTRY = ROOT / "data" / "labels" / "pantry_assumption.txt"
ANSWERS = ROOT / "data" / "labels" / "ingredient_standard_answers.csv"
ROW_ANSWERS = ROOT / "data" / "labels" / "context_dependent_rows.csv"
INGREDIENTS = ROOT / "data" / "processed" / "recipe_ingredients.json"
RECIPES = ROOT / "data" / "processed" / "recipes.json"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def load_pantry():
    """[상비]/[자주]/[제외] 섹션을 읽는다."""
    section, out = None, defaultdict(list)
    for line in PANTRY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section:
            out[section].append(line)
    return set(out["상비"]) | set(out["자주"]), set(out["제외"])


def load_name_map():
    """재료명 → 표준명 (이름 단위)."""
    return {r["재료명"]: r["표준명"].strip()
            for r in csv.DictReader(ANSWERS.open(encoding="utf-8-sig"))
            if r["판정"].strip() != "제외"}


def load_row_map():
    """(source, source_id, seq) → 표준명 (행 단위, 이름 단위보다 우선)."""
    if not ROW_ANSWERS.exists():
        return {}
    out = {}
    for r in csv.DictReader(ROW_ANSWERS.open(encoding="utf-8-sig")):
        if r.get("확정", "").strip():
            for seq in str(r["seq"]).split(";"):
                if seq.strip():
                    out[(r["source"], str(r["source_id"]), seq.strip())] = r["확정"].strip()
    return out


def measure(rows_by_recipe, recipes, pantry, excluded, resolve):
    """resolve(row) -> 비교에 쓸 이름. None 이면 그 행을 무시한다."""
    stat = defaultdict(lambda: Counter())
    missing_counter = Counter()
    reachable_ids = set()
    for key, rows in rows_by_recipe.items():
        rec = recipes.get(key)
        if not rec:
            continue
        need = set()
        for r in rows:
            if (r.get("role_raw") or "") == "양념":
                continue
            name = resolve(r)
            if name is None or name in excluded or name in pantry:
                continue
            need.add(name)
        src = key[0]
        cat = rec.get("ty_nm") or rec.get("rcp_pat2") or "미분류"
        for scope in (src, "합계"):
            stat[scope]["건수"] += 1
            if not need:
                stat[scope]["완전"] += 1
            elif len(need) == 1:
                stat[scope]["1개부족"] += 1
        if len(need) <= 1:
            reachable_ids.add(key)
            stat["cat:" + cat]["도달"] += 1
        stat["cat:" + cat]["건수"] += 1
        if len(need) == 1:
            missing_counter[next(iter(need))] += 1
    return stat, missing_counter, reachable_ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--normalized", metavar="CSV",
                    help="정규화 산출물. 없으면 원본 표기로 측정한다")
    ap.add_argument("--strict", action="store_true",
                    help="정규화 전을 정확 일치로 측정. 부분문자열 매칭이 이미 내던 "
                         "정규화 효과를 걷어낸 진짜 하한선")
    args = ap.parse_args()

    pantry, excluded = load_pantry()
    ing = json.load(INGREDIENTS.open(encoding="utf-8"))
    recipes = {(r["source"], r["source_id"]): r
               for r in json.load(RECIPES.open(encoding="utf-8"))}
    by_recipe = defaultdict(list)
    for x in ing:
        if x.get("name_raw"):
            by_recipe[(x["source"], x["source_id"])].append(x)

    if args.normalized:
        name_map, row_map = load_name_map(), load_row_map()
        # 재고 목록도 같은 자로 접는다 — 김치는 표준명이 배추김치다
        pantry = {name_map.get(n, n) for n in pantry}
        excluded = {name_map.get(n, n) for n in excluded}
        supplied = {}
        for r in csv.DictReader(Path(args.normalized).open(encoding="utf-8-sig")):
            if r.get("표준명", "").strip():
                supplied[(r["source"], str(r["source_id"]), str(r["seq"]))] = r["표준명"].strip()
        covered = {(k[0], k[1]) for k in supplied}

        def resolve(r):
            key = (r["source"], str(r["source_id"]), str(r["seq"]))
            return (row_map.get(key) or supplied.get(key)
                    or name_map.get(r["name_raw"]) or r["name_raw"])

        mode = "정규화 후"
        note = "산출물 %d행 · 레시피 %d건 반영, 나머지는 이름 단위 매핑" % (len(supplied), len(covered))
    else:
        if args.strict:
            def resolve(r):
                return r["name_raw"]

            mode = "정규화 전 (원본 표기 · 정확 일치)"
            note = "부분문자열 매칭이 내던 효과를 걷어낸 하한선"
        else:
            def resolve(r):
                n = r["name_raw"]
                # 기존 기준선의 방식 재현 — 재고 이름을 부분문자열로 포함하면 보유로 본다
                for p in pantry:
                    if p in n:
                        return p
                return n

            mode = "정규화 전 (원본 표기 · 부분문자열 매칭)"
            note = "기존 기준선과 같은 방식"

    stat, missing, _ = measure(by_recipe, recipes, pantry, excluded, resolve)

    print("■ %s" % mode)
    print("  %s" % note)
    print("  재고 %d종 · 제외 %d종\n" % (len(pantry), len(excluded)))
    print("| 코퍼스 | 건수 | 완전 매칭 | 1개 부족 | 도달 가능 |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for scope, label in (("nongjeongwon", "농정원"), ("mfds", "식약처"), ("합계", "**병합**")):
        s = stat[scope]
        n, full, one = s["건수"], s["완전"], s["1개부족"]
        print("| %s | %d | %d | %d | **%.1f%%** |"
              % (label, n, full, one, 100 * (full + one) / n if n else 0))

    print("\n카테고리별 도달 가능 (상위 12)")
    cats = [(k[4:], v["도달"], v["건수"]) for k, v in stat.items() if k.startswith("cat:")]
    for c, reach, n in sorted(cats, key=lambda x: -x[1])[:12]:
        print("   %-16s %3d / %-4d  %5.1f%%" % (c, reach, n, 100 * reach / n if n else 0))

    print("\n하나만 사면 열리는 재료 (상위 12)")
    for name, c in missing.most_common(12):
        print("   %-14s %d건" % (name, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
