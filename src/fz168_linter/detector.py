"""Детекторы и маскирование разметки.

Позиции символов считаются по исходной строке: маскирование заменяет
технические фрагменты пробелами, не меняя длину текста.
"""

from __future__ import annotations

import bisect
import html
import re
from typing import Iterator, List, Tuple

LATIN_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9А-Яа-яЁё])[A-Za-z][A-Za-z0-9]*"
    r"(?:[&+.'\-][A-Za-z0-9]+)*(?![A-Za-z0-9А-Яа-яЁё])"
)
CYRILLIC_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9А-Яа-яЁё])[А-Яа-яЁё]+"
    r"(?:-[А-Яа-яЁё]+)*(?![A-Za-z0-9А-Яа-яЁё])"
)
MIXED_TOKEN_RE = re.compile(
    r"[A-Za-zА-Яа-яЁё][A-Za-z0-9А-Яа-яЁё]*(?:-[A-Za-z0-9А-Яа-яЁё]+)*"
)
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>()\"']+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
MD_LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")
TAG_NAME_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9:._-]*)")
ATTRIBUTE_NAME_RE = re.compile(r"[^\s=/>]+")
ENTITY_RE = re.compile(r"&(?:#[xX][0-9A-Fa-f]+|#\d+|[A-Za-z][A-Za-z0-9]+);")
DJANGO_TAG_RE = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", re.DOTALL)
TEXT_ATTRIBUTES = frozenset(("placeholder", "title", "alt", "aria-label", "aria-description"))
TEXT_INPUT_TYPES = frozenset(
    ("text", "search", "email", "tel", "url", "button", "submit", "reset")
)
JS_STATEMENT_RE = re.compile(
    r"^[ \t]*(?:import|export|const|let|var|function|return|if|for|while|"
    r"switch|try|catch|class|throw|await|async|declare|interface|type)\b"
)
JSX_START_RE = re.compile(r"<(?=[A-Za-z/])")


class TextMap:
    """Перевод абсолютного индекса в строку и колонку (1-based)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.line_starts: List[int] = [0]
        for match in re.finditer("\n", text):
            self.line_starts.append(match.end())

    def position(self, index: int) -> Tuple[int, int]:
        line = bisect.bisect_right(self.line_starts, index)
        return line, index - self.line_starts[line - 1] + 1


def _mask(chars: List[str], start: int, end: int) -> None:
    for index in range(start, min(end, len(chars))):
        if chars[index] not in "\r\n":
            chars[index] = " "


def _mask_addresses(chars: List[str]) -> str:
    visible = "".join(chars)
    for pattern in (URL_RE, EMAIL_RE):
        for match in pattern.finditer(visible):
            _mask(chars, match.start(), match.end())
    return "".join(chars)


def _mask_js_statements(chars: List[str], text: str) -> List[Tuple[int, int]]:
    """Скрывает очевидные JS/TS-строки вне разметки.

    Если в строке есть JSX, скрывается только префикс до первого тега:
    видимый текст компонента продолжает проверяться. Это не парсер:
    динамические выражения и вложенный JSX по-прежнему не вычисляются.
    Возвращает скрытые диапазоны, чтобы разбор разметки их пропускал.
    """

    spans: List[Tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*/")) or JS_STATEMENT_RE.match(line):
            jsx_start = JSX_START_RE.search(line)
            end = offset + (jsx_start.start() if jsx_start else len(line))
            _mask(chars, offset, end)
            spans.append((offset, end))
        offset += len(line)
    return spans


def mask_markdown(text: str) -> str:
    """Скрывает код, URL, e-mail и адреса ссылок; разметка сохраняет длину."""

    chars = list(text)

    cursor = 0
    while True:
        start = text.find("```", cursor)
        if start < 0:
            break
        end = text.find("```", start + 3)
        end = len(text) if end < 0 else end + 3
        _mask(chars, start, end)
        cursor = end

    for match in INLINE_CODE_RE.finditer(text):
        _mask(chars, match.start(), match.end())

    for match in MD_LINK_TARGET_RE.finditer(text):
        _mask(chars, match.start() + 1, match.end())

    return _mask_addresses(chars)


def _quoted_end(text: str, start: int) -> int:
    """Конец строкового литерала JavaScript с учётом экранирования."""

    quote = text[start]
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index
        index += 1
    return -1


def _expression_end(text: str, start: int) -> int:
    """Находит парную скобку JSX, пропуская строки и комментарии."""

    depth = 1
    index = start + 1
    while index < len(text):
        if text[index] in "'\"`":
            end = _quoted_end(text, index)
            if end < 0:
                return -1
            index = end + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                return -1
            index = end + 2
            continue
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            if end < 0:
                return -1
            index = end + 1
            continue
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _literal_span(text: str, start: int, end: int) -> Tuple[int, int]:
    """Только статическая строка: динамические выражения не вычисляются."""

    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start < end and text[start] in "'\"`" and _quoted_end(text, start) == end - 1:
        if text[start] != "`" or "${" not in text[start + 1 : end - 1]:
            return start + 1, end - 1
    return start, start


def _find_tag_end(text: str, start: int, jsx: bool = False) -> int:
    quote = None
    index = start
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif jsx and char == "{":
            end = _expression_end(text, index)
            if end < 0:
                return -1
            index = end
        elif char == ">":
            return index
        index += 1
    return -1


def _text_attribute_spans(
    text: str, start: int, end: int, name: str, jsx: bool
) -> List[Tuple[int, int]]:
    attributes = {}
    index = start
    while index < end:
        if text[index].isspace() or text[index] == "/":
            index += 1
            continue
        if jsx and text[index] == "{":
            closing = _expression_end(text, index)
            index = end if closing < 0 else closing + 1
            continue
        match = ATTRIBUTE_NAME_RE.match(text, index, end)
        if not match:
            index += 1
            continue
        attribute = match.group().lower()
        index = match.end()
        while index < end and text[index].isspace():
            index += 1
        if index >= end or text[index] != "=":
            continue
        index += 1
        while index < end and text[index].isspace():
            index += 1
        if index >= end:
            break
        if text[index] in "'\"":
            closing = text.find(text[index], index + 1, end)
            if closing < 0:
                break
            span = (index + 1, closing)
            index = closing + 1
        elif jsx and text[index] == "{":
            closing = _expression_end(text, index)
            if closing < 0:
                break
            span = _literal_span(text, index + 1, closing)
            index = closing + 1
        else:
            value_start = index
            while index < end and not text[index].isspace():
                index += 1
            span = (value_start, index)
        # HTML использует первое значение при повторе атрибута.
        attributes.setdefault(attribute, span)

    spans = [span for attribute, span in attributes.items() if attribute in TEXT_ATTRIBUTES]
    if name == "input" and "value" in attributes:
        type_span = attributes.get("type")
        input_type = text[slice(*type_span)].lower() if type_span else "text"
        if input_type in TEXT_INPUT_TYPES:
            spans.append(attributes["value"])
    return spans


def mask_html(text: str, jsx: bool = False) -> str:
    """Оставляет текст и статические подписи HTML/JSX, сохраняя позиции."""

    chars = list(text)
    js_spans = _mask_js_statements(chars, text) if jsx else []
    index = 0
    length = len(text)

    def _in_js_span(position: int) -> bool:
        return any(left <= position < right for left, right in js_spans)

    while index < length:
        if jsx and _in_js_span(index):
            index += 1
            continue

        if text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            end = length if end < 0 else end + 3
            _mask(chars, index, end)
            index = end
            continue

        if text[index] == "<" and index + 1 < length and (
            text[index + 1].isalpha() or text[index + 1] in "/!"
        ):
            end = _find_tag_end(text, index + 1, jsx=jsx)
            if end < 0:
                _mask(chars, index, length)
                break
            tag_match = TAG_NAME_RE.match(text, index)
            name = tag_match.group(2).lower() if tag_match else ""
            closing = bool(tag_match and tag_match.group(1))
            _mask(chars, index, end + 1)
            if not closing and name in ("script", "style"):
                close = re.search(r"</" + name + r"\s*>", text[end + 1 :], re.IGNORECASE)
                if close is None:
                    _mask(chars, end + 1, length)
                    index = length
                else:
                    close_end = end + close.end()
                    _mask(chars, end + 1, close_end + 1)
                    index = close_end + 1
            else:
                if tag_match and not closing:
                    for left, right in _text_attribute_spans(
                        text, tag_match.end(), end, name, jsx
                    ):
                        chars[left:right] = text[left:right]
                index = end + 1
            continue

        if jsx and text[index] == "{":
            cursor = _expression_end(text, index)
            cursor = length if cursor < 0 else cursor
            _mask(chars, index, min(cursor + 1, length))
            if cursor < length:
                left, right = _literal_span(text, index + 1, cursor)
                chars[left:right] = text[left:right]
            index = cursor + 1
            continue

        index += 1

    visible = "".join(chars)
    for match in ENTITY_RE.finditer(visible):
        if html.unescape(match.group()) != match.group():
            _mask(chars, match.start(), match.end())
    return _mask_addresses(chars)


def mask_django(text: str) -> str:
    """Маскирует разметку и теги шаблона Django, сохраняя видимый текст.

    Сначала скрываются HTML-теги и атрибуты, затем ``{% ... %}``, ``{{ ... }}``
    и ``{# ... #}`` — в том числе внутри ранее оставленных видимых атрибутов.
    Позиции остаются по исходной строке.
    """

    chars = list(mask_html(text))
    for match in DJANGO_TAG_RE.finditer(text):
        _mask(chars, match.start(), match.end())
    return _mask_addresses(chars)


def mask_for(text: str, input_format: str) -> str:
    if input_format == "html":
        return mask_html(text)
    if input_format == "jsx":
        return mask_html(text, jsx=True)
    if input_format == "markdown":
        return mask_markdown(text)
    if input_format == "django":
        return mask_django(text)
    return _mask_addresses(list(text))


def iter_latin(masked: str, original: str) -> Iterator[Tuple[int, int, str]]:
    for match in LATIN_TOKEN_RE.finditer(masked):
        yield match.start(), match.end(), original[match.start() : match.end()]


def iter_cyrillic(masked: str, original: str) -> Iterator[Tuple[int, int, str]]:
    for match in CYRILLIC_WORD_RE.finditer(masked):
        yield match.start(), match.end(), original[match.start() : match.end()]


def iter_mixed(masked: str, original: str) -> Iterator[Tuple[int, int, str]]:
    for match in MIXED_TOKEN_RE.finditer(masked):
        yield match.start(), match.end(), original[match.start() : match.end()]
