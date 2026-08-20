# -*- coding: utf-8 -*-
"""PantryAI 원천 데이터 1단계 정제 — data/raw -> data/processed.

두 공공 API의 서로 다른 구조를 같은 모양으로 맞추는 것까지만 한다.
표준화·주재료 판정·카테고리 부여·중복 판정은 하지 않는다 (2단계).

재실행 가능하다. `python scripts/build_processed.py` 한 번으로 산출물이 다시 만들어진다.
"""
import io
import json
import os
import re
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stage1 import mfds, nongjeongwon as nj

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
ORPHANS = os.path.join(OUT, "orphans")

MAX_MANUAL = 20


def load(name):
    with io.open(os.path.join(RAW, name), encoding="utf-8") as f:
        return json.load(f)


def dump(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
        f.write("\n")


def blank_to_none(value):
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else value
    return text if text not in ("", None) else None


def recipe_row(**kwargs):
    """두 소스가 같은 열 구성을 갖도록 고정 순서의 레코드를 만든다."""
    keys = [
        "source", "source_id", "name", "summary", "image_url",
        "nation_nm", "ty_nm", "cooking_time", "level_nm", "servings", "calorie", "price",
        "rcp_pat2", "rcp_way2", "info_eng", "info_car", "info_pro", "info_fat", "info_na",
        "info_wgt", "hash_tag", "servings_raw",
    ]
    row = OrderedDict((k, None) for k in keys)
    row.update(kwargs)
    return row


# --------------------------------------------------------------------------- 농정원


def build_nongjeongwon(stats):
    basic = load("nongjeongwon_basic.json")
    ingredients = load("nongjeongwon_ingredient.json")
    steps = load("nongjeongwon_step.json")

    known_ids = set(r["RECIPE_ID"] for r in basic)
    stats["nj_input"] = {
        "basic": len(basic), "ingredient": len(ingredients), "step": len(steps)
    }
    stats["nj_basic_max_id"] = max(known_ids)

    recipes = []
    for r in basic:
        recipes.append(recipe_row(
            source="nongjeongwon",
            source_id=str(r["RECIPE_ID"]),
            name=blank_to_none(r["RECIPE_NM_KO"]),
            summary=blank_to_none(r["SUMRY"]),
            image_url=None,  # 수집분에 IMG_URL/DET_URL 컬럼 자체가 없다
            nation_nm=blank_to_none(r["NATION_NM"]),
            ty_nm=blank_to_none(r["TY_NM"]),
            cooking_time=blank_to_none(r["COOKING_TIME"]),
            level_nm=blank_to_none(r["LEVEL_NM"]),
            servings=blank_to_none(r["QNT"]),
            calorie=blank_to_none(r["CALORIE"]),
            price=blank_to_none(r["PC_NM"]),
        ))

    ing_rows = []
    orphan_ing = []
    typo_counter = Counter()
    split_counter = Counter()
    split_occurrences = Counter()
    orphan_split = Counter()
    unhandled_delimiter = []
    seq_by_recipe = Counter()

    # 원천 파일 순서(ROW_NUM)를 그대로 따른다. IRDNT_SN은 레시피별이 아니라 전역 일련번호다.
    for r in sorted(ingredients, key=lambda x: x["ROW_NUM"]):
        if r["RECIPE_ID"] not in known_ids:
            orphan_ing.append(r)
            if len(nj.split_multi_ingredient(nj.trim_name(r["IRDNT_NM"]))) > 1:
                orphan_split[nj.trim_name(r["IRDNT_NM"])] += 1
            continue
        name = nj.trim_name(r["IRDNT_NM"])
        _, bare = nj.split_group_header(name)
        expanded = nj.expand_ingredient_row(r)
        if len(expanded) > 1:
            split_counter[nj.trim_name(bare)] = len(expanded)
            split_occurrences[nj.trim_name(bare)] += 1
        if nj.has_unhandled_delimiter(nj.trim_name(bare)):
            unhandled_delimiter.append(name)
        for item in expanded:
            if item["typo_from"]:
                typo_counter[item["typo_from"]] += 1
            seq_by_recipe[r["RECIPE_ID"]] += 1
            ing_rows.append(OrderedDict([
                ("source", "nongjeongwon"),
                ("source_id", str(r["RECIPE_ID"])),
                ("seq", seq_by_recipe[r["RECIPE_ID"]]),
                ("group_name", item["group_name"]),
                ("name_raw", item["name_raw"]),
                ("qty_raw", item["qty_raw"]),
                ("role_raw", item["role_raw"]),
            ]))

    step_rows = []
    orphan_step = []
    step_no_by_recipe = Counter()
    cooking_no_by_recipe = {}
    # COOKING_NO는 중복·결번·재시작이 있어 정렬 키로 쓸 수 없다. 파일 순서를 유지하고 다시 매긴다.
    for r in sorted(steps, key=lambda x: x["ROW_NUM"]):
        if r["RECIPE_ID"] not in known_ids:
            orphan_step.append(r)
            continue
        step_no_by_recipe[r["RECIPE_ID"]] += 1
        cooking_no_by_recipe.setdefault(r["RECIPE_ID"], []).append(r["COOKING_NO"])
        step_rows.append(OrderedDict([
            ("source", "nongjeongwon"),
            ("source_id", str(r["RECIPE_ID"])),
            ("step_no", step_no_by_recipe[r["RECIPE_ID"]]),
            ("description", blank_to_none(r["COOKING_DC"])),
            ("tip", blank_to_none(r["STEP_TIP"])),
            ("image_url", None),
        ]))

    stats["nj"] = {
        "recipes": len(recipes),
        "ingredient_rows": len(ing_rows),
        "step_rows": len(step_rows),
        "orphan_ingredient_rows": len(orphan_ing),
        "orphan_step_rows": len(orphan_step),
        "orphan_ids": sorted(set(r["RECIPE_ID"] for r in orphan_ing + orphan_step)),
        "typos": typo_counter,
        "splits": split_counter,
        "split_occurrences": split_occurrences,
        "orphan_split": orphan_split,
        "unhandled_delimiter": unhandled_delimiter,
        "broken_cooking_no": sorted(
            (rid, nos) for rid, nos in cooking_no_by_recipe.items()
            if sorted(nos) != list(range(1, len(nos) + 1))
        ),
        "vague_qty": sum(
            1 for r in ing_rows if r["qty_raw"] in ("약간", "적당량")
        ),
    }
    return recipes, ing_rows, step_rows, orphan_ing, orphan_step


# --------------------------------------------------------------------------- 식약처


def build_mfds(stats):
    raw = load("mfds_recipes.json")
    stats["mfds_input"] = {"recipes": len(raw)}

    recipes, ing_rows, step_rows, unparsed = [], [], [], []
    manual_cells = 0
    step_no_gaps = []
    parsed_ok = 0

    for r in raw:
        result = mfds.parse_ingredients(r["RCP_PARTS_DTLS"], r["RCP_NM"])
        source_id = str(r["RCP_SEQ"])

        recipes.append(recipe_row(
            source="mfds",
            source_id=source_id,
            name=blank_to_none(r["RCP_NM"]),
            summary=blank_to_none(r["RCP_NA_TIP"]),
            image_url=blank_to_none(r["ATT_FILE_NO_MAIN"]),
            rcp_pat2=blank_to_none(r["RCP_PAT2"]),
            rcp_way2=blank_to_none(r["RCP_WAY2"]),
            info_eng=blank_to_none(r["INFO_ENG"]),
            info_car=blank_to_none(r["INFO_CAR"]),
            info_pro=blank_to_none(r["INFO_PRO"]),
            info_fat=blank_to_none(r["INFO_FAT"]),
            info_na=blank_to_none(r["INFO_NA"]),
            info_wgt=blank_to_none(r["INFO_WGT"]),
            hash_tag=blank_to_none(r["HASH_TAG"]),
            servings_raw=result.servings_raw,
        ))

        if result.items:
            parsed_ok += 1
        else:
            unparsed.append(OrderedDict([
                ("source_id", source_id),
                ("recipe_name", r["RCP_NM"]),
                ("kind", "recipe"),
                ("raw", r["RCP_PARTS_DTLS"]),
            ]))
        for i, item in enumerate(result.items, start=1):
            ing_rows.append(OrderedDict([
                ("source", "mfds"),
                ("source_id", source_id),
                ("seq", i),
                ("group_name", item.group_name),
                ("name_raw", item.name_raw),
                ("qty_raw", item.qty_raw),
                ("role_raw", None),
            ]))
        for fragment in result.unparsed:
            unparsed.append(OrderedDict([
                ("source_id", source_id),
                ("recipe_name", r["RCP_NM"]),
                ("kind", "fragment"),
                ("raw", fragment),
            ]))

        step_no = 0
        seen_empty = False
        for n in range(1, MAX_MANUAL + 1):
            description = blank_to_none(r["MANUAL%02d" % n])
            if description is None:
                seen_empty = True
                continue
            if seen_empty:
                step_no_gaps.append((source_id, n))
            manual_cells += 1
            step_no += 1
            step_rows.append(OrderedDict([
                ("source", "mfds"),
                ("source_id", source_id),
                ("step_no", step_no),
                ("description", mfds.strip_step_number(description)),
                ("tip", None),
                ("image_url", blank_to_none(r["MANUAL_IMG%02d" % n])),
            ]))

    stats["mfds"] = {
        "recipes": len(recipes),
        "ingredient_rows": len(ing_rows),
        "step_rows": len(step_rows),
        "manual_cells": manual_cells,
        "step_no_gaps": step_no_gaps,
        "parsed_ok": parsed_ok,
        "recipe_failures": sum(1 for u in unparsed if u["kind"] == "recipe"),
        "fragment_failures": sum(1 for u in unparsed if u["kind"] == "fragment"),
        "step_count_distribution": Counter(
            Counter(s["source_id"] for s in step_rows).values()
        ),
    }
    return recipes, ing_rows, step_rows, unparsed


# ------------------------------------------------------- 원천 결함 근사 측정 (기록용)


COOKING_NOISE = set([
    "재료", "준비", "그릇", "국물", "육수", "양념", "소스", "가루", "기름", "설탕", "소금",
    "간장", "식초", "참기름", "후추", "고명", "장식",
])


def step_only_ingredients(mfds_ing_rows, mfds_step_rows, vocabulary):
    """재료 목록에 없는데 조리과정에만 등장하는 재료를 근사 측정한다. 판정하지 않는다."""
    own = {}
    for row in mfds_ing_rows:
        own.setdefault(row["source_id"], set()).add(row["name_raw"])
    text = {}
    for row in mfds_step_rows:
        text[row["source_id"]] = text.get(row["source_id"], "") + " " + (row["description"] or "")

    findings = []
    for source_id, body in text.items():
        listed = own.get(source_id, set())
        if not listed:
            continue  # 재료를 한 행도 못 뽑은 레시피는 3절에서 이미 집계했다
        hits = set()
        for term in vocabulary:
            if term in body and not any(term in name or name in term for name in listed):
                hits.add(term)
        hits = set(t for t in hits if not any(t != o and t in o for o in hits))
        if len(hits) >= 3:
            findings.append((source_id, sorted(hits)))
    return sorted(findings, key=lambda x: -len(x[1]))


def build_vocabulary(all_ing_rows):
    counts = Counter(r["name_raw"] for r in all_ing_rows)
    vocab = set()
    for name, count in counts.items():
        if count < 5 or len(name) < 2 or len(name) > 5:
            continue
        if not all("가" <= ch <= "힣" for ch in name):
            continue
        if name in COOKING_NOISE:
            continue
        vocab.add(name)
    return vocab


# --------------------------------------------------------------------------- 보고서


def empty_field_table(rows, fields):
    total = len(rows)
    out = []
    for field in fields:
        empty = sum(1 for r in rows if r.get(field) in (None, ""))
        out.append((field, empty, total, (100.0 * empty / total) if total else 0.0))
    return out


DIRTY_NAME_CHECKS = (
    ("그룹 헤더가 이름에 붙음", re.compile(r"^(?:주재료|부재료|재료|양념장|양념|소스)\s+\S|^\(.*\)\s*\S|\S[ 	]{2,}\S")),
    ("레시피별 그룹 헤더 잔류",
     re.compile(r"^.*(?:양념장|양념|소스|육수용|육수|밑간|반죽|토핑|고명|장식|조림장|드레싱|국물|무침)\s+\S")),
    ("수량 수식어 잔류", re.compile(r"\s각각?$")),
    ("원문 번호마커 잔류", re.compile(r"[①-⑳]")),
    ("대괄호 잔류", re.compile(r"[\[\]]")),
)


def audit_names(ing_rows):
    """재료명에 남은 파싱 잔재를 센다. 고유명 기준이 2단계 정규화의 실제 부담이다."""
    out = {}
    for source in ("nongjeongwon", "mfds"):
        names = set(r["name_raw"] for r in ing_rows if r["source"] == source)
        hits = {}
        for label, pattern in DIRTY_NAME_CHECKS:
            hits[label] = sorted(n for n in names if pattern.search(n))
        unbalanced = sorted(n for n in names if n.count("(") != n.count(")"))
        if unbalanced:
            hits["괄호 짝 불일치"] = unbalanced
        dirty = set()
        for v in hits.values():
            dirty.update(v)
        rows = sum(1 for r in ing_rows if r["source"] == source and r["name_raw"] in dirty)
        out[source] = {"names": len(names), "dirty": dirty, "rows": rows, "by_check": hits}
    return out


def write_report(stats, recipes, ing_rows, step_rows, unparsed, mismatches):
    nj_s, mf_s = stats["nj"], stats["mfds"]
    nj_in, mf_in = stats["nj_input"], stats["mfds_input"]
    lines = []
    w = lines.append

    w("# 원천 데이터 1단계 정제 결과 보고서")
    w("")
    w("`scripts/build_processed.py` 실행 결과. 이 파일은 스크립트가 직접 생성한다.")
    w("")
    w("판단이 들어가는 작업(재료명 표준화, 주재료 판정, 카테고리 분류, 중복 판정, 데이터 생성)은")
    w("수행하지 않았다. 아래 수치는 전부 실측이다.")
    w("")

    w("## 1. 행 수 대조")
    w("")
    w("### 농정원")
    w("")
    w("| 원천 | 입력 | 출력 | 분해 증가 | 제외(고아) | 잔차 |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    split_gain = sum(
        (count - 1) * nj_s["split_occurrences"][name]
        for name, count in nj_s["splits"].items()
    )
    residual_ing = nj_in["ingredient"] - (
        nj_s["ingredient_rows"] - split_gain + nj_s["orphan_ingredient_rows"]
    )
    w("| basic | %d | %d | 0 | 0 | %d |" % (
        nj_in["basic"], nj_s["recipes"], nj_in["basic"] - nj_s["recipes"]))
    w("| ingredient | %d | %d | +%d | %d | %d |" % (
        nj_in["ingredient"], nj_s["ingredient_rows"], split_gain,
        nj_s["orphan_ingredient_rows"], residual_ing))
    w("| step | %d | %d | 0 | %d | %d |" % (
        nj_in["step"], nj_s["step_rows"], nj_s["orphan_step_rows"],
        nj_in["step"] - nj_s["step_rows"] - nj_s["orphan_step_rows"]))
    w("")
    w("### 식약처")
    w("")
    w("| 원천 | 입력 | 출력 | 잔차 |")
    w("| --- | ---: | ---: | ---: |")
    w("| 레시피 레코드 | %d | %d | %d |" % (
        mf_in["recipes"], mf_s["recipes"], mf_in["recipes"] - mf_s["recipes"]))
    w("| MANUAL 비어있지 않은 칸 | %d | %d | %d |" % (
        mf_s["manual_cells"], mf_s["step_rows"], mf_s["manual_cells"] - mf_s["step_rows"]))
    w("")
    w("재료는 원천이 행이 아니라 문자열 한 칸(`RCP_PARTS_DTLS`)이므로 행 수 대조 대상이 아니다. 3·4절 참조.")
    w("")
    w("### 제외한 행 — 농정원 고아 레시피 %d건" % len(nj_s["orphan_ids"]))
    w("")
    w("`ingredient`·`step`에는 있으나 `basic`에 없는 `RECIPE_ID`. 삭제하지 않고")
    w("`data/processed/orphans/`에 원본 그대로 보존했다. 처리 방침은 2단계에서 정한다.")
    w("")
    w("| RECIPE_ID | 재료 행 | 조리 행 |")
    w("| ---: | ---: | ---: |")
    for rid in nj_s["orphan_ids"]:
        w("| %s | %d | %d |" % (rid, stats["orphan_ing_by_id"].get(rid, 0),
                                stats["orphan_step_by_id"].get(rid, 0)))
    w("| **합계** | **%d** | **%d** |" % (
        nj_s["orphan_ingredient_rows"], nj_s["orphan_step_rows"]))
    w("")
    w("고아 ID는 %s~%s 연속 구간에 몰려 있다. `basic`은 ID 1~500을 채운 뒤 훨씬 큰 ID(최대 %s)로" % (
        nj_s["orphan_ids"][0], nj_s["orphan_ids"][-1], stats["nj_basic_max_id"]))
    w("건너뛴다 — 수집 시점에 이 구간이 `basic` 응답에서 빠졌을 가능성이 있다. 재수집 판단은 2단계.")
    w("")

    w("## 2. 레시피 건수")
    w("")
    w("| 소스 | 건수 |")
    w("| --- | ---: |")
    w("| 농정원 | %d |" % nj_s["recipes"])
    w("| 식약처 | %d |" % mf_s["recipes"])
    w("| **합계** | **%d** |" % (nj_s["recipes"] + mf_s["recipes"]))
    w("| 고아 (별도 집계, 산출물 미포함) | %d |" % len(nj_s["orphan_ids"]))
    w("")

    w("## 3. 식약처 재료 파싱 성공률")
    w("")
    w("| 항목 | 값 |")
    w("| --- | ---: |")
    w("| 레시피 | %d |" % mf_s["recipes"])
    w("| 재료 행이 1개 이상 나온 레시피 | %d (%.1f%%) |" % (
        mf_s["parsed_ok"], 100.0 * mf_s["parsed_ok"] / mf_s["recipes"]))
    w("| 한 행도 못 뽑은 레시피 | %d |" % mf_s["recipe_failures"])
    w("| 행으로 못 가른 조각 | %d |" % mf_s["fragment_failures"])
    w("")
    w("`data/processed/unparsed_ingredients.json`에 전량 보존했다 (`kind`: `recipe` %d건 + `fragment` %d건 = %d건)." % (
        mf_s["recipe_failures"], mf_s["fragment_failures"], len(unparsed)))
    w("LLM 파싱은 2단계에서 이 잔여분에만 적용한다.")
    w("")
    w("한 행도 못 뽑은 %d건:" % mf_s["recipe_failures"])
    w("")
    for u in unparsed:
        if u["kind"] == "recipe":
            w("- `%s` %s — 원본 `%s`" % (u["source_id"], u["recipe_name"], u["raw"][:60].replace("\n", "\\n")))
    w("")
    w("네 건 모두 원천 `RCP_PARTS_DTLS`가 빈 문자열이거나 `.` 한 글자다 — 파싱 실패가 아니라 원천 결손이다.")
    w("내용이 있는 %d건은 전부 재료 행을 산출했다. 규칙이 놓친 잔여는 레시피 단위가 아니라" % mf_s["parsed_ok"])
    w("조각 단위 %d건이며, 대부분 쉼표 누락(`양파 5g 고추장 9g`)·괄호 짝 오류(`후춧가루(0.5g`)·" % mf_s["fragment_failures"])
    w("수량 없는 재료(`월계수잎`)다.")
    w("")

    w("## 4. 식약처 재료 행 수")
    w("")
    w("| 소스 | 재료 행 | 레시피당 평균 |")
    w("| --- | ---: | ---: |")
    w("| 식약처 | %d | %.1f |" % (
        mf_s["ingredient_rows"], 1.0 * mf_s["ingredient_rows"] / mf_s["recipes"]))
    w("| 농정원 | %d | %.1f |" % (
        nj_s["ingredient_rows"], 1.0 * nj_s["ingredient_rows"] / nj_s["recipes"]))
    w("")

    w("## 4-1. 재료명 잔재 점검")
    w("")
    w("파싱 성공률(3절)은 레시피 단위라 느슨하다. 2단계 재료명 표준화는 고유명 단위로 하므로")
    w("이름에 남은 잔재를 고유명 기준으로 센다.")
    w("")
    audit = audit_names(ing_rows)
    w("| 소스 | 고유 재료명 | 잔재 있는 이름 | 해당 행 |")
    w("| --- | ---: | ---: | ---: |")
    for source, label in (("nongjeongwon", "농정원"), ("mfds", "식약처")):
        a = audit[source]
        ratio = (100.0 * len(a["dirty"]) / a["names"]) if a["names"] else 0.0
        w("| %s | %d | %d (%.1f%%) | %d |" % (label, a["names"], len(a["dirty"]), ratio, a["rows"]))
    w("")
    for source, label in (("nongjeongwon", "농정원"), ("mfds", "식약처")):
        a = audit[source]
        if not a["dirty"]:
            w("- %s: 잔재 0건." % label)
            continue
        w("- %s:" % label)
        for check, names in sorted(a["by_check"].items()):
            if names:
                w("  - %s %d종 — %s" % (check, len(names), ", ".join("`%s`" % n for n in names[:8])))
    w("")

    w("## 5. 분해로 늘어난 행 (농정원 복수 재료)")
    w("")
    w("| 원본 재료명 | 원본 행 | 분해 후 행 수 | 증가 |")
    w("| --- | ---: | ---: | ---: |")
    for name, count in sorted(nj_s["splits"].items()):
        occ = nj_s["split_occurrences"][name]
        w("| `%s` | %d | %d | +%d |" % (name, occ, count * occ, (count - 1) * occ))
    w("| **합계** | **%d** | **%d** | **+%d** |" % (
        sum(nj_s["split_occurrences"].values()),
        sum(nj_s["splits"][n] * nj_s["split_occurrences"][n] for n in nj_s["splits"]),
        split_gain))
    w("")
    if nj_s["orphan_split"]:
        w("지시서에 명시된 복수 재료 8종 중 %d종은 고아 레시피(RECIPE_ID 536·539)에 속해" % len(nj_s["orphan_split"]))
        w("산출물에 들어가지 않았다. 분해하지 않고 원본 그대로 `orphans/`에 보존했다.")
        w("")
        w("| 원본 재료명 | 행 수 | 위치 |")
        w("| --- | ---: | --- |")
        for name in sorted(nj_s["orphan_split"]):
            w("| `%s` | %d | orphans |" % (name, nj_s["orphan_split"][name]))
        w("")
    w("표에 없는데 구분자(`/` `,` `·`)를 품은 재료명: %d건%s" % (
        len(nj_s["unhandled_delimiter"]),
        (" — " + ", ".join("`%s`" % x for x in sorted(set(nj_s["unhandled_delimiter"]))))
        if nj_s["unhandled_delimiter"] else " (없음)"))
    w("")

    w("## 6. 오탈자 교정 건수")
    w("")
    w("| 원본 | 교정 | 행 수 |")
    w("| --- | --- | ---: |")
    for wrong in sorted(nj.TYPO_MAP):
        w("| %s | %s | %d |" % (wrong, nj.TYPO_MAP[wrong], nj_s["typos"].get(wrong, 0)))
    w("| | **합계** | **%d** |" % sum(nj_s["typos"].values()))
    w("")

    w("## 7. 빈 값 현황")
    w("")
    for source, label in (("nongjeongwon", "농정원"), ("mfds", "식약처")):
        subset = [r for r in recipes if r["source"] == source]
        w("### %s 레시피 (%d건)" % (label, len(subset)))
        w("")
        w("| 필드 | 빈 값 | 비율 |")
        w("| --- | ---: | ---: |")
        for field, empty, total, pct in empty_field_table(subset, list(subset[0].keys())):
            if field in ("source", "source_id"):
                continue
            w("| %s | %d | %.1f%% |" % (field, empty, pct))
        w("")
        sub_ing = [r for r in ing_rows if r["source"] == source]
        sub_step = [r for r in step_rows if r["source"] == source]
        w("| 필드 | 빈 값 | 비율 |")
        w("| --- | ---: | ---: |")
        for field, empty, total, pct in empty_field_table(sub_ing, ["group_name", "qty_raw", "role_raw"]):
            w("| 재료.%s | %d / %d | %.1f%% |" % (field, empty, total, pct))
        for field, empty, total, pct in empty_field_table(sub_step, ["description", "tip", "image_url"]):
            w("| 조리.%s | %d / %d | %.1f%% |" % (field, empty, total, pct))
        w("")

    w("## 8. 알려진 원천 데이터 결함 (고치지 않았다 — 기록만)")
    w("")
    w("### 농정원 이미지 없음")
    w("")
    w("수집분에 `IMG_URL`·`DET_URL` 컬럼이 존재하지 않는다. API 명세에는 있으나 수집 데이터에 없다.")
    w("따라서 농정원 레시피 %d건 전부 `image_url`이 null이다. 재수집 여부는 2단계 판단." % nj_s["recipes"])
    w("")
    w("### 식약처 — 재료 목록과 조리과정이 어긋나는 레시피 (근사 측정)")
    w("")
    w("조리과정에만 등장하고 재료 목록에는 없는 재료가 3종 이상인 레시피 **%d건 (%.1f%%)**." % (
        len(mismatches), 100.0 * len(mismatches) / mf_s["recipes"]))
    w("코퍼스 전체 재료명(5회 이상 등장, 2~5자 한글)을 사전으로 삼아 조리과정 텍스트를 조회한 근사치다.")
    w("재료를 한 행도 못 뽑은 %d건은 3절에서 이미 집계했으므로 이 측정에서 제외했다." % mf_s["recipe_failures"])
    w("**판정도 수정도 하지 않았다.** 2단계 판단 재료로만 남긴다.")
    w("")
    w("| source_id | 레시피명 | 조리과정에만 등장 |")
    w("| --- | --- | --- |")
    name_by_id = dict((r["source_id"], r["name"]) for r in recipes if r["source"] == "mfds")
    for source_id, hits in mismatches:
        w("| %s | %s | %s |" % (source_id, name_by_id.get(source_id, ""), ", ".join(hits)))
    w("")
    w("### 농정원 수량 표기")
    w("")
    w("`qty_raw`가 `약간`·`적당량`인 행 %d / %d (%.1f%%) — 수치가 아니다." % (
        nj_s["vague_qty"], nj_s["ingredient_rows"],
        100.0 * nj_s["vague_qty"] / nj_s["ingredient_rows"]))
    w("`느타리버섯 800g`(4인분 잡채) 같은 수량 이상치도 그대로 두었다.")
    w("")
    w("### 농정원 조리 단계 번호 결함")
    w("")
    w("`COOKING_NO`에 중복·결번·재시작이 있는 레시피 %d건. 이 필드를 정렬 키로 쓰면 순서가 뒤집히므로" % len(nj_s["broken_cooking_no"]))
    w("원천 파일 순서(`ROW_NUM`)를 유지하고 `step_no`를 1부터 다시 매겼다. **원본 순서는 바꾸지 않았다.**")
    w("")
    w("| RECIPE_ID | 원본 COOKING_NO | 증상 |")
    w("| ---: | --- | --- |")
    for rid, nos in nj_s["broken_cooking_no"]:
        seq_text = ", ".join(str(n) for n in nos)
        if len(set(nos)) != len(nos):
            symptom = "중복" if nos[-1] != 1 else "중간 재시작"
        else:
            symptom = "결번"
        w("| %s | %s | %s |" % (rid, seq_text, symptom))
    w("")
    w("특히 `316`은 마지막 행(반죽 만들기)이 `COOKING_NO 1`로 붙어 있다 — 순서 자체가 의심스럽다.")
    w("판정하지 않고 원본 순서 그대로 뒀다. 2단계 판단 대상.")
    w("")
    w("### 식약처 조리과정 꼬리 문자")
    w("")
    w("`MANUAL` 설명 끝에 의미 없는 라틴 문자(`a` `b` `c`)가 붙은 칸이 %d개 있다. 제거하지 않았다." % stats["latin_tail"])
    w("")
    w("### 버린 컬럼")
    w("")
    w("- 농정원: `ROW_NUM` `NATION_CODE` `TY_CODE` `IRDNT_CODE` `IRDNT_TY_CODE` `IRDNT_SN`(seq로 대체)")
    w("- 식약처: `ATT_FILE_NO_MK`(썸네일 — 지시서 스키마에 없음), `MANUAL`/`MANUAL_IMG` 빈 칸")
    w("")

    w("## 산출물")
    w("")
    w("| 파일 | 행 수 |")
    w("| --- | ---: |")
    w("| `recipes.json` | %d |" % len(recipes))
    w("| `recipe_ingredients.json` | %d |" % len(ing_rows))
    w("| `recipe_steps.json` | %d |" % len(step_rows))
    w("| `unparsed_ingredients.json` | %d |" % len(unparsed))
    w("| `orphans/nongjeongwon_ingredient.json` | %d |" % nj_s["orphan_ingredient_rows"])
    w("| `orphans/nongjeongwon_step.json` | %d |" % nj_s["orphan_step_rows"])
    w("")
    w("### 표기 규칙")
    w("")
    w("- 형식은 JSON 배열로 통일했다. 빈 문자열은 전부 `null`로 정규화했다.")
    w("- 두 소스가 같은 열 구성을 갖는다. 해당 소스에 없는 필드는 `null`이다.")
    w("- `seq`는 레시피 안에서 1부터 다시 매긴다 (농정원 `IRDNT_SN`을 대체).")
    w("- 식약처 재료의 `group_name`이 `소스소개 > 저나트륨간장소스` 형태인 것은")
    w("  대괄호 섹션과 콜론 하위 그룹이 겹친 경우다. 둘 다 버리지 않으려고 ` > `로 이었다.")
    w("- `name_raw`·`qty_raw`는 원본 표기다. 표준화하지 않았다.")
    w("")

    with io.open(os.path.join(OUT, "report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


# --------------------------------------------------------------------------- main


def verify(stats, recipes, ing_rows, step_rows):
    """산출물 자체 검증. 하나라도 어긋나면 보고서를 쓰지 않고 멈춘다."""
    nj_s, mf_s, nj_in, mf_in = stats["nj"], stats["mfds"], stats["nj_input"], stats["mfds_input"]
    split_gain = sum(
        (count - 1) * nj_s["split_occurrences"][name]
        for name, count in nj_s["splits"].items()
    )

    assert nj_s["recipes"] == nj_in["basic"], "농정원 레시피 수 불일치"
    assert mf_s["recipes"] == mf_in["recipes"], "식약처 레시피 수 불일치"
    assert nj_s["ingredient_rows"] - split_gain + nj_s["orphan_ingredient_rows"] == nj_in["ingredient"], \
        "농정원 재료 행 잔차 != 0"
    assert nj_s["step_rows"] + nj_s["orphan_step_rows"] == nj_in["step"], "농정원 조리 행 잔차 != 0"
    assert mf_s["step_rows"] == mf_s["manual_cells"], "식약처 조리 행 잔차 != 0"

    keys = set((r["source"], r["source_id"]) for r in recipes)
    assert len(keys) == len(recipes), "레시피 키 중복"
    for rows, label in ((ing_rows, "재료"), (step_rows, "조리")):
        assert all((r["source"], r["source_id"]) in keys for r in rows), "%s 행이 레시피를 잃었다" % label
        grouped = {}
        for r in rows:
            grouped.setdefault((r["source"], r["source_id"]), []).append(
                r["seq"] if "seq" in r else r["step_no"])
        for key, nums in grouped.items():
            assert nums == list(range(1, len(nums) + 1)), "%s 순번이 1..n이 아니다: %s" % (label, key)
    assert all(r["name_raw"] and r["name_raw"].strip() == r["name_raw"] for r in ing_rows), \
        "재료명에 공백이 남았다"


def main():
    for path in (OUT, ORPHANS):
        if not os.path.isdir(path):
            os.makedirs(path)

    stats = {}
    nj_recipes, nj_ing, nj_step, orphan_ing, orphan_step = build_nongjeongwon(stats)
    mf_recipes, mf_ing, mf_step, unparsed = build_mfds(stats)

    stats["orphan_ing_by_id"] = Counter(r["RECIPE_ID"] for r in orphan_ing)
    stats["orphan_step_by_id"] = Counter(r["RECIPE_ID"] for r in orphan_step)

    raw_mfds = load("mfds_recipes.json")
    stats["latin_tail"] = sum(
        1 for r in raw_mfds for n in range(1, MAX_MANUAL + 1)
        if r["MANUAL%02d" % n].strip() and r["MANUAL%02d" % n].strip()[-1].isascii()
        and r["MANUAL%02d" % n].strip()[-1].isalpha()
    )

    recipes = nj_recipes + mf_recipes
    ing_rows = nj_ing + mf_ing
    step_rows = nj_step + mf_step

    verify(stats, recipes, ing_rows, step_rows)

    dump(os.path.join(OUT, "recipes.json"), recipes)
    dump(os.path.join(OUT, "recipe_ingredients.json"), ing_rows)
    dump(os.path.join(OUT, "recipe_steps.json"), step_rows)
    dump(os.path.join(OUT, "unparsed_ingredients.json"), unparsed)
    dump(os.path.join(ORPHANS, "nongjeongwon_ingredient.json"), orphan_ing)
    dump(os.path.join(ORPHANS, "nongjeongwon_step.json"), orphan_step)

    vocabulary = build_vocabulary(ing_rows)
    mismatches = step_only_ingredients(mf_ing, mf_step, vocabulary)

    write_report(stats, recipes, ing_rows, step_rows, unparsed, mismatches)

    print("recipes            %d" % len(recipes))
    print("recipe_ingredients %d" % len(ing_rows))
    print("recipe_steps       %d" % len(step_rows))
    print("unparsed           %d" % len(unparsed))
    print("orphan rows        %d ingredient / %d step" % (len(orphan_ing), len(orphan_step)))
    print("step/ingredient mismatch (approx) %d" % len(mismatches))


if __name__ == "__main__":
    main()
