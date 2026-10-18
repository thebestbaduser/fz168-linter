"""Приёмочные сценарии: то, что нельзя регрессировать."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter import Context, check_text  # noqa: E402


class AcceptanceTest(unittest.TestCase):
    def test_sale_without_russian_is_violation(self):
        report = check_text("Купить / Sale", Context(legal_surface="public_information"))
        self.assertTrue(report.has_likely_violation)

    def test_equal_duplicate_has_no_violation(self):
        report = check_text(
            "Распродажа / Sale",
            Context(legal_surface="public_information"),
        )
        self.assertFalse(report.has_likely_violation)

    def test_registered_trademark_on_sign_is_exception(self):
        report = check_text(
            "Вывеска YourBrand",
            Context(legal_surface="public_information"),
            extra_trademarks=["YourBrand"],
        )
        self.assertFalse(report.has_likely_violation)
        self.assertTrue(
            [item for item in report.findings if item.code == "trademark-exception"]
        )

    def test_trademark_does_not_save_complex_name_in_ddu_ad(self):
        report = check_text(
            "ЖК YourBrand",
            Context(
                legal_surface="advertisement",
                object_type="residential_complex",
                ddu_fundraising_ad=True,
            ),
            extra_trademarks=["YourBrand"],
        )
        self.assertTrue(report.has_likely_violation)
        self.assertTrue(
            [item for item in report.findings if item.code == "naming-214fz-trademark"]
        )

    def test_commissioned_before_law_is_not_applicable(self):
        report = check_text(
            "ЖК Prime Park",
            Context(
                object_type="residential_complex",
                ddu_fundraising_ad=True,
                commissioned_before="2025-01-01",
            ),
        )
        self.assertFalse(report.has_likely_violation)
        self.assertTrue(
            [item for item in report.findings if item.code == "naming-214fz-exemption"]
        )

    def test_ambiguous_commission_date_needs_review(self):
        report = check_text(
            "ЖК Prime Park",
            Context(
                object_type="residential_complex",
                ddu_fundraising_ad=True,
                commissioned_before="2025-12-01",
            ),
        )
        self.assertFalse(report.has_likely_violation)
        self.assertTrue([item for item in report.findings if item.status.value == "NEEDS_REVIEW"])

    def test_homoglyph_in_complex_name_is_violation(self):
        report = check_text(
            "ЖК Сити Пaрк",
            Context(object_type="residential_complex", ddu_fundraising_ad=True),
        )
        self.assertTrue(report.has_likely_violation)

    def test_html_technical_latin_is_silent(self):
        html = '<button class="btn sale" data-id="42" aria-label="sale">Купить</button>'
        report = check_text(
            html,
            Context(legal_surface="public_information", input_format="html"),
        )
        self.assertEqual(report.findings, [])

    def test_aggregator_card_is_not_developer_ad(self):
        report = check_text(
            "ЖК Prime Park",
            Context(
                legal_surface="public_information",
                object_type="residential_complex",
                ddu_fundraising_ad=False,
            ),
        )
        self.assertFalse(
            [item for item in report.findings if item.code.startswith("naming-214fz")]
        )

    def test_word_outside_local_dictionary_is_review_not_violation(self):
        report = check_text("В лобби", Context(legal_surface="public_information"))
        self.assertFalse(report.has_likely_violation)
        self.assertTrue(
            [item for item in report.findings if item.status.value == "NEEDS_REVIEW"]
        )

    def test_non_name_latin_in_ddu_ad_is_not_214_violation(self):
        report = check_text(
            "В ЖК Prime Park отделка White Box.",
            Context(
                legal_surface="advertisement",
                object_type="residential_complex",
                ddu_fundraising_ad=True,
            ),
        )
        naming = [item for item in report.findings if item.code == "naming-214fz"]
        self.assertEqual({item.text for item in naming}, {"Prime", "Park"})

    def test_bare_name_is_checked_as_name(self):
        report = check_text(
            "Prime Park",
            Context(
                legal_surface="advertisement",
                object_type="residential_complex",
                ddu_fundraising_ad=True,
            ),
        )
        self.assertTrue(report.has_likely_violation)


if __name__ == "__main__":
    unittest.main()
