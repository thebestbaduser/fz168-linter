import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter import Context, check_text  # noqa: E402


class CheckerTest(unittest.TestCase):
    def test_dictionary_words_are_not_flagged(self):
        report = check_text(
            "Комфорт, дизайн, фасад и терраса.",
            Context(legal_surface="public_information"),
        )
        self.assertFalse(
            [item for item in report.findings if item.code == "borrowed-word"]
        )

    def test_borrowed_word_needs_review_with_replacements(self):
        report = check_text(
            "В просторном лобби.",
            Context(legal_surface="public_information"),
        )
        borrowed = [item for item in report.findings if item.code == "borrowed-word"]
        self.assertTrue(borrowed)
        self.assertEqual(borrowed[0].status.value, "NEEDS_REVIEW")
        self.assertIn("вестибюль", borrowed[0].replacements)

    def test_unknown_context_gives_needs_review(self):
        report = check_text("Prime Park", Context())
        latin = [item for item in report.findings if item.code == "latin-unknown-context"]
        self.assertTrue(latin)
        self.assertEqual(latin[0].status.value, "NEEDS_REVIEW")

    def test_public_information_latin_without_russian_is_violation(self):
        report = check_text("Кнопка Sale", Context(legal_surface="public_information"))
        self.assertTrue(report.has_likely_violation)
        codes = [item.code for item in report.findings]
        self.assertIn("public-info-not-russian", codes)

    def test_russian_duplicate_is_no_issue_found(self):
        report = check_text(
            "Распродажа / Sale",
            Context(legal_surface="public_information"),
        )
        sale = [item for item in report.findings if item.text.lower() == "sale"]
        self.assertTrue(sale)
        self.assertEqual(sale[0].status.value, "NO_ISSUE_FOUND")
        self.assertFalse(report.has_likely_violation)

    def test_internal_surface_is_not_applicable(self):
        report = check_text("Sale", Context(legal_surface="internal"))
        self.assertEqual(report.findings[0].status.value, "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()
