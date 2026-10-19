import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fz168_linter.cli import main  # noqa: E402


class CLITest(unittest.TestCase):
    def run_cli(self, argv, stdin=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with patch("sys.stdin", stdin or io.StringIO()):
                try:
                    exit_code = main(argv)
                except SystemExit as exc:
                    exit_code = exc.code
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_file_format_and_json_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.html"
            path.write_text("<button>Sale</button>", encoding="utf-8")
            code, stdout, stderr = self.run_cli(
                ["check", str(path), "--surface", "public_information", "--format", "json"]
            )
        report = json.loads(stdout)
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(report["context"]["input_format"], "html")
        self.assertTrue(report["has_likely_violation"])

    def test_fail_on_review_and_never(self):
        for policy, expected in (("violation", 0), ("review", 1), ("never", 0)):
            with self.subTest(policy=policy):
                code, _, stderr = self.run_cli(
                    ["check", "-", "--fail-on", policy], io.StringIO("Sale")
                )
                self.assertEqual(code, expected)
                self.assertEqual(stderr, "")

    def test_missing_file_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            code, stdout, stderr = self.run_cli(
                ["check", str(Path(directory) / "missing.txt")]
            )
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("missing.txt", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_invalid_utf8_file_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.txt"
            path.write_bytes(b"\xff")
            code, stdout, stderr = self.run_cli(["check", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("UTF-8", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_stdin_is_decoded_as_utf8(self):
        for data, expected in (("Распродажа".encode("utf-8"), 0), (b"\xff", 2)):
            with self.subTest(data=data):
                stdin = io.TextIOWrapper(io.BytesIO(data), encoding="ascii")
                code, _, stderr = self.run_cli(["check", "-"], stdin)
                self.assertEqual(code, expected)
                self.assertNotIn("Traceback", stderr)

    def test_invalid_commission_date_is_a_usage_error(self):
        for date in ("not-a-date", "2026-02-30", "20260301"):
            with self.subTest(date=date):
                code, stdout, stderr = self.run_cli(
                    ["check", "-", "--commissioned", date]
                )
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main()
