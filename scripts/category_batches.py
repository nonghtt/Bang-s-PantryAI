# -*- coding: utf-8 -*-
"""요리 계통 분류의 배치 명세 생성 · 진행 확인 · 검사 · 병합.

분류 실행은 여러 세션에 걸쳐 이뤄진다. 중간에 끊기거나 같은 배치를 두 번
돌리는 일이 생기므로, 병합 전에 무결성을 검사하고 어긋나면 쓰지 않고 멈춘다.
재료명 정규화의 `merge_batches.py`와 같은 역할이며 검사 항목만 다르다.

    python scripts/category_batches.py --spec      # 배치 명세 생성 (결정적)
    python scripts/category_batches.py --status    # 배치별 진행 상황
    python scripts/category_batches.py             # 검사 + 병합

산출: `data/labels/category_full_output.csv`
표준 라이브러리만 사용한다.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "data" / "labels"
SPEC = LABELS / "category_batches.txt"
PARTS = LABELS / "category_batches"
MERGED = LABELS / "category_full_output.csv"
RECIPES = ROOT / "data" / "processed" / "recipes.json"

FIELDS = ["source", "source_id", "name", "카테고리", "sub", "근거축", "근거"]
CATEGORIES = {"한식", "중식", "일식", "동남아", "양식", "판정불가"}
AXES = {"요리명", "조리법", "주재료"}
SUB_ALLOWED = {"양식", "동남아"}          # sub 를 쓸 수 있는 카테고리 (category_README §1)
N_BATCHES = 8
TAB = chr(9)
NLC = chr(10)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def target_recipes():
    """분류 대상 — 식약처 전량. 농정원은 원천에 계통 필드가 있어 대상이 아니다."""
    rows = [r for r in json.load(RECIPES.open(encoding="utf-8"))
            if r["source"] == "mfds"]
    rows.sort(key=lambda r: int(r["source_id"]))
    return rows


def write_spec():
    rows = target_recipes()
    n = len(rows)
    lines = ["# 요리 계통 분류 배치 명세 — 결정적 분할 (source_id 정렬 후 균등)",
             "# scripts/category_batches.py --spec 가 생성한다. 직접 편집하지 않는다.",
             "# batch_id<TAB>source<TAB>source_id<TAB>요리명"]
    for i, r in enumerate(rows):
        bid = "%02d" % (i * N_BATCHES // n + 1)
        lines.append(TAB.join([bid, r["source"], str(r["source_id"]), r["name"] or ""]))
    SPEC.write_text(NLC.join(lines) + NLC, encoding="utf-8")
    c = Counter(l.split(TAB)[0] for l in lines if not l.startswith("#"))
    print("배치 명세 생성: %s" % SPEC.as_posix())
    print("대상 %d건 · %d배치 %s" % (n, len(c), dict(sorted(c.items()))))


def load_spec():
    if not SPEC.exists():
        sys.exit("[오류] 배치 명세가 없습니다. 먼저 --spec 을 실행하십시오.")
    out = defaultdict(list)
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        bid, src, sid, name = line.split(TAB)
        out[bid].append((src, sid, name))
    return out


def part_path(bid):
    return PARTS / ("category_batch-%s.csv" % bid)


def check_part(bid, spec_rows):
    """배치 파일 하나를 검사한다. 오류 목록을 돌려준다 (비어 있으면 통과)."""
    path = part_path(bid)
    errs = []
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    missing_cols = [c for c in FIELDS if rows and c not in rows[0]]
    if missing_cols:
        return ["컬럼 없음: %s" % ", ".join(missing_cols)], rows

    want = {(s, i) for s, i, _n in spec_rows}
    got = [(r["source"], str(r["source_id"])) for r in rows]
    if len(rows) != len(spec_rows):
        errs.append("행 수 불일치 — 기대 %d, 제출 %d" % (len(spec_rows), len(rows)))
    dup = [k for k, v in Counter(got).items() if v > 1]
    if dup:
        errs.append("중복 키 %d건: %s" % (len(dup), dup[:5]))
    ghost = sorted(set(got) - want)
    if ghost:
        errs.append("명세에 없는 행 %d건: %s" % (len(ghost), ghost[:5]))
    miss = sorted(want - set(got))
    if miss:
        errs.append("빠진 행 %d건: %s" % (len(miss), miss[:5]))

    name_of = {(s, i): n for s, i, n in spec_rows}
    for r in rows:
        key = (r["source"], str(r["source_id"]))
        cat = (r.get("카테고리") or "").strip()
        sub = (r.get("sub") or "").strip()
        axis = (r.get("근거축") or "").strip()
        why = (r.get("근거") or "").strip()
        if key in name_of and (r.get("name") or "") != name_of[key]:
            errs.append("요리명 변경: %s — 기대 %r, 제출 %r"
                        % (key, name_of[key], r.get("name")))
        if cat not in CATEGORIES:
            errs.append("카테고리 값 오류: %s — %r" % (key, cat))
        if sub and cat not in SUB_ALLOWED:
            errs.append("sub 는 %s 에만 쓴다: %s — %r" % ("·".join(sorted(SUB_ALLOWED)), key, sub))
        if cat != "판정불가" and axis not in AXES:
            errs.append("근거축 값 오류: %s — %r" % (key, axis))
        if not why:
            errs.append("근거 공란: %s" % (key,))
    return errs, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", action="store_true", help="배치 명세를 생성한다")
    ap.add_argument("--status", action="store_true", help="진행 상황만 보고 병합하지 않는다")
    args = ap.parse_args()

    if args.spec:
        write_spec()
        return 0

    spec = load_spec()
    PARTS.mkdir(exist_ok=True)

    if args.status:
        print("| 배치 | 대상 | 상태 |")
        print("| --- | ---: | --- |")
        for bid in sorted(spec):
            p = part_path(bid)
            if not p.exists():
                state = "미실행"
            else:
                errs, rows = check_part(bid, spec[bid])
                state = "완료 (%d행)" % len(rows) if not errs else "검사 실패 — %s" % errs[0]
            print("| %s | %d | %s |" % (bid, len(spec[bid]), state))
        return 0

    # 병합 — 전 배치가 있어야 하고 전부 검사를 통과해야 한다
    missing = [b for b in sorted(spec) if not part_path(b).exists()]
    if missing:
        print("[오류] 미실행 배치: %s" % ", ".join(missing), file=sys.stderr)
        return 1
    merged, failed = [], False
    for bid in sorted(spec):
        errs, rows = check_part(bid, spec[bid])
        if errs:
            failed = True
            print("[오류] 배치 %s" % bid, file=sys.stderr)
            for e in errs[:8]:
                print("   - %s" % e, file=sys.stderr)
        merged += rows
    if failed:
        print("검사 실패 — 병합하지 않습니다.", file=sys.stderr)
        return 1

    order = {(s, i): n for bid in sorted(spec) for n, (s, i, _x) in enumerate(spec[bid])}
    merged.sort(key=lambda r: (r["source"], int(r["source_id"])))
    with MERGED.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator=NLC, extrasaction="ignore")
        w.writeheader()
        w.writerows(merged)
    print("병합 완료: %s — %d행" % (MERGED.as_posix(), len(merged)))
    print("카테고리 분포: %s"
          % dict(Counter(r["카테고리"] for r in merged).most_common()))
    print("근거축 분포: %s"
          % dict(Counter((r.get("근거축") or "").strip() for r in merged).most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
