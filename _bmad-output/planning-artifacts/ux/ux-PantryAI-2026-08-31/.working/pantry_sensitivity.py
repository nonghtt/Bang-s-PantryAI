# -*- coding: utf-8 -*-
"""상비 21종 leave-one-out 민감도 — 하나를 안 켰을 때 완전 매칭/1개 부족이 얼마나 줄어드는가."""
import sys, csv, json
from collections import defaultdict, Counter
from pathlib import Path
sys.path.insert(0, "scripts")
import measure_coverage as mc

NORM = Path("data/labels/stage2_full_output.csv")
pantry_raw, excluded_raw = mc.load_pantry()
name_map, row_map = mc.load_name_map(), mc.load_row_map()
ing = json.load(mc.INGREDIENTS.open(encoding="utf-8"))
recipes = {(r["source"], r["source_id"]): r for r in json.load(mc.RECIPES.open(encoding="utf-8"))}
by_recipe = defaultdict(list)
for x in ing:
    if x.get("name_raw"):
        by_recipe[(x["source"], x["source_id"])].append(x)
supplied = {}
for r in csv.DictReader(NORM.open(encoding="utf-8-sig")):
    if r.get("표준명", "").strip():
        supplied[(r["source"], str(r["source_id"]), str(r["seq"]))] = r["표준명"].strip()
def resolve(r):
    key = (r["source"], str(r["source_id"]), str(r["seq"]))
    return row_map.get(key) or supplied.get(key) or name_map.get(r["name_raw"]) or r["name_raw"]

excluded = {name_map.get(n, n) for n in excluded_raw}
def run(pantry_set):
    p = {name_map.get(n, n) for n in pantry_set}
    stat, missing, ids = mc.measure(by_recipe, recipes, p, excluded, resolve)
    return stat["합계"]["완전"], stat["합계"]["1개부족"], missing

base_full, base_one, base_missing = run(pantry_raw)
print("기준(21종 전부 켬): 완전 %d · 1개 부족 %d" % (base_full, base_one))
in_excl = sorted(n for n in pantry_raw if name_map.get(n, n) in excluded)
print("21종 중 측정 제외 목록에도 있는 것(켜도 안 켜도 매칭 무관): %d종 — %s" % (len(in_excl), " ".join(in_excl)))
print()
print("| 안 켠 재료 | 완전 매칭 | 1개 부족 | 완전→1개부족으로 밀린 수 |")
print("| --- | ---: | ---: | ---: |")
rows = []
for n in sorted(pantry_raw):
    f, o, _ = run(pantry_raw - {n})
    rows.append((base_full - f, n, f, o))
for d, n, f, o in sorted(rows, reverse=True):
    print("| %s | %d | %d | %d |" % (n, f, o, d))

# 완전 매칭 10건이 실제로 요구하는 상비 재료
p = {name_map.get(n, n) for n in pantry_raw}
_, _, ids = mc.measure(by_recipe, recipes, p, excluded, resolve)
used = Counter()
full_ids = []
for key in ids:
    need_all = set()
    for r in by_recipe[key]:
        if (r.get("role_raw") or "") == "양념": continue
        nm = resolve(r)
        if nm is None or nm in excluded: continue
        need_all.add(nm)
    if need_all <= p:
        full_ids.append((recipes[key].get("name") or recipes[key].get("rcp_nm") or str(key), sorted(need_all)))
        for nm in need_all: used[nm] += 1
print("\n완전 매칭 %d건이 쓰는 상비 재료(면제/제외 제외):" % len(full_ids))
for nm, c in used.most_common(): print("  %s %d" % (nm, c))
print("\n완전 매칭 레시피:")
for name, need in full_ids: print("  -", name, "←", " ".join(need))

# 오등록 비용: 안 가진 재료 하나를 켰을 때 "없는 재료 섞인 레시피"가 몇 건 뜨는가 = 그 재료가 유일하게 부족한 레시피 수
print("\n오등록(없는데 켬) 비용 — 그 재료 하나만 부족한 레시피 수(= 잘못 뜨는 레시피 수):")
for n in sorted(pantry_raw):
    std = name_map.get(n, n)
    if std in excluded: continue
    _, _, missing = run(pantry_raw - {n})
    print("  %s: %d" % (n, missing.get(std, 0)))
