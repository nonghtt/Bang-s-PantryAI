# -*- coding: utf-8 -*-
"""career-source.md 인덱스 생성 및 무결성 검사.

씨드(`docs/career-source.md`)는 사람이 읽지 않는다. 세션이 인덱스만 읽고
필요한 항목만 조회할 수 있도록 인덱스를 생성하고, 손으로는 지키기 어려운
규칙(ID 중복·끊어진 참조·관계 비대칭·수치 불일치)을 검사한다.

    python scripts/career_index.py           # 검사 + 인덱스 재생성
    python scripts/career_index.py --check   # 검사만 (쓰기 없음)

표준 라이브러리만 사용한다. 오류가 있으면 인덱스를 쓰지 않고 종료 코드 1.
"""
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # 콘솔이 cp949여도 한글이 깨지지 않게
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

SRC = Path(__file__).resolve().parent.parent / "docs" / "career-source.md"

FIELDS_REQUIRED = ["date", "status", "scope", "basis", "verified", "strength"]
REL_FIELDS = ["refines", "refined_by", "supersedes", "superseded_by", "implements", "instances"]
ENUM = {
    "status": {"live", "refined", "superseded"},
    "basis": {"실측", "도메인지식", "제품목적", "관례"},
    "verified": {"yes", "no", "partial"},
    "strength": {"high", "mid", "low"},
}
STORY = {
    "측정이_판단을_뒤집음", "트레이드오프를_수치로", "배제_판단", "전제_오류_수정",
    "검증을_먼저", "정직성_경계", "자동화_함정", "실무경험_적용",
}
# 관계는 쌍으로 유지된다: A에 왼쪽 필드가 있으면 대상 B에 오른쪽 필드가 있어야 한다
MIRROR = {"refines": "refined_by", "supersedes": "superseded_by", "implements": "instances"}
# status 가 이 값이면 해당 관계 필드가 반드시 있어야 한다
STATUS_NEEDS = {"refined": "refined_by", "superseded": "superseded_by"}

ENTRY_RE = re.compile(r"^## (D-\d{3}) (.+)$", re.M)
FIELD_RE = re.compile(r"^- (\w+):\s*(.*)$")
METRIC_NOUNS = ["고유 재료명", "재료명", "레시피", "표준명", "카테고리"]
VERIFIED_MARK = {"yes": "✓", "no": "✗", "partial": "△"}


def parse(text):
    """decisions 섹션의 항목을 [(id, title, fields, body)] 로 돌려준다."""
    if "## decisions" not in text:
        return []
    body = text.split("## decisions", 1)[1].split("\n---\n\n## cases", 1)[0]
    marks = list(ENTRY_RE.finditer(body))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        seg = body[m.end():end]
        fields = {}
        for line in seg.splitlines():
            fm = FIELD_RE.match(line.strip())
            if fm:
                raw = fm.group(2).strip()
                fields[fm.group(1)] = [v.strip() for v in raw.split(",") if v.strip()]
        out.append((m.group(1), m.group(2).strip(), fields, seg))
    return out


def width(s):
    """마크다운 표 정렬용 — 전각 문자를 2칸으로 센다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def check(entries):
    errors, warns = [], []
    ids = [e[0] for e in entries]
    for dup_id in sorted({x for x in ids if ids.count(x) > 1}):
        errors.append("ID 중복: " + dup_id)

    known = set(ids)
    byid = {e[0]: e for e in entries}

    for eid, _title, f, seg in entries:
        for key in FIELDS_REQUIRED:
            if key not in f:
                errors.append("%s 필수 필드 누락: %s" % (eid, key))
        for key, allowed in ENUM.items():
            for val in f.get(key, []):
                if val not in allowed:
                    errors.append("%s %s 값 오류: %s (허용: %s)" % (eid, key, val, "/".join(sorted(allowed))))
        for val in f.get("story", []):
            if val not in STORY:
                warns.append("%s 미등록 story 태그: %s" % (eid, val))
        for val in f.get("date", []):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
                errors.append("%s date 형식 오류: %s" % (eid, val))
        for key in REL_FIELDS:
            for ref in f.get(key, []):
                if ref not in known:
                    errors.append("%s %s 대상 없음: %s" % (eid, key, ref))

        status = (f.get("status") or [""])[0]
        need = STATUS_NEEDS.get(status)
        if need and not f.get(need):
            errors.append("%s status=%s 인데 %s 없음" % (eid, status, need))
        if status == "live":
            for key in ("refined_by", "superseded_by"):
                if f.get(key):
                    errors.append("%s status=live 인데 %s 있음" % (eid, key))
        if "**문제**" not in seg or "**선택**" not in seg:
            warns.append("%s 본문에 **문제**/**선택** 라벨 없음" % eid)

    for eid, _title, f, _seg in entries:
        for left, right in MIRROR.items():
            for ref in f.get(left, []):
                if ref in byid and eid not in byid[ref][2].get(right, []):
                    errors.append("관계 비대칭: %s.%s=%s 인데 %s.%s 에 %s 없음"
                                  % (eid, left, ref, ref, right, eid))
    return errors, warns


def numeric_scan(text):
    """추적 대상 지표에 서로 다른 수치가 쓰였는데 범위 주석이 없으면 보고한다.

    느슨한 명사 추출은 조사 조각(`에서`·`재료명이`)까지 잡아 오탐만 늘었다.
    추적할 지표를 명시하고, 값 뒤 괄호에 범위·시점이 붙어 있으면 정상으로 본다.
    """
    inside = [(m.start(), m.end()) for m in re.finditer(r"\([^()\n]*\)", text)]

    def in_paren(pos):
        return any(a < pos < b for a, b in inside)

    seen = defaultdict(set)
    for noun in METRIC_NOUNS:
        pat = re.escape(noun) + r"[^.\n]{0,12}?\**([\d][\d,]{2,})\s*(종|건)\**(\s*\([^)]*\))?"
        for m in re.finditer(pat, text):
            if m.group(3):        # 값 뒤에 범위·시점 주석이 붙어 있으면 통과
                continue
            if in_paren(m.start(1)):  # 이미 주석 괄호 안의 값이면 통과
                continue
            seen[noun].add(m.group(1) + m.group(2))
    return {k: sorted(v) for k, v in seen.items() if len(v) > 1}


def build_index(entries):
    rows = [("ID", "제목", "날짜", "상태", "scope", "basis", "✓", "강도", "story")]
    for eid, title, f, _seg in entries:
        joined = lambda key: "·".join(f.get(key, [])) or "-"
        status = (f.get("status") or ["-"])[0]
        for key, arrow in (("refined_by", "→"), ("superseded_by", "⇒")):
            if f.get(key):
                status += " %s%s" % (arrow, f[key][0])
        label = title + (" ⊂%s" % f["implements"][0] if f.get("implements") else "")
        rows.append((
            eid, label, (f.get("date") or ["-"])[0][5:], status,
            joined("scope"), joined("basis"),
            VERIFIED_MARK.get((f.get("verified") or [""])[0], "?"),
            (f.get("strength") or ["-"])[0], joined("story"),
        ))
    widths = [max(width(r[i]) for r in rows) for i in range(len(rows[0]))]

    def render(row):
        cells = [c + " " * (widths[i] - width(c)) for i, c in enumerate(row)]
        return "| " + " | ".join(cells) + " |"

    lines = [render(rows[0]), "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    lines += [render(r) for r in rows[1:]]
    return "\n".join(lines)


def main():
    if not SRC.exists():
        print("없음: %s" % SRC, file=sys.stderr)
        return 1
    text = SRC.read_text(encoding="utf-8")
    entries = parse(text)
    if not entries:
        print("decisions 항목을 찾지 못했습니다.", file=sys.stderr)
        return 1

    errors, warns = check(entries)
    dup = numeric_scan(text)

    counts = defaultdict(int)
    for _eid, _t, f, _s in entries:
        counts[(f.get("status") or ["?"])[0]] += 1
    print("항목 %d개 — %s" % (len(entries), " · ".join("%s %d" % kv for kv in sorted(counts.items()))))
    print("강도 high %d / 미검증(no·partial) %d"
          % (sum(1 for e in entries if e[2].get("strength") == ["high"]),
             sum(1 for e in entries if e[2].get("verified") in (["no"], ["partial"]))))

    if dup:
        print("\n[주의] 같은 명사에 다른 수치 — 시점·범위 주석이 필요합니다")
        for k, v in sorted(dup.items()):
            print("   %s: %s" % (k, ", ".join(v)))
    for w in warns:
        print("[경고] " + w)
    for e in errors:
        print("[오류] " + e, file=sys.stderr)
    if errors:
        print("\n오류 %d건 — 인덱스를 쓰지 않고 멈춥니다." % len(errors), file=sys.stderr)
        return 1

    if "--check" in sys.argv:
        print("\n검사만 수행했습니다 (--check).")
        return 0

    index = ("## 인덱스\n\n"
             "> 자동 생성 — `python scripts/career_index.py`. **직접 편집하지 않는다.**\n"
             "> 상태 `→` 정교화됨 · `⇒` 대체됨 · 제목의 `⊂` 는 상위 원칙 항목.\n\n"
             + build_index(entries) + "\n")

    if "## 인덱스" in text:
        head, rest = text.split("## 인덱스", 1)
        _old, tail = rest.split("\n---\n", 1)
        text = head + index + "\n---\n" + tail
    else:
        head, tail = text.split("\n---\n\n## meta", 1)
        text = head + "\n---\n\n" + index + "\n---\n\n## meta" + tail

    text = re.sub(r"최종 갱신: \d{4}-\d{2}-\d{2}", "최종 갱신: " + date.today().isoformat(), text)
    SRC.write_text(text, encoding="utf-8")
    print("\n인덱스 재생성 완료 (%d행)" % len(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
