"""Классификатор находок по правовому контексту."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .detector import TextMap, iter_cyrillic, iter_latin, iter_mixed, mask_for
from .homoglyphs import find_mixed_script
from .models import Context, Finding, Report, Status

DATA_DIR = Path(__file__).with_name("data")

# Буквальное прочтение ч. 3 ст. 5 168-ФЗ: «до дня вступления в силу
# настоящего Федерального закона» = 24.06.2025 (день опубликования).
LITERAL_EXEMPTION = "2025-06-24"
# Распространённое в комментариях прочтение: объекты, введённые до 01.03.2026.
COMMENTARY_EXEMPTION = "2026-03-01"

_LEGAL_214 = ("214-ФЗ п. 7 ст. 2 (введён ст. 4 168-ФЗ)",)
_LEGAL_ZOZPP = ("ЗоЗПП ст. 10.1 п. 2 (введена ст. 1 168-ФЗ)", "53-ФЗ ч. 2 ст. 3")
_LEGAL_AD = ("38-ФЗ ч. 11 ст. 5", "53-ФЗ ч. 2 ст. 3", "приказ ФАС № 1079/23")
_LEGAL_TRADEMARK = ("ЗоЗПП ст. 10.1 п. 4", "53-ФЗ ч. 3 ст. 3")


def _norm(value: str) -> str:
    return value.lower().replace("ё", "е").strip()


def _has_latin(value: str) -> bool:
    return any("a" <= char.lower() <= "z" for char in value)


@lru_cache(maxsize=1)
def load_data() -> Dict[str, Any]:
    def read(name: str) -> Dict[str, Any]:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))

    tech = read("whitelist_tech.json")
    approved = read("dictionary_approved.json")
    rules_doc = read("rules_re.json")
    meta = read("dictionaries_meta.json")

    latin_index: Dict[str, Dict[str, Any]] = {}
    cyrillic_index: Dict[str, Dict[str, Any]] = {}
    for rule in rules_doc["rules"]:
        for variant in rule.get("latin_variants", []):
            latin_index[_norm(variant)] = rule
        for variant in rule.get("variants", []):
            if not _has_latin(variant):
                cyrillic_index[_norm(variant)] = rule

    return {
        "tech": {_norm(term) for term in tech["terms"]},
        "approved": {_norm(word) for word in approved["words"]},
        "latin_index": latin_index,
        "cyrillic_index": cyrillic_index,
        "rules_version": rules_doc.get("version", "unknown"),
        "dictionary_version": meta.get("version", "unknown"),
        "meta": meta,
    }


def _make(
    code: str,
    status: Status,
    message: str,
    start: int,
    end: int,
    text: str,
    text_map: TextMap,
    **kwargs: Any,
) -> Finding:
    line, column = text_map.position(start)
    return Finding(
        code=code,
        status=status,
        message=message,
        start=start,
        end=end,
        line=line,
        column=column,
        text=text,
        **kwargs,
    )


def _has_russian_equivalent(rule: Optional[Dict[str, Any]], normalized_text: str) -> bool:
    if not rule:
        return False
    for replacement in rule.get("replacements", []):
        head = _norm(replacement.split()[0])
        if len(head) >= 4 and head in normalized_text:
            return True
    return False


_MORPH = None
_MORPH_TRIED = False


def _lemma(word: str) -> Optional[str]:
    global _MORPH, _MORPH_TRIED
    if not _MORPH_TRIED:
        _MORPH_TRIED = True
        try:
            import pymorphy3  # type: ignore

            _MORPH = pymorphy3.MorphAnalyzer()
        except Exception:
            _MORPH = None
    if _MORPH is None:
        return None
    try:
        return _MORPH.parse(word)[0].normal_form
    except Exception:
        return None


def _is_naming_context(context: Context) -> bool:
    return context.object_type == "residential_complex" and context.ddu_fundraising_ad is True


def _exemption(context: Context) -> Optional[Tuple[Status, str]]:
    if not context.commissioned_before:
        return None
    if context.commissioned_before <= LITERAL_EXEMPTION:
        return (
            Status.NOT_APPLICABLE,
            "Объект введён до дня вступления закона в силу (ч. 3 ст. 5 168-ФЗ) — "
            "норма о кириллице к наименованию не применяется.",
        )
    if context.commissioned_before < COMMENTARY_EXEMPTION:
        return (
            Status.NEEDS_REVIEW,
            "Дата ввода между 24.06.2025 и 01.03.2026. Буквальное прочтение ч. 3 ст. 5 "
            "168-ФЗ исключения не даёт, распространённое толкование — даёт. Нужна "
            "юридическая проверка.",
        )
    return None


def check_text(
    text: str,
    context: Optional[Any] = None,
    *,
    input_format: Optional[str] = None,
    extra_trademarks: Optional[Sequence[str]] = None,
    extra_whitelist: Optional[Sequence[str]] = None,
) -> Report:
    """Проверяет текст и возвращает отчёт.

    ``context`` — :class:`Context` или dict. ``input_format`` переопределяет
    формат из контекста.
    """

    if context is None:
        ctx = Context()
    elif isinstance(context, Context):
        ctx = context
    elif isinstance(context, dict):
        ctx = Context.from_dict(context)
    else:
        raise TypeError("context должен быть Context, dict или None")

    if input_format is not None:
        data = ctx.to_dict()
        data["input_format"] = input_format
        ctx = Context.from_dict(data)

    data_store = load_data()
    tech: Set[str] = set(data_store["tech"])
    tech.update(_norm(term) for term in (extra_whitelist or ()))
    trademarks = {_norm(word) for word in (extra_trademarks or ())}

    masked = mask_for(text, ctx.input_format)
    text_map = TextMap(text)
    normalized_text = _norm(masked)
    findings: List[Finding] = []

    # 1. Смешанные алфавиты (гомоглифы).
    for start, end, token in iter_mixed(masked, text):
        chars = find_mixed_script(token)
        if not chars:
            continue
        if _is_naming_context(ctx):
            status = Status.LIKELY_VIOLATION
            message = (
                "Смешение алфавитов в наименовании объекта: требование «только с "
                "использованием кириллицы» (214-ФЗ п. 7 ст. 2)."
            )
            basis = _LEGAL_214
            confidence = "high"
        else:
            status = Status.NEEDS_REVIEW
            message = (
                "Слово содержит латинские и кириллические символы: возможна визуальная "
                "подмена. Проверьте эталонное написание."
            )
            basis = ()
            confidence = "high"
        findings.append(
            _make(
                "MIXED_SCRIPT_SUSPECTED",
                status,
                message,
                start,
                end,
                token,
                text_map,
                legal_basis=basis,
                confidence=confidence,
                details={"chars": chars},
            )
        )

    # 2. Латиница.
    for start, end, token in iter_latin(masked, text):
        normalized = _norm(token)
        if normalized in tech:
            continue
        rule = data_store["latin_index"].get(normalized)

        if _is_naming_context(ctx):
            exemption = _exemption(ctx)
            if exemption is not None:
                status, message = exemption
                findings.append(
                    _make(
                        "naming-214fz-exemption",
                        status,
                        message,
                        start,
                        end,
                        token,
                        text_map,
                        legal_basis=_LEGAL_214,
                        confidence="medium",
                        rule_id=rule["id"] if rule else None,
                    )
                )
                continue
            if normalized in trademarks:
                message = (
                    "Наименование ЖК в рекламе долевого строительства: исключение для "
                    "зарегистрированных товарных знаков (ст. 10.1 п. 4 ЗоЗПП) не отменяет "
                    "требование 214-ФЗ о кириллице."
                )
                code = "naming-214fz-trademark"
            else:
                message = (
                    "Наименование объекта в рекламе, связанной с привлечением средств "
                    "дольщиков, должно быть только на кириллице (214-ФЗ п. 7 ст. 2)."
                )
                code = "naming-214fz"
            findings.append(
                _make(
                    code,
                    Status.LIKELY_VIOLATION,
                    message,
                    start,
                    end,
                    token,
                    text_map,
                    legal_basis=_LEGAL_214,
                    confidence="high",
                    rule_id=rule["id"] if rule else None,
                    replacements=tuple(rule.get("replacements", ())) if rule else (),
                )
            )
            continue

        if normalized in trademarks:
            findings.append(
                _make(
                    "trademark-exception",
                    Status.NO_ISSUE_FOUND,
                    "Обозначение передано как зарегистрированный товарный знак: для вывесок "
                    "и публичной информации действует исключение (ст. 10.1 п. 4 ЗоЗПП, "
                    "ч. 3 ст. 3 53-ФЗ). Для наименования ЖК в рекламе ДДУ исключение не "
                    "применяется.",
                    start,
                    end,
                    token,
                    text_map,
                    legal_basis=_LEGAL_TRADEMARK,
                    confidence="medium",
                    rule_id=rule["id"] if rule else None,
                )
            )
            continue

        if ctx.legal_surface == "internal":
            findings.append(
                _make(
                    "latin-internal",
                    Status.NOT_APPLICABLE,
                    "Внутренний интерфейс: требования к публичной информации потребителя "
                    "и рекламе не применяются.",
                    start,
                    end,
                    token,
                    text_map,
                    confidence="medium",
                )
            )
            continue

        if ctx.legal_surface == "advertisement":
            if _has_russian_equivalent(rule, normalized_text):
                findings.append(
                    _make(
                        "russian-duplicate-present",
                        Status.NO_ISSUE_FOUND,
                        "Рядом найден русский текст. Проверьте равнозначность оформления: "
                        "цвет, тип и размер шрифта, разборчивость (ч. 2 ст. 3 53-ФЗ).",
                        start,
                        end,
                        token,
                        text_map,
                        legal_basis=_LEGAL_AD,
                        confidence="medium",
                        rule_id=rule["id"] if rule else None,
                    )
                )
            else:
                findings.append(
                    _make(
                        "advertising-foreign-text",
                        Status.NEEDS_REVIEW,
                        "Иностранный текст в рекламе без видимого русского дубля. Само по себе "
                        "нарушение ч. 11 ст. 5 38-ФЗ не образует основания для возбуждения "
                        "дела (приказ ФАС № 1079/23): нужна оценка рекламы и состава.",
                        start,
                        end,
                        token,
                        text_map,
                        legal_basis=_LEGAL_AD,
                        confidence="low",
                        rule_id=rule["id"] if rule else None,
                        replacements=tuple(rule.get("replacements", ())) if rule else (),
                    )
                )
            continue

        if ctx.legal_surface == "public_information":
            if _has_russian_equivalent(rule, normalized_text):
                findings.append(
                    _make(
                        "russian-duplicate-present",
                        Status.NO_ISSUE_FOUND,
                        "Рядом найден русский текст. Проверьте равнозначность оформления "
                        "(ч. 2 ст. 3 53-ФЗ).",
                        start,
                        end,
                        token,
                        text_map,
                        legal_basis=_LEGAL_ZOZPP,
                        confidence="medium",
                        rule_id=rule["id"] if rule else None,
                    )
                )
            else:
                findings.append(
                    _make(
                        "public-info-not-russian",
                        Status.LIKELY_VIOLATION,
                        "Публичная информация потребителя без русского текста "
                        "(ЗоЗПП ст. 10.1 п. 2). Требуется перевод или русский дубль.",
                        start,
                        end,
                        token,
                        text_map,
                        legal_basis=_LEGAL_ZOZPP,
                        confidence="medium",
                        rule_id=rule["id"] if rule else None,
                        replacements=tuple(rule.get("replacements", ())) if rule else (),
                    )
                )
            continue

        findings.append(
            _make(
                "latin-unknown-context",
                Status.NEEDS_REVIEW,
                "Латиница найдена, но правовой контекст не задан. Укажите "
                "legal_surface/object_type, чтобы получить применимую норму.",
                start,
                end,
                token,
                text_map,
                confidence="low",
                rule_id=rule["id"] if rule else None,
            )
        )

    # 3. Кириллические заимствования.
    for start, end, token in iter_cyrillic(masked, text):
        normalized = _norm(token)
        if normalized in data_store["approved"]:
            continue
        rule = data_store["cyrillic_index"].get(normalized)
        if rule is None:
            lemma = _lemma(token)
            if lemma and _norm(lemma) != normalized:
                rule = data_store["cyrillic_index"].get(_norm(lemma))
        if rule is None:
            continue
        findings.append(
            _make(
                "borrowed-word",
                Status.NEEDS_REVIEW,
                rule.get("reason", "Заимствование требует проверки."),
                start,
                end,
                token,
                text_map,
                rule_id=rule["id"],
                legal_basis=tuple(rule.get("legal_basis", ())),
                confidence=rule.get("confidence", "medium"),
                replacements=tuple(rule.get("replacements", ())),
                details={"source": rule.get("source", "")},
            )
        )

    findings.sort(key=lambda item: (item.start, item.code))
    return Report(
        findings=findings,
        context=ctx,
        rules_version=data_store["rules_version"],
        dictionary_version=data_store["dictionary_version"],
    )
