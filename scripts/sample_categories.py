# -*- coding: utf-8 -*-
"""요리 계통 정답 세트의 표집 — 결정적 2층 층화 표집.

한 층으로 뽑으면 표본의 90% 이상이 한식이 되어 비한식 정확도를 잴 수 없다.
그래서 두 층으로 나눈다 (`data/labels/category_README.md` §4-2).

  (A) 대표 층 — 식약처 전량에서 `rcp_pat2` 비율대로. 전체 정확도의 대표값
  (B) 함정 층 — 요리명에 외래 계통 키워드가 걸리는 것에서. 어려운 구간의 정확도

무작위가 아니라 `source_id` 정렬 후 균등 간격이라 재현 가능하다 (D-034).
B는 A에 이미 뽑힌 것을 뺀 뒤 뽑아 120건이 서로 겹치지 않게 한다.

    python scripts/sample_categories.py            # 표집 + 정답지 골격 생성
    python scripts/sample_categories.py --check    # 기존 파일과 대조만 (쓰기 없음)

표준 라이브러리만 사용한다.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "data" / "processed" / "recipes.json"
SAMPLE = ROOT / "data" / "labels" / "category_sample.txt"
ANSWERS = ROOT / "data" / "labels" / "category_answers.csv"

N_PER_LAYER = 60

TAB = chr(9)
NLC = chr(10)

# 함정 층의 정의. 이 목록이 표집의 일부이므로 바꾸면 표본이 바뀐다 —
# 바꿀 때는 정답 세트를 다시 만들어야 한다.
KEYWORDS = {
    "양식": ["샐러드", "스테이크", "파스타", "피자", "샌드위치", "수프", "스프", "그라탕",
           "그라탱", "리조또", "리조토", "오믈렛", "브런치", "크림", "치즈", "버거",
           "토스트", "브리또", "타코", "라자냐", "뇨끼", "베이글", "머핀", "쿠키",
           "케이크", "타르트", "푸딩", "무스"],
    "중식": ["볶음밥", "짜장", "짬뽕", "탕수", "마파", "깐풍", "유린기", "춘권", "딤섬",
           "완자", "꽃빵", "팔보", "라조"],
    "일식": ["주먹밥", "돈까스", "돈가스", "우동", "초밥", "스시", "덮밥", "규동",
           "가라아게", "오코노미", "타코야키", "텐동", "라멘", "미소", "유부",
           "데리야끼", "데리야키"],
    "동남아": ["카레", "커리", "쌀국수", "월남쌈", "팟타이", "나시", "분짜", "반미",
            "똠얌", "사테"],
}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def even_pick(items, k):
    """정렬된 목록에서 균등 간격으로 k개. 무작위가 아니라 재현 가능하다."""
    n = len(items)
    if k >= n:
        return list(items)
    return [items[(i * n) // k] for i in range(k)]


def allocate(counts, total):
    """층별 비율대로 total 개를 나눈다. 최대잉여법으로 합이 정확히 total 이 된다."""
    grand = sum(counts.values())
    base, rem = {}, {}
    for k, v in counts.items():
        exact = v * total / grand
        base[k] = int(exact)
        rem[k] = exact - base[k]
    short = total - sum(base.values())
    for k in sorted(rem, key=lambda x: (-rem[x], x))[:short]:
        base[k] += 1
    return base


def keyword_hit(name):
    """요리명에 외래 계통 키워드가 있으면 (계통, 키워드). 없으면 None."""
    for cat in ("동남아", "일식", "중식", "양식"):
        for w in KEYWORDS[cat]:
            if w in name:
                return cat, w
    return None


def main():
    check = "--check" in sys.argv
    recipes = [r for r in json.load(RECIPES.open(encoding="utf-8"))
               if r["source"] == "mfds"]
    recipes.sort(key=lambda r: int(r["source_id"]))

    # (A) 대표 층 — rcp_pat2 비율대로
    strata = defaultdict(list)
    for r in recipes:
        strata[r.get("rcp_pat2") or "미분류"].append(r)
    quota = allocate({k: len(v) for k, v in strata.items()}, N_PER_LAYER)
    layer_a = []
    for k in sorted(strata):
        layer_a += even_pick(strata[k], quota[k])
    picked = {(r["source"], str(r["source_id"])) for r in layer_a}

    # (B) 함정 층 — 외래 키워드가 걸리는 것에서, A 와 겹치지 않게
    pool = [r for r in recipes
            if keyword_hit(r["name"] or "")
            and (r["source"], str(r["source_id"])) not in picked]
    layer_b = even_pick(pool, N_PER_LAYER)

    lines = ["# 요리 계통 정답 세트 표집 — 결정적 2층 층화 표집.",
             "# scripts/sample_categories.py 가 생성한다. 직접 편집하지 않는다.",
             "# layer<TAB>source<TAB>source_id<TAB>요리명",
             "# A=대표 층(rcp_pat2 비율) · B=함정 층(외래 키워드 %d건 중)" % len(pool)]
    for tag, rows in (("A", layer_a), ("B", layer_b)):
        for r in rows:
            lines.append(TAB.join([tag, r["source"], str(r["source_id"]), r["name"]]))
    text = NLC.join(lines) + NLC

    if check:
        old = SAMPLE.read_text(encoding="utf-8") if SAMPLE.exists() else ""
        print("재현 일치" if old == text else "[오류] 기존 표집과 다릅니다")
        return 0 if old == text else 1

    SAMPLE.write_text(text, encoding="utf-8")

    # 정답지 골격 — 이미 있으면 덮어쓰지 않는다 (사람이 채운 답을 지우지 않기 위해)
    if ANSWERS.exists():
        print("정답지 이미 존재 — 골격을 덮어쓰지 않습니다: %s" % ANSWERS.name)
    else:
        cols = ["층", "source", "source_id", "name", "카테고리", "sub", "근거축", "근거", "확신"]
        with ANSWERS.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator=NLC)
            w.writerow(cols)
            for tag, rows in (("A", layer_a), ("B", layer_b)):
                for r in rows:
                    w.writerow([tag, r["source"], r["source_id"], r["name"], "", "", "", "", ""])
        print("정답지 골격 생성: %s" % ANSWERS.name)

    print("(A) 대표 층 %d건 — 층별 배분 %s"
          % (len(layer_a), {k: quota[k] for k in sorted(quota)}))
    print("(B) 함정 층 %d건 — 후보 %d건 중" % (len(layer_b), len(pool)))
    c = Counter(keyword_hit(r["name"])[0] for r in layer_b)
    print("    함정 층의 키워드 계통 분포: %s" % dict(c.most_common()))
    print("표집 명세: %s" % SAMPLE.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
