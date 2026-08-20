# -*- coding: utf-8 -*-
"""식약처 조리식품 레시피 원천 데이터 1단계 정제 규칙.

`RCP_PARTS_DTLS` 한 덩어리 문자열을 재료 행으로 분해한다.
규칙으로 갈라지지 않는 조각은 버리지 않고 `unparsed`로 돌려준다.
"""
import re

FRACTIONS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
QTY_WORDS = ("적당량", "약간", "조금", "소량")
UNITS = (
    r"(?:g|kg|mg|ml|㎖|㎗|ℓ|L|cc|㏄|개|장|마리|컵|줌|봉|모|쪽|줄기|대|알|팩|통|스푼|"
    r"큰술|작은술|Ts|ts|T|t)"
)

# 수량 꼬리표: 숫자(또는 유니코드 분수)로 시작해 단위로 끝난다.
QTY_TAIL_RE = re.compile(
    r"(?:(?<=\s)|^)([0-9%s][0-9%s/.\-~×xX*= ]*[a-zA-Z가-힣㎖㎗ℓ㏄%%]{0,6})\s*$" % (FRACTIONS, FRACTIONS)
)
# 띄어쓰기가 빠진 '양파20g' 형태. 단위가 확실할 때만 가른다 ('또띠아8인치'는 이름이다).
GLUED_QTY_TAIL_RE = re.compile(
    r"(?<=[가-힣)\]])([0-9%s][0-9%s/.\-~]*\s*%s)\s*$" % (FRACTIONS, FRACTIONS, UNITS)
)
QTY_ANY_RE = re.compile(
    r"(?:(?<=\s)|^)[0-9%s][0-9%s/.\-~×xX*=]*[a-zA-Z가-힣㎖㎗ℓ㏄%%]{0,6}" % (FRACTIONS, FRACTIONS)
)
QTY_WORD_TAIL_RE = re.compile(r"(%s)\s*$" % "|".join(QTY_WORDS))

# 재료명 안에 수량이 남아 있으면 두 항목이 붙어 있는 것이다 — 쪼개지 말고 잔여로 넘긴다.
UNIT_IN_NAME_RE = re.compile(
    r"[0-9%s]\s*(?:g|kg|mg|ml|㎖|㎗|ℓ|L|cc|㏄|개|장|마리|컵|줌|봉|모|쪽|줄기|큰술|작은술|Ts|ts)" % FRACTIONS
)

SERVINGS_RE = re.compile(r"^\s*(?:\[\s*)?(\d+(?:~\d+)?\s*인분(?:\s*기준)?)\s*\]?\s*")
SERVINGS_INLINE_RE = re.compile(r"^\d+(?:~\d+)?\s*인분\s+(?=\S)")

# 재료 항목 앞에 그룹 헤더가 붙어 남는 세 형태.
#   '(반죽재료) 강력분'  /  '주재료   달걀흰자'  /  '양념 다진 마늘'
LEADING_PAREN_HEADER_RE = re.compile(r"^\(\s*([^()]{1,20})\s*\)\s*(?=\S)")
MULTISPACE_RE = re.compile(r"[ 	]{2,}")
HEADER_WORDS = ("주재료", "부재료", "재료", "양념장", "양념", "소스")
HEADER_WORD_RE = re.compile(r"^(%s)\s+(?=\S)" % "|".join(HEADER_WORDS))
MAX_INLINE_HEADER_LEN = 12
# 레시피마다 이름이 다른 그룹 헤더는 접미사로 알아본다 ('톳 무침양념 설탕', '육수 무').
# 마지막 토큰은 재료명이므로 그 앞 토큰이 이 접미사로 끝날 때만 가른다.
GROUP_SUFFIX_RE = re.compile(
    r"(?:양념장|양념|소스|육수용|육수|밑간|반죽|토핑|고명|장식|조림장|드레싱|국물|무침)$"
)
QTY_HEAD_RE = re.compile(r"^(?:[0-9%s]|%s)" % (FRACTIONS, "|".join(QTY_WORDS)))

# 원문 표기 잔재. 재료 본체가 아니므로 이름에서 떼어낸다.
CIRCLED_RE = re.compile(r"[①-⑳]")
# 앞에 공백이 있을 때만 수량 수식어다. '팔각'·'노각'은 재료 이름이다.
EACH_TAIL_RE = re.compile(r"\s+각각?\s*$")
LABEL_TRIM_CHARS = "-•·●*>＞ 	"
BRACKET_RE = re.compile(r"\[\s*([^\[\]\n]{1,40}?)\s*\]")
BULLET_CHARS = "●•·◦‣▪-*>＞ \t"
STEP_NUMBER_RE = re.compile(r"^\s*\d{1,2}\.\s*(?=\D)")
TAG_RE = re.compile(r"<[^>]*>")


class Item(object):
    __slots__ = ("group_name", "name_raw", "qty_raw")

    def __init__(self, group_name, name_raw, qty_raw):
        self.group_name = group_name
        self.name_raw = name_raw
        self.qty_raw = qty_raw

    def __repr__(self):
        return "Item(%r, %r, %r)" % (self.group_name, self.name_raw, self.qty_raw)


class ParseResult(object):
    __slots__ = ("servings_raw", "items", "unparsed", "title_lines")

    def __init__(self, servings_raw, items, unparsed, title_lines):
        self.servings_raw = servings_raw
        self.items = items
        self.unparsed = unparsed
        self.title_lines = title_lines


def normalize_html(text):
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = TAG_RE.sub(" ", text)
    return text.replace("<", " ").replace(">", " ")


def strip_step_number(description):
    """'1. 손질된 새우를 데친다.' -> '손질된 새우를 데친다.'"""
    return STEP_NUMBER_RE.sub("", description.strip()).strip()


def extract_servings(text):
    """앞머리의 인분 표기를 떼어 (인분, 나머지)로 돌려준다."""
    m = SERVINGS_RE.match(text)
    if not m:
        return (None, text)
    return (re.sub(r"\s+", " ", m.group(1)).strip(), text[m.end():])


def _matching_open(text):
    """끝의 ')'와 짝을 이루는 '('의 위치. 짝이 없으면 None."""
    depth = 0
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
            if depth == 0:
                return i
    return None


def _parens_balanced(text):
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def split_top_level(text, delimiters=",\n"):
    """괄호 안의 쉼표는 자르지 않는다. 괄호가 짝이 안 맞으면 깊이를 무시한다."""
    track_depth = _parens_balanced(text)
    out = []
    buf = []
    depth = 0
    for ch in text:
        if track_depth and ch == "(":
            depth += 1
        elif track_depth and ch == ")":
            depth = max(0, depth - 1)
        if ch in delimiters and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


def _clean_name(name):
    name = name.strip().strip(",.;·•●[]").strip()
    # 짝이 맞는 괄호는 이름의 일부다 ('황태(채)'). 짝이 없는 것만 떼어낸다.
    while name and not _parens_balanced(name):
        if name[-1] in "()":
            name = name[:-1].strip()
        elif name[0] in "()":
            name = name[1:].strip()
        else:
            break
    return name.strip(",.;").strip()


def _qty_tail(text):
    """문자열 끝의 수량 표기가 시작되는 위치. 없으면 None."""
    for pattern in (QTY_TAIL_RE, GLUED_QTY_TAIL_RE):
        m = pattern.search(text)
        if m and m.start(1) > 0:
            return m.start(1)
    return None


def split_name_qty(item):
    """'연두부 75g(3/4모)' -> ('연두부', '75g(3/4모)'). 못 가르면 None."""
    s = item.strip().strip(",").strip()
    if not s:
        return None

    if s.endswith(")"):
        open_idx = _matching_open(s)
        if open_idx is not None and open_idx > 0:
            head = s[:open_idx].strip()
            inside = s[open_idx + 1:-1].strip()
            start = _qty_tail(head)
            if start is not None:
                name = _clean_name(head[:start])
                qty = s[start:].strip()
            else:
                name = _clean_name(head)
                qty = inside
            if name and not UNIT_IN_NAME_RE.search(name):
                return (name, qty)
            return None

    start = _qty_tail(s)
    if start is not None:
        name = _clean_name(s[:start])
        qty = s[start:].strip()
        if name and not UNIT_IN_NAME_RE.search(name):
            return (name, qty)
        return None

    m = QTY_WORD_TAIL_RE.search(s)
    if m and m.start(1) > 0:
        name = _clean_name(s[:m.start(1)])
        qty = m.group(1)
        if name and not UNIT_IN_NAME_RE.search(name):
            return (name, qty)
    return None


def _strip_bullets(line):
    return line.strip().lstrip(BULLET_CHARS).strip()


def _clean_label(label):
    """그룹명 앞에 남은 불릿·하이픈을 떼어낸다 ('- 양념장' -> '양념장')."""
    if not label:
        return label
    return label.strip().strip(LABEL_TRIM_CHARS).strip() or None


def _compose_group(section, label):
    section = _clean_label(section)
    label = _clean_label(label)
    if section and label:
        return "%s > %s" % (section, label)
    return label or section


def strip_inline_header(piece):
    """항목 앞에 붙어 남은 그룹 헤더를 떼어 (헤더, 나머지)로 돌려준다.

    헤더가 겹쳐 붙은 경우('닭뼈육수 재료 닭뼈')가 있어 더 떼어낼 것이 없을 때까지 반복한다.
    """
    label, text = None, piece.strip()
    for _ in range(3):
        found, text = _strip_one_header(text)
        if not found:
            break
        label = found
    return (label, text)


def _strip_one_header(piece):
    label = None
    s = piece.strip()

    m = LEADING_PAREN_HEADER_RE.match(s)
    if m:
        label = m.group(1).strip()
        s = s[m.end():].strip()

    parts = MULTISPACE_RE.split(s, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        head, tail = parts[0].strip(), parts[1].strip()
        # 뒤가 수량으로 시작하면 헤더가 아니라 '재료  수량'이 벌어진 것이다.
        if len(head) <= MAX_INLINE_HEADER_LEN and not QTY_HEAD_RE.match(tail):
            label = head
            s = tail

    m = HEADER_WORD_RE.match(s)
    if m:
        label = m.group(1)
        s = s[m.end():].strip()

    # 헤더는 항목 맨 앞 한두 토큰이다. 아직 여러 항목이면 항목 단위로 갈린 뒤에 다룬다.
    # 괄호 안의 쉼표는 항목 구분이 아니다 ('육수 돼지고기(삼겹살, 60g)').
    if len(split_top_level(s)) == 1:
        tokens = s.split()
        for i in range(min(2, len(tokens) - 1), 0, -1):
            rest = " ".join(tokens[i:])
            # 뒤가 수량뿐이면 헤더가 아니라 '육수 200g' 같은 재료다.
            if GROUP_SUFFIX_RE.search(tokens[i - 1]) and not QTY_HEAD_RE.match(rest):
                label = " ".join(tokens[:i])
                s = rest
                break

    m = SERVINGS_INLINE_RE.match(s)
    if m:
        s = s[m.end():].strip()

    return (_clean_label(label), s)


def tidy_name(name):
    """재료명에 남은 원문 표기 잔재를 떼어낸다. 표준화는 하지 않는다."""
    name = CIRCLED_RE.sub("", name)
    name = EACH_TAIL_RE.sub("", name)
    return name.strip().strip(",.;").strip()


def name_is_broken(name):
    """괄호나 대괄호 짝이 깨진 이름 — 원본이 잘린 것이므로 잔여로 넘긴다."""
    return ("[" in name) or ("]" in name) or (not _parens_balanced(name))


def _split_label_and_item(left):
    """콜론 앞부분을 (앞선 재료 항목, 새 그룹명)으로 가른다."""
    left = left.strip()
    last = None
    for m in QTY_ANY_RE.finditer(left):
        last = m
    if last and last.end() < len(left):
        trailing = left[last.end():].strip()
        if trailing:
            return (left[:last.end()].strip(), trailing)
    return (None, left)


def parse_ingredients(raw, recipe_name=""):
    """RCP_PARTS_DTLS 한 덩어리를 재료 행으로 분해한다."""
    items = []
    unparsed = []
    titles = []
    if not raw or not raw.strip():
        return ParseResult(None, items, unparsed, titles)

    text = normalize_html(raw)
    servings, text = extract_servings(text)
    name_key = re.sub(r"\s+", "", recipe_name or "")
    current_group = None

    for rawline in text.split("\n"):
        line = _strip_bullets(rawline)
        if not line:
            continue

        # 줄 앞에 붙은 그룹 헤더를 떼어낸다.
        #   '재료 굴(40g), 멸치(2g)'  '(반죽재료) 강력분 300g'  '주재료   달걀흰자 180g'
        inline_label, remainder = strip_inline_header(line)
        if inline_label and remainder:
            current_group = inline_label
            line = remainder

        # 대괄호 그룹 헤더를 경계로 잘라 (섹션명, 본문) 조각을 만든다.
        segments = []
        pos = 0
        section = None
        for m in BRACKET_RE.finditer(line):
            chunk = line[pos:m.start()].strip()
            if chunk:
                segments.append((section, chunk))
            section = m.group(1)
            pos = m.end()
        tail = line[pos:].strip()
        if tail or not segments:
            segments.append((section, tail))

        for section, body in segments:
            body = body.strip().lstrip("[").strip()
            if section is not None:
                current_group = section
            if not body:
                continue
            current_group = _consume_body(
                body, section, current_group, items, unparsed, titles, name_key
            )

    return ParseResult(servings, items, unparsed, titles)


def _consume_body(body, section, current_group, items, unparsed, titles, name_key):
    pieces = split_top_level(body)
    produced_any = False
    for piece in pieces:
        while True:
            if ":" in piece or "：" in piece:
                head, rest = re.split(r"[:：]", piece, maxsplit=1)
                lead_item, label = _split_label_and_item(head)
                if lead_item:
                    if _emit(lead_item, current_group, items, unparsed):
                        produced_any = True
                if label:
                    current_group = _compose_group(section, label)
                piece = rest.strip()
                if not piece:
                    break
                continue
            break
        if not piece:
            continue
        # 원문의 '크림치즈 > 우유'는 normalize_html이 '>'를 지워 공백만 남는다.
        # 줄 중간에서도 헤더를 되살린다.
        piece_label, stripped = strip_inline_header(piece)
        if piece_label and stripped:
            current_group = _compose_group(section, piece_label)
            piece = stripped
        item = _build_item(piece, current_group)
        if item is not None:
            items.append(item)
            produced_any = True
        elif len(pieces) == 1 and not produced_any:
            # 수량이 없는 홑줄 — 요리명이거나 섹션 라벨이다.
            if re.sub(r"\s+", "", piece) == name_key:
                titles.append(piece)
            else:
                current_group = _compose_group(section, piece)
        else:
            unparsed.append(piece)
    return current_group


def _build_item(piece, group):
    """항목 하나를 재료 행으로 만든다. 만들 수 없으면 None — 부작용은 없다."""
    parsed = split_name_qty(piece)
    if not parsed:
        return None
    name = tidy_name(parsed[0])
    if not name or name_is_broken(name):
        return None
    return Item(group, name, parsed[1])


def _emit(piece, group, items, unparsed):
    """콜론 앞에 붙어 있던 선행 항목을 행으로 만든다. 만들었으면 True."""
    item = _build_item(piece, group)
    if item is None:
        unparsed.append(piece)
        return False
    items.append(item)
    return True
