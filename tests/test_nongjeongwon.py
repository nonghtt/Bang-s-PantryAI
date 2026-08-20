# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from stage1 import nongjeongwon as nj


class SplitGroupHeaderTest(unittest.TestCase):
    def test_extracts_bracket_header_as_group_name(self):
        self.assertEqual(nj.split_group_header("[쇠고기양념] 다진파"), ("쇠고기양념", "다진파"))

    def test_keeps_spaces_inside_header(self):
        self.assertEqual(nj.split_group_header("[절임용 소금물] 소금"), ("절임용 소금물", "소금"))

    def test_returns_no_group_when_no_bracket(self):
        self.assertEqual(nj.split_group_header("다진 마늘"), (None, "다진 마늘"))


class FixTypoTest(unittest.TestCase):
    def test_corrects_known_typo(self):
        self.assertEqual(nj.fix_typo("돼기고기"), ("돼지고기", "돼기고기"))

    def test_reports_no_correction_for_clean_name(self):
        self.assertEqual(nj.fix_typo("돼지고기"), ("돼지고기", None))

    def test_does_not_touch_unlisted_misspelling(self):
        self.assertEqual(nj.fix_typo("느타리버섯"), ("느타리버섯", None))


class SplitMultiIngredientTest(unittest.TestCase):
    def test_splits_slash_separated_row(self):
        self.assertEqual(
            nj.split_multi_ingredient("식용유/소금/참기름/잣가루"),
            ["식용유", "소금", "참기름", "잣가루"],
        )

    def test_splits_middle_dot_separated_row(self):
        self.assertEqual(
            nj.split_multi_ingredient("빨강파프리카·노랑 파프리카·청피망"),
            ["빨강파프리카", "노랑 파프리카", "청피망"],
        )

    def test_splits_comma_separated_row(self):
        self.assertEqual(nj.split_multi_ingredient("후추, 식용유"), ["후추", "식용유"])

    def test_drops_trailing_gakgak_marker(self):
        self.assertEqual(nj.split_multi_ingredient("홍피망, 청피망 각각"), ["홍피망", "청피망"])

    def test_distributes_shared_head_noun(self):
        self.assertEqual(nj.split_multi_ingredient("노랑/빨강 파프리카"), ["노랑 파프리카", "빨강 파프리카"])

    def test_returns_single_item_for_plain_name(self):
        self.assertEqual(nj.split_multi_ingredient("다진 마늘"), ["다진 마늘"])

    def test_leaves_unlisted_delimiter_row_intact(self):
        self.assertEqual(nj.split_multi_ingredient("깨소금·참깨·통깨·들깨"), ["깨소금·참깨·통깨·들깨"])


class TrimNameTest(unittest.TestCase):
    def test_strips_outer_whitespace(self):
        self.assertEqual(nj.trim_name("달걀 "), "달걀")

    def test_preserves_inner_whitespace(self):
        self.assertEqual(nj.trim_name(" 다진 마늘 "), "다진 마늘")



class ExpandIngredientRowTest(unittest.TestCase):
    def row(self, name, qty="1작은술", role="양념"):
        return {"IRDNT_NM": name, "IRDNT_CPCTY": qty, "IRDNT_TY_NM": role}

    def test_returns_one_row_for_plain_ingredient(self):
        self.assertEqual(
            nj.expand_ingredient_row(self.row("다진 마늘", "1큰술", "부재료")),
            [{"group_name": None, "name_raw": "다진 마늘", "qty_raw": "1큰술",
              "role_raw": "부재료", "typo_from": None}],
        )

    def test_lifts_bracket_header_into_group_name(self):
        self.assertEqual(
            nj.expand_ingredient_row(self.row("[쇠고기양념] 다진파")),
            [{"group_name": "쇠고기양념", "name_raw": "다진파", "qty_raw": "1작은술",
              "role_raw": "양념", "typo_from": None}],
        )

    def test_duplicates_quantity_across_split_ingredients(self):
        self.assertEqual(
            nj.expand_ingredient_row(self.row("소금, 후추", "약간")),
            [
                {"group_name": None, "name_raw": "소금", "qty_raw": "약간",
                 "role_raw": "양념", "typo_from": None},
                {"group_name": None, "name_raw": "후추", "qty_raw": "약간",
                 "role_raw": "양념", "typo_from": None},
            ],
        )

    def test_records_which_typo_was_corrected(self):
        rows = nj.expand_ingredient_row(self.row("돼기고기", "100g", "주재료"))
        self.assertEqual(rows[0]["name_raw"], "돼지고기")
        self.assertEqual(rows[0]["typo_from"], "돼기고기")

    def test_trims_trailing_space_from_source_name(self):
        self.assertEqual(nj.expand_ingredient_row(self.row("달걀 "))[0]["name_raw"], "달걀")

    def test_normalises_empty_quantity_to_none(self):
        self.assertIsNone(nj.expand_ingredient_row(self.row("소금", ""))[0]["qty_raw"])


if __name__ == "__main__":
    unittest.main()
