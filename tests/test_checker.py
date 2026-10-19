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

    def test_unrelated_or_incomplete_russian_text_is_not_a_duplicate(self):
        for text in (
            "Редакция. Sale",
            "Распродажа завершилась. Sale",
            "Распродажа\nДругой раздел\nSale",
            "Обратный путь / Callback",
            "Горячее блюдо / Hot",
        ):
            with self.subTest(text=text):
                report = check_text(text, Context(legal_surface="public_information"))
                self.assertTrue(report.has_likely_violation)

    def test_complete_adjacent_duplicate_in_either_order(self):
        for text in ("Распродажа / Sale", "Sale (Распродажа)", "Обратный звонок — Callback"):
            with self.subTest(text=text):
                report = check_text(text, Context(legal_surface="public_information"))
                self.assertFalse(report.has_likely_violation)

    def test_duplicate_cannot_come_from_another_html_block_or_attribute(self):
        for text in (
            "<button>Sale</button><p>Распродажа</p>",
            '<button aria-label="Sale">Распродажа</button>',
            "<div>Обратный</div><div>звонок / Callback</div>",
        ):
            with self.subTest(text=text):
                report = check_text(
                    text, Context(legal_surface="public_information", input_format="html")
                )
                self.assertTrue(report.has_likely_violation)

    def test_inline_html_can_contain_duplicate(self):
        report = check_text(
            "<p><span>Sale</span> / <strong>Распродажа</strong></p>",
            Context(legal_surface="public_information", input_format="html"),
        )
        self.assertFalse(report.has_likely_violation)

    def test_multiword_rules_keep_replacement_and_original_offsets(self):
        for term, rule_id in (("White Box", "re-whitebox"), ("шелл энд кор", "re-shell-core")):
            text = "Отделка: " + term
            with self.subTest(text=text):
                report = check_text(text, Context(legal_surface="public_information"))
                matched = [item for item in report.findings if item.rule_id == rule_id]
                self.assertEqual(len(matched), 1)
                self.assertEqual(matched[0].text, term)
                self.assertEqual(text[matched[0].start : matched[0].end], term)
                self.assertTrue(matched[0].replacements)

    def test_multiword_rule_cannot_join_different_controls(self):
        for text in (
            '<input placeholder="White" title="Box">',
            "<button>White</button><button>Box</button>",
        ):
            with self.subTest(text=text):
                report = check_text(
                    text, Context(legal_surface="public_information", input_format="html")
                )
                self.assertEqual([item.text for item in report.findings], ["White", "Box"])
                self.assertTrue(all(item.rule_id is None for item in report.findings))

    def test_trademark_requires_explicit_registered_status(self):
        for trademark_status in ("unknown", "application", "none", "registered"):
            with self.subTest(status=trademark_status):
                report = check_text(
                    "Your Brand",
                    Context(legal_surface="public_information", trademark_status=trademark_status),
                    extra_trademarks=["Your Brand"],
                )
                self.assertEqual(len(report.findings), 1)
                expected = {
                    "registered": "NO_ISSUE_FOUND", "unknown": "NEEDS_REVIEW",
                    "application": "LIKELY_VIOLATION", "none": "LIKELY_VIOLATION",
                }[trademark_status]
                self.assertEqual(report.findings[0].status.value, expected)

    def test_date_exemption_applies_to_mixed_and_latin_names(self):
        for name in ("Пaрк", "Park"):
            with self.subTest(name=name):
                report = check_text(
                    "ЖК «" + name + "». Квартиры.",
                    Context(
                        object_type="residential_complex",
                        ddu_fundraising_ad=True,
                        commissioned_before="2025-01-01",
                    ),
                )
                self.assertFalse(report.has_likely_violation)
                self.assertEqual(report.findings[0].status.value, "NOT_APPLICABLE")

    def test_building_name_and_technical_name_are_checked(self):
        for name in ("Park", "Wi-Fi", "QR-код"):
            with self.subTest(name=name):
                report = check_text(
                    "Жилой дом «" + name + "».",
                    Context(object_type="building", ddu_fundraising_ad=True),
                )
                self.assertTrue(report.has_likely_violation)

    def test_context_rejects_malformed_or_misspelled_values(self):
        for values in (
            {"commissioned_before": "2025-02-30"},
            {"commissioned_before": "20250101"},
            {"commissioned_before": ""},
            {"ddu_fundraising_ad": "false"},
            {"entity_roles": "developer"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Context.from_dict(values)
        with self.assertRaises(TypeError):
            Context.from_dict({"legal_surfac": "public_information"})

    def test_context_mutation_is_revalidated(self):
        context = Context()
        context.commissioned_before = "not-a-date"
        with self.assertRaises(ValueError):
            check_text("Park", context)
        context = Context()
        context.entity_roles = "developer"
        with self.assertRaises(ValueError):
            check_text("Park", context)

    def test_name_heuristic_does_not_capture_russian_description(self):
        for text in (
            "ЖК Парк рядом с Central Park",
            "Новая отделка White Box",
            "Слоган «White Box» в рекламе.",
        ):
            with self.subTest(text=text):
                report = check_text(
                    text,
                    Context(
                        legal_surface="advertisement", object_type="residential_complex",
                        ddu_fundraising_ad=True,
                    ),
                )
                self.assertFalse(report.has_likely_violation)

    def test_exemption_cutoff_is_strictly_before_the_date(self):
        for date, status in (
            (None, "LIKELY_VIOLATION"),
            ("2025-06-23", "NOT_APPLICABLE"),
            ("2025-06-24", "NEEDS_REVIEW"),
            ("2026-02-28", "NEEDS_REVIEW"),
            ("2026-03-01", "LIKELY_VIOLATION"),
        ):
            for name in ("Park", "Пaрк"):
                with self.subTest(date=date, name=name):
                    report = check_text(
                        name,
                        Context(
                            object_type="building", ddu_fundraising_ad=True,
                            commissioned_before=date,
                        ),
                    )
                    self.assertEqual(report.findings[0].status.value, status)
                    if date is None:
                        self.assertEqual(report.findings[0].confidence, "medium")
                        self.assertIn("Дата ввода не задана", report.findings[0].message)

    def test_custom_lists_reject_a_string_or_empty_term(self):
        for name in ("extra_whitelist", "extra_trademarks"):
            with self.subTest(name=name):
                with self.assertRaises(TypeError):
                    check_text("Sale", **{name: "Sale"})
                with self.assertRaises(ValueError):
                    check_text("Sale", **{name: [""]})

    def test_dictionary_findings_preserve_meaning_check(self):
        report = check_text("Лобби", Context(legal_surface="public_information"))
        item = report.findings[0]
        self.assertEqual(item.status.value, "NEEDS_REVIEW")
        self.assertIn("политическое", item.message)
        self.assertIn("1031", item.details["dictionary_check"])
        self.assertTrue(item.details["source"].startswith("https://ruslang.ru/"))


if __name__ == "__main__":
    unittest.main()
