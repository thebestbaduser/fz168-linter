import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter import Context, check_text  # noqa: E402


class HomoglyphTest(unittest.TestCase):
    def test_mixed_script_in_complex_name_is_violation(self):
        report = check_text(
            "ЖК Сити Пaрк",
            Context(object_type="residential_complex", ddu_fundraising_ad=True),
        )
        mixed = [item for item in report.findings if item.code == "MIXED_SCRIPT_SUSPECTED"]
        self.assertTrue(mixed)
        self.assertEqual(mixed[0].status.value, "LIKELY_VIOLATION")
        char = mixed[0].details["chars"][0]
        self.assertEqual(char["codepoint"], "U+0061")
        self.assertEqual(char["expected_codepoint"], "U+0430")

    def test_pure_cyrillic_has_no_homoglyph(self):
        report = check_text(
            "ЖК Сити Парк",
            Context(object_type="residential_complex", ddu_fundraising_ad=True),
        )
        self.assertFalse(
            [item for item in report.findings if item.code == "MIXED_SCRIPT_SUSPECTED"]
        )

    def test_latin_word_is_not_homoglyph(self):
        report = check_text("Реклама Prime Park", Context())
        self.assertFalse(
            [item for item in report.findings if item.code == "MIXED_SCRIPT_SUSPECTED"]
        )


if __name__ == "__main__":
    unittest.main()
