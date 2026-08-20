# -*- coding: utf-8 -*-
"""2단계 정규화 배치 산출물의 진행 상황 확인과 병합.

배치 실행은 여러 세션에 걸쳐 이뤄진다. 중간에 끊기거나 같은 배치를 두 번
돌리는 일이 생기므로, 병합 전에 무결성을 검사하고 어긋나면 쓰지 않고 멈춘다.

    python scripts/merge_batches.py --status          # 배치별 진행 상황
    python scripts/merge_batches.py                   # 검사 + 병합

산출: `data/labels/stage2_full_output.csv`
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
BATCHES = LABELS / "batches.txt"
VOCAB = LABELS / "standard_names.txt"
INGREDIENTS = ROOT / "data" / "processed" / "recipe_ingredients.json"
PARTS = LABELS / "batches"
MERGED = LABELS / "stage2_full_output.csv"
FIELDS = ["source", "source_id", "seq", "name_raw", "표준명", "근거"]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def load_batches():
    out = defaultdict(list)
    for line in BATCHES.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        bid, src, sid = line.split("\t")
        out[bid].append((src, sid))
    return out


def load_corpus():
    rows = defaultdict(list)
    for x in json.load(INGREDIENTS.open(encoding="utf-8")):
        if x.get("name_raw"):
            rows[(x["source"], str(x["source_id"]))].append(x)
    return rows


def part_path(bid):
    return PARTS / ("stage2_batch-%s.csv" % bid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="진행 상황만 보고 병합하지 않는다")
    args = ap.parse_args()

    batches = load_batches()
    corpus = load_corpus()
    expected = {bid: sum(len(corpus[k]) for k in keys) for bid, keys in batches.items()}

    print("배치 %d개 · 레시피 %d건 · 재료 %d행\n"
          % (len(batches), sum(len(v) for v in batches.values()), sum(expected.values())))
    print("| 배치 | 레시피 | 기대 행 | 제출 행 | 상태 |")
    print("| --- | ---: | ---: | ---: | --- |")

    done, problems, all_rows = [], [], []
    for bid in sorted(batches):
        p = part_path(bid)
        if not p.exists():
            print("| %s | %d | %d | - | 미실행 |" % (bid, len(batches[bid]), expected[bid]))
            continue
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
        missing = [c for c in ("source", "source_id", "seq", "name_raw", "표준명") if rows and c not in rows[0]]
        if missing:
            state = "컬럼 없음: " + ",".join(missing)
            problems.append("%s %s" % (bid, state))
        elif len(rows) != expected[bid]:
            state = "**행 수 불일치**"
            problems.append("%s 행 수 %d != 기대 %d" % (bid, len(rows), expected[bid]))
        else:
            state = "완료"
            done.append(bid)
            all_rows.extend(rows)
        print("| %s | %d | %d | %d | %s |" % (bid, len(batches[bid]), expected[bid], len(rows), state))

    print("\n완료 %d / %d 배치" % (len(done), len(batches)))

    if all_rows:
        vocab = {l.strip() for l in VOCAB.open(encoding="utf-8")
                 if l.strip() and not l.startswith("#")}
        seen = Counter((r["source"], str(r["source_id"]), str(r["seq"])) for r in all_rows)
        dup = [k for k, c in seen.items() if c > 1]
        ghost = [r for r in all_rows
                 if not any(x["name_raw"] == r["name_raw"] and str(x["seq"]) == str(r["seq"])
                            for x in corpus.get((r["source"], str(r["source_id"])), ()))]
        oov = {r["표준명"].strip() for r in all_rows
               if r["표준명"].strip() and r["표준명"].strip() not in vocab
               and not (r.get("근거") or "").strip().startswith(("어휘없음", "판별불가"))}
        blank = [r for r in all_rows if not r["표준명"].strip()]
        print("중복 키 %d · 원본에 없는 행 %d · 어휘 밖 %d · 표준명 공란 %d"
              % (len(dup), len(ghost), len(oov), len(blank)))
        if dup:
            problems.append("중복 키 %d건 예: %s" % (len(dup), dup[:3]))
        if ghost:
            problems.append("원본에 없는 행 %d건" % len(ghost))
        if blank:
            problems.append("표준명 공란 %d건" % len(blank))
        if oov:
            print("   어휘 밖: %s" % ", ".join(sorted(oov)[:10]))

    for msg in problems:
        print("[오류] %s" % msg, file=sys.stderr)
    if problems:
        print("\n오류 %d건 — 병합하지 않고 멈춥니다." % len(problems), file=sys.stderr)
        return 1
    if args.status:
        return 0
    if len(done) != len(batches):
        print("\n미완 배치가 있어 병합하지 않습니다.")
        return 0

    all_rows.sort(key=lambda r: (r["source"], int(r["source_id"]), int(r["seq"])))
    with MERGED.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print("\n병합 완료: %s (%d행)" % (MERGED.as_posix(), len(all_rows)))
    print("다음: python scripts/score_normalization.py %s" % MERGED.as_posix())
    print("      python scripts/measure_coverage.py --normalized %s" % MERGED.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
