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


def _add_name_options(parser: argparse.ArgumentParser, *, require_official: bool = False) -> None:
    parser.add_argument(
        "--official-name",
        required=require_official,
        default=None,
        help="эталонное наименование из ЕИСЖС или проектной декларации",
    )
    parser.add_argument(
        "--alias",
        action="append",
        default=[],
        help="вариант написания (можно несколько раз)",
    )
    parser.add_argument("--name-source", default=None, help="источник эталонного наименования")


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
    check.add_argument(
        "--role",
        action="append",
        default=[],
        help="роль лица: developer, advertiser, seller (можно несколько раз)",
    )
    _add_name_options(check)
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument(
        "--fail-on",
        choices=("violation", "review", "never"),
        default="violation",
        help="код выхода 1: только при LIKELY_VIOLATION, при любом NEEDS_REVIEW или никогда",
    )

    audit = subparsers.add_parser(
        "name-audit", help="сверить текст с официальным наименованием и алиасами"
    )
    audit.add_argument("text", help="проверяемый текст")
    _add_name_options(audit, require_official=True)
    audit.add_argument(
        "--surface",
        choices=("advertisement", "public_information", "internal", "unknown"),
        default="unknown",
    )
    audit.add_argument(
        "--object-type",
        choices=("residential_complex", "building", "other", "unknown"),
        default="unknown",
    )
    audit.add_argument("--ddu-ad", action="store_true", help="реклама привлечения средств дольщиков")
    audit.add_argument("--commissioned", default=None, help="дата ввода объекта, YYYY-MM-DD")
    audit.add_argument(
        "--role",
        action="append",
        default=[],
        help="роль лица: developer, advertiser, seller (можно несколько раз)",
    )
    audit.add_argument("--format", choices=("text", "json"), default="text")
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


def _emit(report, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(report)


def _read_text(path: str) -> str:
    if path == "-":
        if hasattr(sys.stdin, "buffer"):
            return sys.stdin.buffer.read().decode("utf-8")
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:  # корректный UTF-8 при перенаправлении вывода в файл
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "name-audit":
            context = Context(
                legal_surface=args.surface,
                entity_roles=tuple(args.role),
                object_type=args.object_type,
                ddu_fundraising_ad=True if args.ddu_ad else None,
                commissioned_before=args.commissioned,
                official_name=args.official_name,
                aliases=tuple(args.alias),
                name_source=args.name_source,
                input_format="text",
            )
            report = check_text(args.text, context, name_audit=True)
            _emit(report, args.format)
            return 1 if report.has_likely_violation else 0

        suffix = "" if args.path == "-" else Path(args.path).suffix.lower()
        input_format = args.input or SUFFIX_FORMATS.get(suffix, "text")
        context = Context(
            legal_surface=args.surface,
            entity_roles=tuple(args.role),
            object_type=args.object_type,
            ddu_fundraising_ad=True if args.ddu_ad else None,
            commissioned_before=args.commissioned,
            trademark_status=args.trademark,
            input_format=input_format,
            official_name=args.official_name,
            aliases=tuple(args.alias),
            name_source=args.name_source,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        text = _read_text(args.path)
    except UnicodeError:
        parser.error(f"не удалось прочитать {args.path!r}: ожидается текст в UTF-8")
    except OSError as exc:
        parser.error(f"не удалось прочитать {args.path!r}: {exc}")

    report = check_text(text, context, extra_trademarks=args.trademark_word)
    _emit(report, args.format)

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
