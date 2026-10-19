"""Командная строка fz168."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .checker import check_text
from .models import Context, Status

SUFFIX_FORMATS = {
    ".html": "html",
    ".htm": "html",
    ".jsx": "jsx",
    ".tsx": "jsx",
    ".md": "markdown",
    ".markdown": "markdown",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fz168",
        description=(
            "Предварительная проверка текстов на языковые риски по 168-ФЗ. "
            "Не является юридическим заключением."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="проверить файл или stdin")
    check.add_argument("path", help="путь к файлу или - для stdin")
    check.add_argument("--input", choices=("text", "html", "jsx", "markdown"), default=None)
    check.add_argument(
        "--surface",
        choices=("advertisement", "public_information", "internal", "unknown"),
        default="unknown",
    )
    check.add_argument(
        "--object-type",
        choices=("residential_complex", "building", "other", "unknown"),
        default="unknown",
    )
    check.add_argument("--ddu-ad", action="store_true", help="реклама привлечения средств дольщиков")
    check.add_argument("--commissioned", default=None, help="дата ввода объекта, YYYY-MM-DD")
    check.add_argument(
        "--trademark",
        choices=("registered", "application", "none", "unknown"),
        default="unknown",
    )
    check.add_argument(
        "--trademark-word",
        action="append",
        default=[],
        help="слово-товарный знак (можно несколько раз)",
    )
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument(
        "--fail-on",
        choices=("violation", "review", "never"),
        default="violation",
        help="код выхода 1: только при LIKELY_VIOLATION, при любом NEEDS_REVIEW или никогда",
    )
    return parser


def _print_report(report) -> None:
    if not report.findings:
        print("Находок нет.")
        return
    for finding in report.findings:
        print(
            f"{finding.status.value} {finding.code} "
            f"{finding.line}:{finding.column} \"{finding.text}\""
        )
        print(f"  {finding.message}")
        if finding.replacements:
            print("  Варианты: " + ", ".join(finding.replacements))
        if finding.legal_basis:
            print("  Основание: " + "; ".join(finding.legal_basis))
        if finding.confidence:
            print(f"  Уверенность: {finding.confidence}")
    counts = {status.value: len(report.by_status(status)) for status in Status}
    print("\nИтого: " + ", ".join(f"{name}={value}" for name, value in counts.items()))


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:  # корректный UTF-8 при перенаправлении вывода в файл
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    suffix = "" if args.path == "-" else Path(args.path).suffix.lower()
    input_format = args.input or SUFFIX_FORMATS.get(suffix, "text")
    try:
        context = Context(
            legal_surface=args.surface,
            object_type=args.object_type,
            ddu_fundraising_ad=True if args.ddu_ad else None,
            commissioned_before=args.commissioned,
            trademark_status=args.trademark,
            input_format=input_format,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        if args.path == "-":
            if hasattr(sys.stdin, "buffer"):
                text = sys.stdin.buffer.read().decode("utf-8")
            else:
                text = sys.stdin.read()
        else:
            text = Path(args.path).read_text(encoding="utf-8")
    except UnicodeError:
        parser.error(f"не удалось прочитать {args.path!r}: ожидается текст в UTF-8")
    except OSError as exc:
        parser.error(f"не удалось прочитать {args.path!r}: {exc}")

    report = check_text(text, context, extra_trademarks=args.trademark_word)

    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(report)

    if args.fail_on == "never":
        return 0
    if args.fail_on == "review":
        return 1 if any(
            finding.status in (Status.LIKELY_VIOLATION, Status.NEEDS_REVIEW)
            for finding in report.findings
        ) else 0
    return 1 if report.has_likely_violation else 0


if __name__ == "__main__":
    raise SystemExit(main())
