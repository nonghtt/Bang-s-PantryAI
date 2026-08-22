# -*- coding: utf-8 -*-
"""요리 계통 분류 결과를 정답 세트와 대조해 정확도를 낸다.

분류를 수행한 세션은 이 스크립트를 실행하지 않는다 — 정답을 보게 되면
다음 배치에서 판단 기준을 정답에 맞춰 고치게 되고, 그 순간 측정이 오염된다.
채점은 분류와 분리된 시점에 수행한다. (D-034)

    python scripts/score_categories.py data/labels/category_batches/category_batch-01.csv
    python scripts/score_categories.py data/labels/category_full_output.csv

두 층의 정확도를 **합산하지 않는다** (`category_README.md` §4-2).
  (A) 대표 층 — 전체 정확도의 대표값. 공식 수치는 이것이다
  (B) 함정 층 — 외래 키워드가 걸리는 어려운 구간의 정확도

산출: 표준 출력에 요약, `<입력파일>.score.md` 에 상세 보고서.
표준 라이브러리만 사용한다.
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "data" / "labels" / "category_answers.csv"
SNAPSHOT = ROOT / "data" / "labels" / "spec-snapshot"
RULES = ROOT / "data" / "labels" / "category_README.md"
PROMPT = (ROOT / "_bmad-output" / "planning-artifacts" / "prds"
          / "prd-PantryAI-2026-08-18" / "category-classify-prompt.md")
NLC = chr(10)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def spec_named():
    """명세에 요리명이 그대로 등장하는 집합.

    하드코딩하지 않고 채점 시점에 센다 — 명세를 고치면 분리 대상도 따라 바뀐다.
    (`category_README.md` §4-4. D-041 에서 상수가 규칙과 어긋난 사고를 되풀이하지 않는다)

    **단 읽는 것은 분류 실행 시점의 스냅샷이다** (`data/labels/spec-snapshot/`).
    현재 문서를 읽으면 채점 결과를 문서에 기록하는 것만으로 그 행이 채점에서
    빠져 점수가 오른다 — 자동화가 정직성을 깨는 자리다. (D-047)
    """
    # 실행 세션이 본 명세는 그 시점의 것이지 지금 것이 아니다.
    # 현재 문서를 읽으면 **채점 이후에 추가된 내용까지 분리 대상이 되어**
    # 불일치가 소급해서 숨는다. 실제로 그 사고가 났다 — `spec-snapshot/README.md` 참조.
    snap = sorted(SNAPSHOT.glob("category*.md")) if SNAPSHOT.exists() else []
    if snap:
        sources = snap
    else:
        sources = [RULES, PROMPT]
        print("[경고] 명세 스냅샷이 없어 현재 문서를 읽습니다 — 채점 이후 추가된 내용이"
              " 분리 대상에 섞일 수 있습니다.", file=sys.stderr)
    names = set()
    for p in sources:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        names |= set(re.findall(r"`([^`]{2,40})`", text))
        names |= set(re.findall(r"^mfds,\d+,([^,]+),", text, re.M))
    return names


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    out_path = Path(sys.argv[1])
    if not out_path.exists():
        print("없음: %s" % out_path, file=sys.stderr)
        return 1

    answers = {r["source_id"]: r
               for r in csv.DictReader(ANSWERS.open(encoding="utf-8-sig"))}
    rows = list(csv.DictReader(out_path.open(encoding="utf-8-sig")))
    for col in ("source_id", "카테고리"):
        if rows and col not in rows[0]:
            print("컬럼 없음: %s" % col, file=sys.stderr)
            return 1

    leaked = spec_named()
    scored = defaultdict(list)     # 층 -> [(정답행, 제출행, 맞음)]
    undecidable, exposed, unknown = [], [], 0
    for r in rows:
        a = answers.get(str(r["source_id"]))
        if a is None:
            unknown += 1
            continue
        got = (r.get("카테고리") or "").strip()
        exp = a["카테고리"].strip()
        if a["name"] in leaked:            # 명세에 요리명이 노출된 행
            exposed.append((a, r, got == exp))
            continue
        if exp == "판정불가":               # 규칙상 평가셋에서 제외 (§3-6)
            undecidable.append((a, r, got == exp))
            continue
        scored[a["층"]].append((a, r, got == exp))

    total = sum(len(v) for v in scored.values())
    print("입력 %s — %d행" % (out_path.name, len(rows)))
    print("정답과 겹친 행 %d (정답지 밖 %d행은 채점 대상이 아님)"
          % (total + len(undecidable) + len(exposed), unknown))
    print("  채점 %d · 판정불가 제외 %d · 명세 노출 제외 %d"
          % (total, len(undecidable), len(exposed)))

    lines = ["# 요리 계통 분류 채점 보고서", "",
             "입력: `%s`" % out_path.as_posix(), "",
             "| 항목 | 값 |", "| --- | ---: |",
             "| 제출 행 | %d |" % len(rows),
             "| 정답과 겹친 행 | %d |" % (total + len(undecidable) + len(exposed)),
             "| 채점 대상 | %d |" % total,
             "| 판정불가(§3-6 제외) | %d |" % len(undecidable),
             "| 명세 노출(§4-4 제외) | %d |" % len(exposed), ""]

    if total:
        print()
        print("■ 층별 정확도 — 합산하지 않는다")
        lines += ["## 층별 정확도", "",
                  "**두 수치를 합산하지 않는다.** 공식 수치는 대표 층이다. (§4-2)", "",
                  "| 층 | 일치 | 대상 | 정확도 |", "| --- | ---: | ---: | ---: |"]
        label = {"A": "대표 층 (공식)", "B": "함정 층"}
        for tag in ("A", "B"):
            v = scored.get(tag, [])
            if not v:
                continue
            ok = sum(1 for _a, _r, g in v if g)
            print("   %-14s %3d/%-3d  %5.1f%%" % (label[tag], ok, len(v), 100 * ok / len(v)))
            lines.append("| %s | %d | %d | %.1f%% |" % (label[tag], ok, len(v), 100 * ok / len(v)))
        lines.append("")

        # 카테고리별 — 재현율(정답 기준)과 정밀도(제출 기준)
        rec, pre = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        for _tag, v in scored.items():
            for a, r, good in v:
                rec[a["카테고리"]][0] += good
                rec[a["카테고리"]][1] += 1
                got = (r.get("카테고리") or "").strip()
                pre[got][0] += good
                pre[got][1] += 1
        print()
        print("카테고리별 (정답 기준 재현율 / 제출 기준 정밀도)")
        lines += ["## 카테고리별", "",
                  "| 계통 | 정답 수 | 맞힘 | 재현율 | 제출 수 | 정밀도 |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for c in sorted(set(rec) | set(pre)):
            rg, rt = rec[c]
            pg, pt = pre[c]
            print("   %-6s 재현 %2d/%-2d  정밀 %2d/%-2d" % (c, rg, rt, pg, pt))
            lines.append("| %s | %d | %d | %s | %d | %s |"
                         % (c, rt, rg, ("%.0f%%" % (100 * rg / rt)) if rt else "-",
                            pt, ("%.0f%%" % (100 * pg / pt)) if pt else "-"))
        lines.append("")

        # 근거축 — 채점 대상이 아니다. 판단 경로가 겹치는지만 본다
        axis = [(a.get("근거축", ""), (r.get("근거축") or "").strip())
                for v in scored.values() for a, r, _g in v]
        same = sum(1 for x, y in axis if x and x == y)
        print()
        print("근거축 일치 %d/%d (%.0f%%) — 채점 대상이 아니라 판단 경로 비교다"
              % (same, len(axis), 100 * same / len(axis) if axis else 0))
        lines += ["## 근거축", "",
                  "**채점 대상이 아니다.** 정답을 만든 쪽과 모델의 판단 경로가 겹치는지만 본다.", "",
                  "| | 값 |", "| --- | ---: |",
                  "| 일치 | %d / %d (%.0f%%) |" % (same, len(axis),
                                                  100 * same / len(axis) if axis else 0), ""]
        cross = Counter(axis)
        lines += ["| 정답 축 → 제출 축 | 건수 |", "| --- | ---: |"]
        lines += ["| %s → %s | %d |" % (x or "(빈칸)", y or "(빈칸)", n)
                  for (x, y), n in cross.most_common()]
        lines.append("")

        # sub — 카테고리를 맞힌 행에서만
        subs = [(a.get("sub", "").strip(), (r.get("sub") or "").strip())
                for v in scored.values() for a, r, g in v if g and a.get("sub", "").strip()]
        if subs:
            hit = sum(1 for x, y in subs if x == y)
            print("sub 일치 %d/%d (카테고리를 맞힌 행 중 정답에 sub 가 있는 것)" % (hit, len(subs)))
            lines += ["## sub", "",
                      "카테고리를 맞힌 행 중 정답에 `sub`가 있는 %d건에서 %d건 일치." % (len(subs), hit),
                      ""]

        miss = [(a, r) for v in scored.values() for a, r, g in v if not g]
        if miss:
            print()
            print("■ 불일치 %d건" % len(miss))
            lines += ["## 불일치 %d건" % len(miss), "",
                      "| 층 | id | 요리명 | 정답 | 제출 | 정답 근거 | 제출 근거 |",
                      "| --- | ---: | --- | --- | --- | --- | --- |"]
            for a, r in sorted(miss, key=lambda x: (x[0]["층"], int(x[0]["source_id"]))):
                print("   [%s] %-5s %-24s 정답 %-5s → 제출 %-5s"
                      % (a["층"], a["source_id"], a["name"], a["카테고리"],
                         (r.get("카테고리") or "").strip()))
                print("        정답근거: %s" % a["근거"])
                print("        제출근거: %s" % (r.get("근거") or "").strip())
                lines.append("| %s | %s | %s | %s | %s | %s | %s |"
                             % (a["층"], a["source_id"], a["name"], a["카테고리"],
                                (r.get("카테고리") or "").strip(),
                                a["근거"], (r.get("근거") or "").strip()))
            lines.append("")

    if undecidable:
        agree = sum(1 for _a, _r, g in undecidable if g)
        print()
        print("판정불가 %d행 (§3-6 로 채점 제외) — 모델도 판정불가로 낸 것 %d건"
              % (len(undecidable), agree))
        lines += ["## 판정불가 %d행 (채점 제외)" % len(undecidable), "",
                  "규칙 §3-6 이 평가셋에서 제외하도록 정했다. 참고로만 본다 —"
                  " 모델도 `판정불가`로 낸 것 **%d건**." % agree, "",
                  "| id | 요리명 | 제출 | 제출 근거 |", "| ---: | --- | --- | --- |"]
        lines += ["| %s | %s | %s | %s |" % (a["source_id"], a["name"],
                                             (r.get("카테고리") or "").strip(),
                                             (r.get("근거") or "").strip())
                  for a, r, _g in undecidable]
        lines.append("")

    if exposed:
        agree = sum(1 for _a, _r, g in exposed if g)
        print("명세 노출 %d행 (§4-4 로 채점 제외) — 그중 정답과 일치 %d건" % (len(exposed), agree))
        lines += ["## 명세 노출 %d행 (채점 제외)" % len(exposed), "",
                  "요리명이 규칙 문서 또는 실행 지시서에 그대로 등장한다. 분류 능력이 아니라"
                  " 명세 독해를 잴 위험이 있어 분리한다 (§4-4). 정답과 일치 **%d건**." % agree, "",
                  "| id | 요리명 | 정답 | 제출 |", "| ---: | --- | --- | --- |"]
        lines += ["| %s | %s | %s | %s |" % (a["source_id"], a["name"], a["카테고리"],
                                             (r.get("카테고리") or "").strip())
                  for a, r, _g in exposed]
        lines.append("")

    report = out_path.with_suffix(out_path.suffix + ".score.md")
    report.write_text(NLC.join(lines) + NLC, encoding="utf-8")
    print()
    print("상세 보고서: %s" % report.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
