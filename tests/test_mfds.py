# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from stage1 import mfds


class SplitNameQtyTest(unittest.TestCase):
    def test_splits_trailing_unit_with_paren_detail(self):
        self.assertEqual(mfds.split_name_qty("연두부 75g(3/4모)"), ("연두부", "75g(3/4모)"))

    def test_treats_sole_paren_group_as_quantity(self):
        self.assertEqual(mfds.split_name_qty("팽이버섯(½봉)"), ("팽이버섯", "½봉"))

    def test_keeps_comma_inside_paren_quantity(self):
        self.assertEqual(
            mfds.split_name_qty("소고기(불고기용 부채살, 200g)"), ("소고기", "불고기용 부채살, 200g")
        )

    def test_keeps_equals_inside_paren_quantity(self):
        self.assertEqual(mfds.split_name_qty("물(4컵=800g)"), ("물", "4컵=800g"))

    def test_keeps_descriptive_paren_inside_name(self):
        self.assertEqual(mfds.split_name_qty("황태(채) 15g(10개)"), ("황태(채)", "15g(10개)"))

    def test_splits_bare_number_quantity(self):
        self.assertEqual(mfds.split_name_qty("밥 180"), ("밥", "180"))

    def test_splits_non_numeric_quantity_word(self):
        self.assertEqual(mfds.split_name_qty("참깨 약간"), ("참깨", "약간"))

    def test_splits_quantity_word_glued_to_name(self):
        self.assertEqual(mfds.split_name_qty("소금적당량"), ("소금", "적당량"))

    def test_keeps_leading_digit_in_name(self):
        self.assertEqual(mfds.split_name_qty("2가지색 미니파프리카 70g"), ("2가지색 미니파프리카", "70g"))

    def test_splits_metric_unit_with_fraction_detail(self):
        self.assertEqual(mfds.split_name_qty("물 300ml(1½컵)"), ("물", "300ml(1½컵)"))

    def test_returns_none_when_no_quantity(self):
        self.assertIsNone(mfds.split_name_qty("유산지"))

    def test_returns_none_when_two_items_are_glued_together(self):
        self.assertIsNone(mfds.split_name_qty("흰후춧가루 0.1g레몬즙 5g"))


    def test_splits_quantity_glued_to_name_without_space(self):
        self.assertEqual(mfds.split_name_qty("양파20g"), ("양파", "20g"))

    def test_splits_glued_quantity_with_paren_detail(self):
        self.assertEqual(mfds.split_name_qty("레몬즙15g(1큰술)"), ("레몬즙", "15g(1큰술)"))

    def test_does_not_split_number_that_belongs_to_the_name(self):
        self.assertEqual(mfds.split_name_qty("또띠아8인치 30g"), ("또띠아8인치", "30g"))

    def test_splits_soryang_quantity_word(self):
        self.assertEqual(mfds.split_name_qty("시금치 소량"), ("시금치", "소량"))

    def test_drops_stray_open_paren_from_name(self):
        self.assertEqual(mfds.split_name_qty("두부((30g)"), ("두부", "30g"))


class SplitTopLevelTest(unittest.TestCase):
    def test_does_not_split_comma_inside_parens(self):
        self.assertEqual(
            mfds.split_top_level("파프리카(빨간색, 노란색 각 30g), 부추(10g)"),
            ["파프리카(빨간색, 노란색 각 30g)", "부추(10g)"],
        )

    def test_splits_plain_comma_list(self):
        self.assertEqual(mfds.split_top_level("연어 60g, 어린잎 20g"), ["연어 60g", "어린잎 20g"])


    def test_splits_on_comma_when_parens_are_unbalanced(self):
        self.assertEqual(
            mfds.split_top_level("두부((30g), 부추(20g)"), ["두부((30g)", "부추(20g)"]
        )


class ExtractServingsTest(unittest.TestCase):
    def test_extracts_bracketed_servings(self):
        self.assertEqual(mfds.extract_servings("[1인분]조선부추 50g"), ("1인분", "조선부추 50g"))

    def test_extracts_spaced_bracketed_servings(self):
        self.assertEqual(mfds.extract_servings("[ 2인분 ] 삼겹살(200g)"), ("2인분", "삼겹살(200g)"))

    def test_extracts_gijun_servings(self):
        self.assertEqual(mfds.extract_servings("2인분 기준\n• 오이(1개)"), ("2인분 기준", "• 오이(1개)"))

    def test_returns_none_when_no_servings_prefix(self):
        self.assertEqual(mfds.extract_servings("연어 60g, 어린잎 20g"), (None, "연어 60g, 어린잎 20g"))


class ParseIngredientsTest(unittest.TestCase):
    def parse(self, raw, name=""):
        return mfds.parse_ingredients(raw, name)

    def test_drops_leading_dish_title_and_keeps_section_label_as_group(self):
        r = self.parse(
            "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리)\n고명\n시금치 10g(3줄기)",
            "새우 두부 계란찜",
        )
        self.assertEqual(r.title_lines, ["새우두부계란찜"])
        self.assertEqual(
            [(i.group_name, i.name_raw, i.qty_raw) for i in r.items],
            [
                (None, "연두부", "75g(3/4모)"),
                (None, "칵테일새우", "20g(5마리)"),
                ("고명", "시금치", "10g(3줄기)"),
            ],
        )
        self.assertEqual(r.unparsed, [])

    def test_extracts_servings_and_bullet_colon_group(self):
        r = self.parse(
            "[1인분]조선부추 50g, 날콩가루 7g(1⅓작은술)\n·양념장 : 저염간장 3g(2/3작은술), 참깨 약간",
            "부추 콩가루 찜",
        )
        self.assertEqual(r.servings_raw, "1인분")
        self.assertEqual(
            [(i.group_name, i.name_raw, i.qty_raw) for i in r.items],
            [
                (None, "조선부추", "50g"),
                (None, "날콩가루", "7g(1⅓작은술)"),
                ("양념장", "저염간장", "3g(2/3작은술)"),
                ("양념장", "참깨", "약간"),
            ],
        )

    def test_reads_bullet_group_header_on_its_own_line(self):
        r = self.parse(
            "●방울토마토 소박이 : \n방울토마토 150g(5개), 양파 10g(3×1cm)\n●양념장 : \n고춧가루 4g(1작은술)",
            "방울토마토 소박이",
        )
        self.assertEqual(
            [(i.group_name, i.name_raw, i.qty_raw) for i in r.items],
            [
                ("방울토마토 소박이", "방울토마토", "150g(5개)"),
                ("방울토마토 소박이", "양파", "10g(3×1cm)"),
                ("양념장", "고춧가루", "4g(1작은술)"),
            ],
        )

    def test_handles_html_break_and_bracket_group(self):
        r = self.parse(
            "2인분 기준<br>\n•[간편식 재료] 알배추(40g), 우목심(50g)<br>\n\n•[추가 재료] 오징어(30g), 물(4컵=800g)",
            "토마토 해물누룽지탕",
        )
        self.assertEqual(r.servings_raw, "2인분 기준")
        self.assertEqual(
            [(i.group_name, i.name_raw, i.qty_raw) for i in r.items],
            [
                ("간편식 재료", "알배추", "40g"),
                ("간편식 재료", "우목심", "50g"),
                ("추가 재료", "오징어", "30g"),
                ("추가 재료", "물", "4컵=800g"),
            ],
        )

    def test_handles_inline_bracket_section_with_colon_subgroup(self):
        r = self.parse(
            "밥 150g, 소금 0.2g [소스소개] 저나트륨간장소스:간장 1g, 물 2g",
            "두부 채소 볶음밥",
        )
        self.assertEqual(
            [(i.group_name, i.name_raw, i.qty_raw) for i in r.items],
            [
                (None, "밥", "150g"),
                (None, "소금", "0.2g"),
                ("소스소개 > 저나트륨간장소스", "간장", "1g"),
                ("소스소개 > 저나트륨간장소스", "물", "2g"),
            ],
        )

    def test_keeps_unsplittable_fragment_instead_of_dropping_it(self):
        r = self.parse("새우 60g, 유산지", "종이에 싸서 구운 도미")
        self.assertEqual([(i.name_raw, i.qty_raw) for i in r.items], [("새우", "60g")])
        self.assertEqual(r.unparsed, ["유산지"])

    def test_returns_nothing_for_empty_source_string(self):
        r = self.parse("", "이름")
        self.assertEqual(r.items, [])
        self.assertEqual(r.unparsed, [])
        self.assertIsNone(r.servings_raw)


class StripStepNumberTest(unittest.TestCase):
    def test_removes_leading_step_number(self):
        self.assertEqual(mfds.strip_step_number("1. 손질된 새우를 데친다."), "손질된 새우를 데친다.")

    def test_removes_two_digit_step_number(self):
        self.assertEqual(mfds.strip_step_number("10. 마무리한다."), "마무리한다.")

    def test_leaves_description_without_number_untouched(self):
        self.assertEqual(mfds.strip_step_number("새우를 데친다."), "새우를 데친다.")

    def test_does_not_strip_number_that_is_part_of_the_sentence(self):
        self.assertEqual(mfds.strip_step_number("180도로 굽는다."), "180도로 굽는다.")



class StripInlineHeaderTest(unittest.TestCase):
    def test_strips_header_word_prefix(self):
        self.assertEqual(
            mfds.strip_inline_header("재료 굴(40g), 멸치(2g)"), ("재료", "굴(40g), 멸치(2g)")
        )

    def test_strips_seasoning_header_prefix(self):
        self.assertEqual(
            mfds.strip_inline_header("양념 다진 마늘(1g)"), ("양념", "다진 마늘(1g)")
        )

    def test_strips_parenthesised_header(self):
        self.assertEqual(
            mfds.strip_inline_header("(반죽재료) 강력분 300g"), ("반죽재료", "강력분 300g")
        )

    def test_strips_multispace_header(self):
        self.assertEqual(
            mfds.strip_inline_header("주재료   달걀흰자 180g"), ("주재료", "달걀흰자 180g")
        )

    def test_multispace_header_may_be_an_ingredient_name(self):
        self.assertEqual(
            mfds.strip_inline_header("크림치즈   우유 100g"), ("크림치즈", "우유 100g")
        )

    def test_keeps_ingredient_when_gap_precedes_quantity(self):
        """'저염간장  2g'은 헤더가 아니라 재료와 수량이 벌어진 것이다."""
        self.assertEqual(
            mfds.strip_inline_header("저염간장  2g, 물 100g"), (None, "저염간장  2g, 물 100g")
        )

    def test_keeps_ingredient_when_gap_precedes_quantity_word(self):
        self.assertEqual(mfds.strip_inline_header("간장  적당량"), (None, "간장  적당량"))

    def test_drops_inline_servings_after_header(self):
        self.assertEqual(
            mfds.strip_inline_header("재료 1인분 봄동(10g)"), ("재료", "봄동(10g)")
        )

    def test_returns_unchanged_when_no_header(self):
        self.assertEqual(mfds.strip_inline_header("연두부 75g"), (None, "연두부 75g"))

    def test_strips_recipe_specific_group_header(self):
        """레시피마다 이름이 다른 헤더는 접미사로 알아본다."""
        self.assertEqual(mfds.strip_inline_header("육수 무"), ("육수", "무"))
        self.assertEqual(mfds.strip_inline_header("톳 무침양념 설탕"), ("톳 무침양념", "설탕"))
        self.assertEqual(mfds.strip_inline_header("밥 밑간 참기름"), ("밥 밑간", "참기름"))

    def test_keeps_processing_prefix_as_part_of_the_name(self):
        """'다진'·'썬'은 그룹 헤더가 아니라 재료명의 일부다."""
        self.assertEqual(mfds.strip_inline_header("다진 마늘"), (None, "다진 마늘"))
        self.assertEqual(mfds.strip_inline_header("얇게 썬 쇠고기"), (None, "얇게 썬 쇠고기"))
        self.assertEqual(mfds.strip_inline_header("송송 썬 붉은 고추"), (None, "송송 썬 붉은 고추"))

    def test_keeps_sauce_when_it_is_the_last_token(self):
        """'머스터드 소스'는 재료명이다 — 접미사가 마지막 토큰이면 가르지 않는다."""
        self.assertEqual(mfds.strip_inline_header("머스터드 소스"), (None, "머스터드 소스"))


class TidyNameTest(unittest.TestCase):
    def test_removes_circled_marker(self):
        self.assertEqual(mfds.tidy_name("무가당 코코아가루①"), "무가당 코코아가루")

    def test_removes_trailing_each(self):
        self.assertEqual(mfds.tidy_name("청홍고추 각각"), "청홍고추")
        self.assertEqual(mfds.tidy_name("파프리카(빨강/노랑) 각"), "파프리카(빨강/노랑)")

    def test_keeps_ordinary_name(self):
        self.assertEqual(mfds.tidy_name("다진 마늘"), "다진 마늘")

    def test_keeps_ingredient_names_that_end_in_gak(self):
        """'팔각'·'노각'은 재료 이름이지 '각각' 수식어가 아니다."""
        self.assertEqual(mfds.tidy_name("팔각"), "팔각")
        self.assertEqual(mfds.tidy_name("노각"), "노각")


class NameIsBrokenTest(unittest.TestCase):
    def test_detects_unclosed_paren(self):
        self.assertTrue(mfds.name_is_broken("바지락(모시조개"))

    def test_detects_stray_bracket(self):
        self.assertTrue(mfds.name_is_broken("후추적당량[양송이 속양파다진것"))

    def test_accepts_balanced_paren(self):
        self.assertFalse(mfds.name_is_broken("황태(채)"))


class CleanLabelTest(unittest.TestCase):
    def test_strips_leading_hyphen(self):
        self.assertEqual(mfds._clean_label("- 양념장"), "양념장")

    def test_strips_bullet(self):
        self.assertEqual(mfds._clean_label("● 소스"), "소스")

if __name__ == "__main__":
    unittest.main()
