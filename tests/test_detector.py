import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter import Context, check_text  # noqa: E402
from fz168_linter.detector import mask_for  # noqa: E402


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
        for text in ("Слово Пaрк", "СитиPаrk", "ЖК Pаrk42", "ЖК Пaрк2"):
            with self.subTest(text=text):
                report = check_text(text, Context())
                codes = [item.code for item in report.findings]
                self.assertNotIn("latin-unknown-context", codes)
                self.assertEqual(codes, ["MIXED_SCRIPT_SUSPECTED"])

    def test_visible_html_attributes_are_checked_with_original_offsets(self):
        cases = (
            '<input placeholder="Sale">',
            "<button TITLE='Sale'>Купить</button>",
            '<img alt="Sale" src="sale.jpg">',
            '<button aria-label="Sale">Купить</button>',
            '<div aria-description="Sale"></div>',
            '<input placeholder=Sale>',
            '<input type="submit" value="Sale">',
            '<input value="Sale" type="button">',
            '<input type="reset" value="Sale">',
            '<input type="text" value="Sale">',
            '<input value="Sale">',
        )
        for text in cases:
            with self.subTest(text=text):
                report = check_text(text, Context(input_format="html"))
                self.assertEqual([item.text for item in report.findings], ["Sale"])
                item = report.findings[0]
                self.assertEqual(text[item.start:item.end], "Sale")
                self.assertEqual(item.column, text.index("Sale") + 1)

    def test_nonvisible_values_and_technical_attributes_are_ignored(self):
        text = (
            '<input type="hidden" value="Sale"><input type="password" value="Sale">'
            '<input type="radio" value="Sale"><option value="Sale">Купить</option>'
            '<div data-label="Sale" onclick="buy()" class="Sale" id="Sale"></div>'
        )
        self.assertEqual(check_text(text, Context(input_format="html")).findings, [])

    def test_static_jsx_text_and_attributes_are_checked(self):
        cases = (
            '<button>{"Sale"}</button>',
            "<button>{ 'Sale' }</button>",
            '<button>{`Sale`}</button>',
            '<input placeholder={"Sale"} />',
            '<button aria-label={\'Sale\'} />',
            '<input type={"submit"} value={"Sale"} />',
            '<button>{"Sale }"}</button>',
        )
        for text in cases:
            with self.subTest(text=text):
                report = check_text(text, Context(input_format="jsx"))
                self.assertEqual([item.text for item in report.findings], ["Sale"])
                item = report.findings[0]
                self.assertEqual(text[item.start:item.end], "Sale")

    def test_jsx_technical_expressions_do_not_leak_literals_or_braces(self):
        text = (
            '<button onClick={() => { run("Sale }"); }}>Купить</button>'
            '<div>{/* "Sale }" */}{lookup({ key: "Sale }" })}'
            '{`Sale ${value}`}</div><input placeholder={label} />'
        )
        self.assertEqual(check_text(text, Context(input_format="jsx")).findings, [])

    def test_jsx_component_code_outside_markup_is_ignored(self):
        text = (
            'import { useState } from "react";\n'
            'const sale = "Sale";\n'
            "export default function Block() {\n"
            '  return <button className="sale">Купить</button>;\n'
            "}\n"
        )
        report = check_text(
            text, Context(legal_surface="public_information", input_format="jsx")
        )
        self.assertEqual(report.findings, [])

    def test_jsx_visible_text_inside_component_is_still_checked(self):
        text = (
            "export default function Block() {\n"
            '  return <button>{"Sale"}</button>;\n'
            "}\n"
        )
        report = check_text(
            text, Context(legal_surface="public_information", input_format="jsx")
        )
        self.assertEqual([item.text for item in report.findings], ["Sale"])

    def test_urls_and_email_are_ignored_in_every_input_format(self):
        visible = "https://example.com/sale www.example.com/buy sale@example.com Sale"
        for input_format in ("text", "markdown", "html", "jsx"):
            with self.subTest(input_format=input_format):
                text = visible if input_format in ("text", "markdown") else f"<p>{visible}</p>"
                report = check_text(text, Context(input_format=input_format))
                self.assertEqual([item.text for item in report.findings], ["Sale"])
                self.assertEqual(report.findings[0].start, text.rindex("Sale"))

    def test_script_and_style_tags_support_whitespace_and_exact_closing_names(self):
        text = (
            '<SCRIPT\n type="text/javascript">const sale = "</scripture>";</SCRIPT >'
            '<style\tmedia="screen">.sale { display: block; }</style>Купить'
        )
        self.assertEqual(check_text(text, Context(input_format="html")).findings, [])

    def test_html_entities_do_not_become_latin_words(self):
        text = '<p title="&amp; Sale">&nbsp;&copy;&#169;&#xA9; Купить</p>'
        report = check_text(text, Context(input_format="html"))
        self.assertEqual([item.text for item in report.findings], ["Sale"])

    def test_masking_preserves_length_newlines_and_original_positions(self):
        cases = {
            "text": "Адрес\r\nhttps://example.com/sale\nSale",
            "markdown": "```\r\nSale\r\n```\n[Купить](https://sale.com) Sale",
            "html": '<!--Sale\n--><input\nplaceholder="Sale">&nbsp;\n',
            "jsx": '<button\n onClick={() => { run("Sale }"); }}>{"Sale"}</button>\n',
        }
        for input_format, text in cases.items():
            with self.subTest(input_format=input_format):
                masked = mask_for(text, input_format)
                self.assertEqual(len(masked), len(text))
                self.assertEqual(
                    [(i, char) for i, char in enumerate(masked) if char in "\r\n"],
                    [(i, char) for i, char in enumerate(text) if char in "\r\n"],
                )
                report = check_text(text, Context(input_format=input_format))
                self.assertEqual([item.text for item in report.findings], ["Sale"])
                item = report.findings[0]
                self.assertEqual(text[item.start:item.end], "Sale")
                prefix = text[:item.start]
                self.assertEqual(item.line, prefix.count("\n") + 1)
                self.assertEqual(item.column, len(prefix.rsplit("\n", 1)[-1]) + 1)


if __name__ == "__main__":
    unittest.main()
