# -*- coding: utf-8 -*-
"""2단계 재료명 정규화 결과를 정답 세트와 대조해 일치율을 낸다.

정규화를 수행한 세션은 이 스크립트를 실행하지 않는다 — 정답을 보게 되면
다음 실행에서 프롬프트를 정답에 맞춰 고치게 되고, 그 순간 측정이 오염된다.
채점은 정규화와 분리된 시점에 수행한다.

    python scripts/score_normalization.py data/labels/stage2_pilot_output.csv

산출: 표준 출력에 요약, `<입력파일>.score.md` 에 상세 보고서.
표준 라이브러리만 사용한다.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "data" / "labels" / "ingredient_standard_answers.csv"
VOCAB = ROOT / "data" / "labels" / "standard_names.txt"
PILOT = ROOT / "data" / "labels" / "pilot_recipes.txt"
ROW_ANSWERS = ROOT / "data" / "labels" / "context_dependent_rows.csv"
INGREDIENTS = ROOT / "data" / "processed" / "recipe_ingredients.json"

# 코퍼스만으로는 도달할 수 없다고 기록된 항목 (D-025·D-026).
# 모델이 맞힐 수 없으므로 본 집계에서 분리하고 따로 보고한다.
CONTEXT_DEPENDENT = {"치즈", "슬라이스치즈", "저염치즈", "발사믹소스", "파스타"}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def load_answers():
    rows = list(csv.DictReader(ANSWERS.open(encoding="utf-8-sig")))
    return ({r["재료명"]: r["표준명"].strip() for r in rows},
            {r["재료명"]: r["판정"].strip() for r in rows})


def load_row_answers():
    """행 단위 정답. 이름은 같지만 레시피 맥락이 표준명을 바꾸는 경우.

    `표고버섯`이라고만 적혔어도 조리과정이 "말린 표고버섯"·"물에 불려"라고 하면
    그 행의 정답은 `건표고버섯`이다. 이름 단위 정답지로는 표현할 수 없다 (D-029).
    """
    if not ROW_ANSWERS.exists():
        return {}
    out = {}
    for r in csv.DictReader(ROW_ANSWERS.open(encoding="utf-8-sig")):
        if not r.get("확정", "").strip():
            continue
        for seq in str(r["seq"]).split(";"):
            if seq.strip():
                out[(r["source"], str(r["source_id"]), seq.strip())] = r["확정"].strip()
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    out_path = Path(sys.argv[1])
    if not out_path.exists():
        print("없음: %s" % out_path, file=sys.stderr)
        return 1

    answer, verdict = load_answers()
    row_answer = load_row_answers()
    vocab = {l.strip() for l in VOCAB.open(encoding="utf-8")
             if l.strip() and not l.startswith("#")}
    rows = list(csv.DictReader(out_path.open(encoding="utf-8-sig")))
    for col in ("name_raw", "표준명"):
        if rows and col not in rows[0]:
            print("컬럼 없음: %s (필요: source, source_id, seq, name_raw, 표준명)" % col, file=sys.stderr)
            return 1

    # 원본 대조 — 없는 재료명을 지어냈거나 행을 빠뜨렸는지
    corpus = defaultdict(set)
    rowcount = Counter()
    for x in json.load(INGREDIENTS.open(encoding="utf-8")):
        if x.get("name_raw"):
            key = (x["source"], str(x["source_id"]))
            corpus[key].add(x["name_raw"])
            rowcount[key] += 1
    ghost = [r for r in rows
             if r["name_raw"] not in corpus.get((r.get("source", ""), str(r.get("source_id", ""))), set())]

    # 기대 행 수 — 파일럿 명세에서 계산한다. 행이 빠지거나 늘면 채점 자체가 성립하지 않는다.
    expected = None
    if PILOT.exists():
        picks = [tuple(l.split("\t")) for l in PILOT.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
        expected = sum(rowcount[k] for k in picks)
        if expected != len(rows):
            print("[오류] 행 수 불일치 — 기대 %d행, 제출 %d행. 채점을 중단합니다."
                  % (expected, len(rows)), file=sys.stderr)
            return 1

    scored, hits = [], []
    skipped_ctx, unknown = [], []
    row_hit = 0
    for r in rows:
        n, got = r["name_raw"], r["표준명"].strip()
        key = (r.get("source", ""), str(r.get("source_id", "")), str(r.get("seq", "")))
        if key in row_answer:          # 행 단위 정답이 이름 단위보다 우선한다
            row_hit += 1
            scored.append((n, got, row_answer[key], "맥락"))
            hits.append(got == row_answer[key])
            continue
        if n in CONTEXT_DEPENDENT:
            skipped_ctx.append((n, got, answer.get(n, "-")))
            continue
        if n not in answer:
            unknown.append(n)
            continue
        scored.append((n, got, answer[n], verdict.get(n, "-")))
        hits.append(got == answer[n])

    total = len(scored)
    ok = sum(hits)
    # 어휘 위반은 채점 대상뿐 아니라 제출한 모든 행에서 본다 —
    # 정답지 밖 재료명에 지어낸 표준명을 붙인 것도 결함이다.
    oov = [(r["name_raw"], r["표준명"].strip()) for r in rows
           if r["표준명"].strip() and r["표준명"].strip() not in vocab
           and not (r.get("근거") or "").strip().startswith("어휘없음")]

    by_verdict = defaultdict(lambda: [0, 0])
    for (_n, got, exp, v), good in zip(scored, hits):
        by_verdict[v][0] += good
        by_verdict[v][1] += 1

    print("입력 %s — %d행" % (out_path.name, len(rows)))
    print("채점 대상 %d행 (정답지 밖 %d행 · 맥락 의존 %d행 제외 · 행 단위 정답 적용 %d행)"
          % (total, len(unknown), len(skipped_ctx), row_hit))
    if total:
        print("\n■ 일치율  %d/%d = %.1f%%" % (ok, total, 100 * ok / total))
        print("\n판정 유형별")
        for v, (g, t) in sorted(by_verdict.items(), key=lambda kv: -kv[1][1]):
            print("   %-6s %4d/%-4d  %5.1f%%" % (v, g, t, 100 * g / t if t else 0))
    print("\n어휘 밖 표준명 %d건%s" % (len(oov), (" — " + ", ".join(sorted({g for _n, g in oov})[:8])) if oov else ""))
    print("원본에 없는 행 %d건" % len(ghost))
    if skipped_ctx:
        agree = sum(1 for _n, g, a in skipped_ctx if g == a)
        print("맥락 의존 %d행 (참고용, 본 집계 제외) — 정답지와 우연 일치 %d건" % (len(skipped_ctx), agree))

    miss = [(n, g, e, v) for (n, g, e, v), good in zip(scored, hits) if not good]
    lines = ["# 정규화 채점 보고서", "", "입력: `%s`" % out_path.as_posix(), "",
             "| 항목 | 값 |", "| --- | ---: |",
             "| 제출 행 | %d |" % len(rows),
             "| 채점 대상 | %d |" % total,
             "| 일치 | %d |" % ok,
             "| **일치율** | **%.1f%%** |" % (100 * ok / total if total else 0),
             "| 어휘 밖 표준명 | %d |" % len(oov),
             "| 원본에 없는 행 | %d |" % len(ghost),
             "| 정답지 밖(미채점) | %d |" % len(unknown),
             "| 맥락 의존(제외) | %d |" % len(skipped_ctx), ""]
    lines += ["## 판정 유형별", "", "| 판정 | 일치 | 대상 | 일치율 |", "| --- | ---: | ---: | ---: |"]
    for v, (g, t) in sorted(by_verdict.items(), key=lambda kv: -kv[1][1]):
        lines.append("| %s | %d | %d | %.1f%% |" % (v, g, t, 100 * g / t if t else 0))
    if miss:
        lines += ["", "## 불일치 %d건" % len(miss), "",
                  "| 재료명 | 제출 | 정답 | 판정 |", "| --- | --- | --- | --- |"]
        lines += ["| %s | %s | %s | %s |" % (n, g or "(빈칸)", e, v)
                  for n, g, e, v in sorted(miss, key=lambda x: x[3])]
    if unknown:
        c = Counter(unknown)
        lines += ["", "## 정답지 밖 재료명 %d종 (채점 불가)" % len(c), "",
                  ", ".join("`%s`(%d)" % kv for kv in c.most_common(40))]
    report = out_path.with_suffix(out_path.suffix + ".score.md")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n상세 보고서: %s" % report.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
