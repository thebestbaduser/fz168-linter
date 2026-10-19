"""Классификатор находок по правовому контексту."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .detector import TextMap, iter_cyrillic, iter_latin, iter_mixed, mask_for
from .homoglyphs import find_mixed_script
from .models import Context, Finding, Report, Status

DATA_DIR = Path(__file__).with_name("data")

# Общая дата и отдельная дата вступления статей 1 и 4 (ст. 5 168-ФЗ).
GENERAL_EFFECTIVE_DATE = "2025-06-24"
NAMING_EFFECTIVE_DATE = "2026-03-01"

_LEGAL_214 = ("214-ФЗ п. 7 ст. 2 (введён ст. 4 168-ФЗ)",)
_LEGAL_ZOZPP = ("ЗоЗПП ст. 10.1 п. 2 (введена ст. 1 168-ФЗ)", "53-ФЗ ч. 2 ст. 3")
_LEGAL_AD = ("38-ФЗ ч. 11 ст. 5", "53-ФЗ ч. 2 ст. 3", "приказ ФАС № 1079/23")
_LEGAL_TRADEMARK = ("ЗоЗПП ст. 10.1 п. 4", "53-ФЗ ч. 3 ст. 3")

_NAME_WORD = r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9]*(?:[\-&+.][A-Za-zА-Яа-яЁё0-9]+)*"
NAME_MARKER_RE = re.compile(
    r"(?<!\w)(?:ЖК|жилой\s+комплекс|жилого\s+комплекса|жилом\s+комплексе|"
    r"жилой\s+дом|жилого\s+дома|жилом\s+доме)\s*[«\"']?"
    r"(" + _NAME_WORD + r"(?:[ \t]+" + _NAME_WORD + r")*)",
    re.IGNORECASE,
)
QUOTED_NAME_RE = re.compile(
    r"[«\"'](" + _NAME_WORD + r"(?:[ \t]+" + _NAME_WORD + r")*)[»\"']"
)
_INLINE_TAG_RE = re.compile(r"</?(?:span|b|strong|i|em|small|u|abbr)(?:\s[^<>]*)?\s*>", re.I)
_DUPLICATE_GAP_RE = re.compile(r"[ \t/|—–():\-]*")


def _norm(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def _term_set(values: Optional[Sequence[str]], name: str) -> Set[str]:
    if values is None:
        return set()
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} должен быть последовательностью строк, а не строкой")
    result = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} должен содержать непустые строки")
        result.add(_norm(value))
    return result


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


def _phrase_pattern(value: str) -> str:
    return r"[ \t]+".join(re.escape(word) for word in value.split())


def _same_text_block(masked: str, original: str, start: int, end: int) -> bool:
    for gap in re.finditer(r"[ \t]+", masked[start:end]):
        source = original[start + gap.start() : start + gap.end()]
        if not re.fullmatch(r"[ \t]*", _INLINE_TAG_RE.sub("", source)):
            return False
    return True


def _has_russian_equivalent(
    rule: Optional[Dict[str, Any]], masked: str, original: str, start: int, end: int
) -> bool:
    """Ищет полный перевод непосредственно около обозначения, в одном текстовом блоке.

    Текст в другом предложении, блоке HTML или атрибуте не считается дублем.
    Проверка касается содержания; оформление линтер установить не может.
    """

    if not rule:
        return False
    window_start = max(0, start - 256)
    nearby = masked[window_start : end + 256]
    for replacement in rule.get("replacements", []):
        pattern = r"(?<!\w)" + _phrase_pattern(replacement) + r"(?!\w)"
        for match in re.finditer(pattern, nearby, re.IGNORECASE):
            match_start, match_end = window_start + match.start(), window_start + match.end()
            if not _same_text_block(masked, original, match_start, match_end):
                continue
            if match_end <= start:
                left, right = match_end, start
            elif match_start >= end:
                left, right = end, match_start
            else:
                continue
            if right - left > 256:
                continue
            gap = _INLINE_TAG_RE.sub("", original[left:right])
            if _DUPLICATE_GAP_RE.fullmatch(gap):
                return True
    return False


def _iter_terms(
    masked: str,
    original: str,
    variants: Iterable[str],
    iterator: Callable[[str, str], Iterator[Tuple[int, int, str]]],
) -> Iterator[Tuple[int, int, str]]:
    """Сначала длинные словосочетания, затем оставшиеся отдельные слова."""

    phrases = sorted({term for term in variants if " " in term}, key=lambda item: (-len(item), item))
    spans: List[Tuple[int, int, str]] = []
    for phrase in phrases:
        pattern = r"(?<!\w)" + _phrase_pattern(phrase) + r"(?!\w)"
        for match in re.finditer(pattern, masked, re.IGNORECASE):
            if not _same_text_block(masked, original, match.start(), match.end()):
                continue
            if not any(match.start() < right and match.end() > left for left, right, _ in spans):
                spans.append((match.start(), match.end(), original[match.start() : match.end()]))
    phrase_spans = tuple(spans)
    spans.extend(
        (start, end, token)
        for start, end, token in iterator(masked, original)
        if not any(start < right and end > left for left, right, _ in phrase_spans)
    )
    yield from sorted(spans)


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
    return (
        context.object_type in ("residential_complex", "building")
        and context.ddu_fundraising_ad is True
    )


def _looks_like_bare_name(text: str) -> bool:
    """Короткое самостоятельное обозначение; русскую рекламную фразу не считаем именем."""

    stripped = text.strip()
    if not stripped or len(stripped) > 80:
        return False
    return (
        not any(char in stripped for char in ".,;:!?\r\n")
        and all(_has_latin(word) for word in stripped.split())
    )


def _name_spans(masked: str) -> List[Tuple[int, int]]:
    """Границы вероятного наименования объекта.

    Название определяется после маркеров «ЖК», «жилой комплекс», в кавычках,
    либо как вся короткая строка без знаков конца предложения. Это эвристика:
    остальная латиница в рекламе получает статус рекламного текста, а не
    нарушения 214-ФЗ.
    """

    spans: List[Tuple[int, int]] = []
    for marker in re.finditer(
        r"(?<!\w)(?:ЖК|жилой\s+комплекс|жилого\s+комплекса|жилом\s+комплексе|"
        r"жилой\s+дом|жилого\s+дома|жилом\s+доме)\s*", masked, re.IGNORECASE
    ):
        quoted = QUOTED_NAME_RE.match(masked, marker.end())
        if quoted:
            spans.append((quoted.start(1), quoted.end(1)))
            continue
        match = NAME_MARKER_RE.match(masked, marker.start())
        if match:
            # После латинского обозначения русский текст считается уже описанием.
            name = match.group(1)
            parts = list(re.finditer(_NAME_WORD, name))
            last = match.start(1)
            seen_latin = False
            for part in parts:
                latin = _has_latin(part.group())
                if not latin and (seen_latin or part.group()[0].islower()):
                    break
                seen_latin = seen_latin or latin
                last = match.start(1) + part.end()
            spans.append((match.start(1), last))
    quoted = QUOTED_NAME_RE.fullmatch(masked.strip())
    if not spans and quoted:
        offset = len(masked) - len(masked.lstrip())
        spans.append((offset + quoted.start(1), offset + quoted.end(1)))
    if not spans and _looks_like_bare_name(masked):
        spans.append((0, len(masked)))
    return spans


def _in_spans(start: int, end: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(start >= left and end <= right for left, right in spans)


def _clean_name(value: str) -> str:
    text = re.sub(r"[«»\"'`]", "", value)
    return re.sub(r"\s+", " ", text).strip(" .,:;!?—-")


def _name_phrase_pattern(value: str) -> str:
    words = []
    for word in _clean_name(value).split():
        escaped = re.escape(word)
        escaped = escaped.replace("е", "[её]").replace("Е", "[ЕЁ]")
        words.append(escaped)
    return r"[ \t]+".join(words)


def _name_spans_for(masked: str, value: str) -> List[Tuple[int, int]]:
    pattern = _name_phrase_pattern(value)
    if not pattern:
        return []
    return [
        (match.start(), match.end())
        for match in re.finditer(r"(?<!\w)" + pattern + r"(?!\w)", masked, re.IGNORECASE)
    ]


def _exemption(context: Context) -> Optional[Tuple[Status, str]]:
    if not context.commissioned_before:
        return None
    if context.commissioned_before < GENERAL_EFFECTIVE_DATE:
        return (
            Status.NOT_APPLICABLE,
            "Объект введён до дня вступления закона в силу (ч. 3 ст. 5 168-ФЗ) — "
            "норма о кириллице к наименованию не применяется.",
        )
    if context.commissioned_before < NAMING_EFFECTIVE_DATE:
        return (
            Status.NEEDS_REVIEW,
            "Дата ввода между общей датой вступления закона в силу (24.06.2025) "
            "и датой вступления нормы о наименовании (01.03.2026). Применимость "
            "переходного исключения ч. 3 ст. 5 168-ФЗ требует юридической проверки.",
        )
    return None


def check_text(
    text: str,
    context: Optional[Any] = None,
    *,
    input_format: Optional[str] = None,
    extra_trademarks: Optional[Sequence[str]] = None,
    extra_whitelist: Optional[Sequence[str]] = None,
    name_audit: bool = False,
) -> Report:
    """Проверяет текст и возвращает отчёт.

    ``context`` — :class:`Context` или dict. ``input_format`` переопределяет
    формат из контекста.
    """

    if not isinstance(text, str):
        raise TypeError("text должен быть строкой")
    if context is None:
        ctx = Context()
    elif isinstance(context, Context):
        ctx = context
    elif isinstance(context, dict):
        ctx = Context.from_dict(context)
    else:
        raise TypeError("context должен быть Context, dict или None")

    # Повторная валидация защищает и от изменённого после создания Context.
    ctx = replace(ctx, **({"input_format": input_format} if input_format is not None else {}))

    data_store = load_data()
    tech: Set[str] = set(data_store["tech"])
    tech.update(_term_set(extra_whitelist, "extra_whitelist"))
    trademarks = _term_set(extra_trademarks, "extra_trademarks")

    masked = mask_for(text, ctx.input_format)
    text_map = TextMap(text)
    findings: List[Finding] = []
    name_spans = _name_spans(masked) if _is_naming_context(ctx) else []

    official_name = (ctx.official_name or "").strip()
    alias_values = [alias.strip() for alias in ctx.aliases]
    alias_spans: List[Tuple[int, int]] = []
    for alias in alias_values:
        alias_spans.extend(_name_spans_for(masked, alias))
    official_spans = _name_spans_for(masked, official_name) if official_name else []

    # 1. Смешанные алфавиты (гомоглифы).
    for start, end, token in iter_mixed(masked, text):
        chars = find_mixed_script(token)
        if not chars:
            continue
        if _norm(token) in tech and not _in_spans(start, end, name_spans):
            continue
        if _is_naming_context(ctx) and _in_spans(start, end, name_spans):
            exemption = _exemption(ctx)
            if exemption is not None:
                status, message = exemption
            else:
                status = Status.LIKELY_VIOLATION
                message = (
                    "Смешение алфавитов в наименовании объекта: требование «только с "
                    "использованием кириллицы» (214-ФЗ п. 7 ст. 2)."
                )
            basis = _LEGAL_214
            confidence = "high" if ctx.commissioned_before and not exemption else "medium"
            if ctx.commissioned_before is None:
                message += " Дата ввода не задана: проверьте переходное исключение."
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
    for start, end, token in _iter_terms(
        masked, text, set(data_store["latin_index"]) | tech | trademarks, iter_latin
    ):
        normalized = _norm(masked[start:end])
        rule = data_store["latin_index"].get(normalized)

        # Часть алиаса официального названия разбирается отдельной сверкой.
        if _in_spans(start, end, alias_spans):
            continue

        if _is_naming_context(ctx) and _in_spans(start, end, name_spans):
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
            if ctx.commissioned_before is None:
                message += " Дата ввода не задана: проверьте переходное исключение."
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
                    confidence="high" if ctx.commissioned_before else "medium",
                    rule_id=rule["id"] if rule else None,
                    replacements=tuple(rule.get("replacements", ())) if rule else (),
                )
            )
            continue

        if normalized in tech:
            continue

        if (
            normalized in trademarks
            and ctx.legal_surface != "internal"
            and ctx.trademark_status in ("registered", "unknown")
        ):
            registered = ctx.trademark_status == "registered"
            findings.append(
                _make(
                    "trademark-exception" if registered else "trademark-needs-review",
                    Status.NO_ISSUE_FOUND if registered else Status.NEEDS_REVIEW,
                    ("Обозначение передано как зарегистрированный товарный знак: для вывесок "
                    "и публичной информации действует исключение (ст. 10.1 п. 4 ЗоЗПП, "
                    "ч. 3 ст. 3 53-ФЗ). Для наименования ЖК в рекламе ДДУ исключение не "
                    "применяется.") if registered else (
                        "Обозначение передано как товарный знак, но его статус неизвестен. "
                        "Проверьте регистрацию или иное основание охраны; исключение не подтверждено."
                    ),
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
            if _has_russian_equivalent(rule, masked, text, start, end):
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
                        "дела (приказ ФАС № 1079/23). Возможны другие основания, включая "
                        "искажение смысла или отсутствие существенной информации: нужна "
                        "оценка рекламы и состава.",
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
            if _has_russian_equivalent(rule, masked, text, start, end):
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
    for start, end, token in _iter_terms(
        masked, text, data_store["cyrillic_index"], iter_cyrillic
    ):
        normalized = _norm(masked[start:end])
        if normalized in data_store["approved"]:
            continue
        rule = data_store["cyrillic_index"].get(normalized)
        if rule is None:
            lemma = _lemma(token)
            if lemma and _norm(lemma) != normalized:
                rule = data_store["cyrillic_index"].get(_norm(lemma))
        if rule is None:
            continue
        # Словарные эвристики не превращают внутренние тексты в публичную информацию.
        if ctx.legal_surface == "internal":
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
                details={
                    "source": rule.get("source", ""),
                    "dictionary_check": rule.get("dictionary_check", ""),
                },
            )
        )

    findings.sort(key=lambda item: (item.start, item.code))

    # 4. Сверка с официальным наименованием.
    developer = "developer" in {role.lower() for role in ctx.entity_roles}
    naming_context = _is_naming_context(ctx)
    official_norm = _norm(_clean_name(official_name)) if official_name else ""
    alias_seen: Set[str] = set()

    for alias in alias_values:
        alias_norm = _norm(_clean_name(alias))
        if not alias_norm or alias_norm in alias_seen or alias_norm == official_norm:
            continue
        spans = _name_spans_for(masked, alias)
        if not spans:
            continue
        alias_seen.add(alias_norm)
        start, end = spans[0]
        has_latin = any("a" <= char.lower() <= "z" for char in alias)
        details = {
            "official_name": official_name or None,
            "alias": alias,
            "name_source": ctx.name_source,
        }
        if naming_context and developer:
            code = "name-alias-latin"
            status = Status.LIKELY_VIOLATION
            message = (
                f"В рекламе ДДУ застройщика использован вариант «{alias}» при официальном "
                f"наименовании «{official_name}». По 214-ФЗ требуется кириллица."
            )
        else:
            code = "name-alias-mismatch"
            status = Status.NEEDS_REVIEW
            if official_name:
                message = (
                    f"В тексте встретился вариант «{alias}», официальное наименование — "
                    f"«{official_name}». Это расхождение с эталоном, а не автоматическое нарушение."
                )
            else:
                message = (
                    f"В тексте встретился вариант «{alias}», эталонное наименование не задано. "
                    "Укажите official_name из ЕИСЖС или проектной декларации."
                )
        findings.append(
            _make(
                code,
                status,
                message,
                start,
                end,
                text[start:end],
                text_map,
                legal_basis=_LEGAL_214 if naming_context else (),
                confidence="high" if naming_context and developer else "medium",
                details=details,
            )
        )

    official_has_latin = bool(official_name) and any(
        "a" <= char.lower() <= "z" for char in official_name
    )
    if official_has_latin:
        start, end = official_spans[0] if official_spans else (0, 0)
        if naming_context and developer:
            status = Status.LIKELY_VIOLATION
            message = (
                "Официальное наименование содержит латиницу; в рекламе ДДУ застройщика "
                "требуется кириллица (214-ФЗ п. 7 ст. 2)."
            )
        else:
            status = Status.NEEDS_REVIEW
            message = (
                "Официальное наименование содержит латиницу. Проверьте дату ввода и "
                "применимость требования 214-ФЗ."
            )
        findings.append(
            _make(
                "name-official-latin",
                status,
                message,
                start,
                end,
                official_name,
                text_map,
                legal_basis=_LEGAL_214 if naming_context else (),
                confidence="high" if naming_context and developer else "medium",
                details={
                    "name_source": ctx.name_source,
                    "position_known": bool(official_spans),
                },
            )
        )

    if name_audit and official_name and not alias_spans and not official_spans:
        findings.append(
            _make(
                "name-not-found",
                Status.NEEDS_REVIEW,
                f"Официальное наименование «{official_name}» не найдено в тексте. "
                "Проверьте, что карточка содержит эталонное название.",
                0,
                0,
                official_name,
                text_map,
                confidence="medium",
                details={"name_source": ctx.name_source},
            )
        )

    if (
        name_audit
        and official_name
        and official_spans
        and not alias_spans
        and not official_has_latin
    ):
        start, end = official_spans[0]
        findings.append(
            _make(
                "name-official-present",
                Status.NO_ISSUE_FOUND,
                "В тексте найдено официальное наименование; расхождений по эталону нет.",
                start,
                end,
                text[start:end],
                text_map,
                confidence="medium",
                details={"name_source": ctx.name_source},
            )
        )

    findings.sort(key=lambda item: (item.start, item.code))
    return Report(
        findings=findings,
        context=ctx,
        rules_version=data_store["rules_version"],
        dictionary_version=data_store["dictionary_version"],
    )
