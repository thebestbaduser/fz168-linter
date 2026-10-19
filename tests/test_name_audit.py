import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter import Context, check_text  # noqa: E402


class NameAuditTest(unittest.TestCase):
    def test_alias_of_official_name_needs_review(self):
        report = check_text(
            "Test Object",
            Context(
                object_type="residential_complex",
                ddu_fundraising_ad=False,
                official_name="Тестовый Объект",
                aliases=("Test Object",),
                name_source="ЕИСЖС",
            ),
        )
        findings = [item for item in report.findings if item.code == "name-alias-mismatch"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status.value, "NEEDS_REVIEW")
        self.assertEqual(findings[0].details["official_name"], "Тестовый Объект")
        self.assertFalse(
            [item for item in report.findings if item.code == "latin-unknown-context"]
        )

    def test_alias_in_developer_ddu_ad_is_violation(self):
        report = check_text(
            "Test Object",
            Context(
                legal_surface="advertisement",
                object_type="residential_complex",
                ddu_fundraising_ad=True,
                entity_roles=("developer",),
                official_name="Тестовый Объект",
                aliases=("Test Object",),
            ),
        )
        findings = [item for item in report.findings if item.code == "name-alias-latin"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status.value, "LIKELY_VIOLATION")

    def test_aggregator_ddu_card_is_not_developer_violation(self):
        report = check_text(
            "Test Object",
            Context(
                legal_surface="advertisement",
                object_type="residential_complex",
                ddu_fundraising_ad=True,
                entity_roles=("aggregator",),
                official_name="Тестовый Объект",
                aliases=("Test Object",),
            ),
        )
        self.assertFalse(report.has_likely_violation)
        self.assertTrue(
            [item for item in report.findings if item.code == "name-alias-mismatch"]
        )

    def test_official_name_present_is_reported_in_audit_mode(self):
        report = check_text(
            "Тестовый Объект",
            Context(
                object_type="residential_complex",
                ddu_fundraising_ad=False,
                official_name="Тестовый Объект",
            ),
            name_audit=True,
        )
        self.assertFalse(report.has_likely_violation)
        self.assertTrue(
            [item for item in report.findings if item.code == "name-official-present"]
        )

    def test_missing_official_name_is_review(self):
        report = check_text(
            "Prime Park",
            Context(
                object_type="residential_complex",
                ddu_fundraising_ad=False,
                official_name="Тестовый Объект",
            ),
            name_audit=True,
        )
        self.assertTrue([item for item in report.findings if item.code == "name-not-found"])

    def test_alias_equal_to_official_is_ignored(self):
        report = check_text(
            "Тестовый Объект",
            Context(
                object_type="residential_complex",
                ddu_fundraising_ad=False,
                official_name="Тестовый Объект",
                aliases=("тестовый объект",),
            ),
        )
        self.assertFalse(
            [item for item in report.findings if item.code.startswith("name-alias")]
        )

    def test_latin_official_name_in_developer_ad_is_violation(self):
        report = check_text(
            "Test Object",
            Context(
                legal_surface="advertisement",
                object_type="residential_complex",
                ddu_fundraising_ad=True,
                entity_roles=("developer",),
                official_name="Test Object",
            ),
        )
        findings = [item for item in report.findings if item.code == "name-official-latin"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status.value, "LIKELY_VIOLATION")

    def test_context_serializes_name_fields(self):
        context = Context(
            official_name="Тестовый Объект",
            aliases=("Test Object",),
            name_source="ЕИСЖС",
        )
        data = context.to_dict()
        self.assertEqual(data["official_name"], "Тестовый Объект")
        self.assertEqual(data["aliases"], ["Test Object"])
        self.assertEqual(Context.from_dict(data).name_source, "ЕИСЖС")


if __name__ == "__main__":
    unittest.main()
