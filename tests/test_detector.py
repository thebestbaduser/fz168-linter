import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter import Context, check_text  # noqa: E402


class DetectorTest(unittest.TestCase):
    def test_html_attributes_and_urls_are_ignored(self):
        html = (
            '<div class="sale hot"><a href="https://example.com/callback">Купить</a>'
            "<script>var sale = 1;</script></div>"
        )
        report = check_text(
            html,
            Context(legal_surface="public_information", input_format="html"),
        )
        self.assertEqual(report.findings, [])

    def test_markdown_code_and_links_are_ignored(self):
        text = "Пример:\n```\nconst sale = 1;\n```\nСсылка: https://example.com/sale\n"
        report = check_text(
            text,
            Context(legal_surface="public_information", input_format="markdown"),
        )
        self.assertEqual(report.findings, [])

    def test_offsets_point_to_original_string(self):
        text = "Купите квартиру, Sale!"
        report = check_text(text, Context(legal_surface="public_information"))
        sales = [item for item in report.findings if item.text.lower() == "sale"]
        self.assertTrue(sales)
        item = sales[0]
        self.assertEqual(text[item.start : item.end], "Sale")
        self.assertEqual((item.line, item.column), (1, text.index("Sale") + 1))

    def test_latin_next_to_cyrillic_is_not_a_separate_token(self):
        report = check_text("Слово Пaрк", Context())
        codes = [item.code for item in report.findings]
        self.assertNotIn("latin-unknown-context", codes)


if __name__ == "__main__":
    unittest.main()
