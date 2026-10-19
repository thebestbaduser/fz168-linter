import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter.django_validators import FZ168Validator  # noqa: E402

try:
    from django.core.exceptions import ValidationError
    from django.db.migrations.writer import MigrationWriter
except ImportError:
    ValidationError = None
    MigrationWriter = None


class ValidatorConfigurationTest(unittest.TestCase):
    def test_equality_uses_normalized_context(self):
        self.assertEqual(FZ168Validator(), FZ168Validator(legal_surface="unknown"))
        self.assertEqual(
            FZ168Validator(entity_roles=["seller"]),
            FZ168Validator(entity_roles=("seller",)),
        )
        self.assertNotEqual(FZ168Validator(), FZ168Validator(legal_surface="public_information"))
        self.assertNotEqual(FZ168Validator(), object())

    def test_invalid_context_fails_during_configuration(self):
        with self.assertRaises(ValueError):
            FZ168Validator(legal_surface="publik_information")


@unittest.skipIf(ValidationError is None, "Django extra is not installed")
class DjangoValidatorTest(unittest.TestCase):
    def test_validation_blocks_only_likely_violation(self):
        validator = FZ168Validator(legal_surface="public_information")
        with self.assertRaises(ValidationError) as raised:
            validator("Sale")
        error = raised.exception
        self.assertEqual(error.code, "fz168")
        self.assertIn("Sale", error.params["details"])
        self.assertTrue(error.params["basis"])
        validator("Распродажа")
        FZ168Validator()("Sale")

    def test_migration_serialization_round_trip(self):
        validator = FZ168Validator(
            legal_surface="public_information", entity_roles=["seller"]
        )
        serialized, imports = MigrationWriter.serialize(validator)
        namespace = {}
        for statement in imports:
            exec(statement, namespace)
        restored = eval(serialized, namespace)
        self.assertEqual(restored, validator)
        self.assertEqual(restored.deconstruct(), validator.deconstruct())


if __name__ == "__main__":
    unittest.main()
