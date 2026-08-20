# -*- coding: utf-8 -*-
"""채점 결과를 분해한다 — 배치별·출처별·재료명별·미배정 행별.

`score_normalization.py` 가 내는 공식 일치율 하나로는 보이지 않는 것을 본다.

  * 배치별 일치율 — 12배치로 쪼개 실행한 판단이 배치마다 흔들렸는가 (D-038 한계)
  * 출처별 일치율 — 식약처/농정원 코퍼스 격차가 정확도로도 나타나는가 (D-039)
  * 불일치 상위 재료명 — 어디를 고쳐야 하는가
  * 어휘없음·판별불가 행 — "모르겠다"고 표시한 것이 실제로 몰라도 되는 것이었는가

정답 판정 규칙은 재구현하지 않는다. `score_normalization` 에서 그대로 가져다 쓴다.

    python scripts/analyze_normalization.py data/labels/stage2_full_output.csv

산출: 표준 출력에 요약, `<입력파일>.breakdown.md` 에 상세.
표준 라이브러리만 사용한다.
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from score_normalization import (CONTEXT_DEPENDENT, ROOT, load_answers,
                                 load_row_answers)

BATCHES = ROOT / "data" / "labels" / "batches.txt"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def rate(good, total):
    return 100.0 * good / total if total else 0.0


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    out_path = Path(sys.argv[1])
    answer, verdict = load_answers()
    row_answer = load_row_answers()
    rows = list(csv.DictReader(out_path.open(encoding="utf-8-sig")))

    batch_of = {}
    for line in BATCHES.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        bid, source, sid = line.split("\t")
        batch_of[(source, sid)] = bid

    by_batch = defaultdict(lambda: [0, 0])
    by_source = defaultdict(lambda: [0, 0])
    by_name = defaultdict(lambda: [0, 0])
    miss_pairs = Counter()
    row_detail = []
    unscored = []          # 정답지 밖 — 채점 자체가 불가능한 행

    for r in rows:
        n = r["name_raw"]
        got = r["표준명"].strip()
        why = (r.get("근거") or "").strip()
        key = (r.get("source", ""), str(r.get("source_id", "")), str(r.get("seq", "")))
        if key in row_answer:
            exp, kind = row_answer[key], "맥락"
        elif n in CONTEXT_DEPENDENT:
            continue
        elif n in answer:
            exp, kind = answer[n], verdict.get(n, "-")
        else:
            unscored.append((n, got, why))
            continue
        good = got == exp
        b = batch_of.get((r.get("source", ""), str(r.get("source_id", ""))), "??")
        for bucket, k in ((by_batch, b), (by_source, r.get("source", "")), (by_name, n)):
            bucket[k][0] += good
            bucket[k][1] += 1
        if not good:
            miss_pairs[(n, got, exp, kind)] += 1
        if kind == "맥락":
            row_detail.append((key, n, got, exp, good, why))

    tot_g = sum(v[0] for v in by_batch.values())
    tot_t = sum(v[1] for v in by_batch.values())

    # 미배정 행 — "모르겠다"고 낸 것이 정답지에 있었는지
    oov_rows = [r for r in rows if (r.get("근거") or "").strip().startswith("어휘없음")]
    und_rows = [r for r in rows if "판별불가" in (r.get("근거") or "")]
    overlap = {id(r) for r in oov_rows} & {id(r) for r in und_rows}

    def answerable(subset):
        inside = [r for r in subset if r["name_raw"] in answer]
        agree = [r for r in inside if r["표준명"].strip() == answer[r["name_raw"]]]
        return inside, agree

    oov_in, oov_ok = answerable(oov_rows)
    und_in, und_ok = answerable(und_rows)

    L = []
    def emit(s=""):
        print(s)
        L.append(s)

    emit("입력 %s — %d행, 채점 대상 %d행, 일치 %d (%.1f%%)"
         % (out_path.name, len(rows), tot_t, tot_g, rate(tot_g, tot_t)))
    emit()
    emit("## 출처별")
    emit()
    emit("| 출처 | 일치 | 대상 | 일치율 |")
    emit("| --- | ---: | ---: | ---: |")
    for k, (g, t) in sorted(by_source.items(), key=lambda kv: -kv[1][1]):
        emit("| %s | %d | %d | %.2f%% |" % (k, g, t, rate(g, t)))
    emit()
    emit("## 배치별")
    emit()
    emit("| 배치 | 일치 | 대상 | 일치율 |")
    emit("| --- | ---: | ---: | ---: |")
    for k in sorted(by_batch):
        g, t = by_batch[k]
        emit("| %s | %d | %d | %.2f%% |" % (k, g, t, rate(g, t)))
    emit()
    emit("## 불일치 상위 재료명")
    emit()
    emit("| 재료명 | 제출 | 정답 | 판정 | 건수 | 그 이름의 전체 행 |")
    emit("| --- | --- | --- | --- | ---: | ---: |")
    for (n, got, exp, kind), c in miss_pairs.most_common(40):
        emit("| %s | %s | %s | %s | %d | %d |" % (n, got or "(빈칸)", exp, kind, c, by_name[n][1]))
    emit()
    emit("## 행 단위 정답 %d건" % len(row_detail))
    emit()
    emit("| source | id | seq | 재료명 | 제출 | 정답 | 결과 |")
    emit("| --- | ---: | ---: | --- | --- | --- | --- |")
    for (s_, i_, q_), n, got, exp, good, why in sorted(row_detail):
        emit("| %s | %s | %s | %s | %s | %s | %s |"
             % (s_, i_, q_, n, got or "(빈칸)", exp, "O" if good else "X"))
    emit()
    emit("## 미배정 행 — 정답지에 있었는가")
    emit()
    emit("| 구분 | 행 | 고유명 | 정답지 안 | 그중 정답과 일치 |")
    emit("| --- | ---: | ---: | ---: | ---: |")
    emit("| 어휘없음 | %d | %d | %d | %d |"
         % (len(oov_rows), len({r["name_raw"] for r in oov_rows}), len(oov_in), len(oov_ok)))
    emit("| 판별불가 | %d | %d | %d | %d |"
         % (len(und_rows), len({r["name_raw"] for r in und_rows}), len(und_in), len(und_ok)))
    emit("| (겹침) | %d | | | |" % len(overlap))
    if oov_in or und_in:
        emit()
        emit("정답지에 있었던 미배정 재료명: "
             + ", ".join("`%s`(%d)" % kv for kv in
                         Counter(r["name_raw"] for r in oov_in + und_in).most_common(30)))
    emit()
    emit("## 정답지 밖 %d행 — 상위 재료명" % len(unscored))
    emit()
    emit(", ".join("`%s`(%d)" % kv for kv in Counter(n for n, _g, _w in unscored).most_common(40)))

    report = out_path.with_suffix(out_path.suffix + ".breakdown.md")
    report.write_text("# 정규화 채점 분해" + chr(10) * 2 + chr(10).join(L) + chr(10),
                      encoding="utf-8")
    print()
    print("상세: %s" % report.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
