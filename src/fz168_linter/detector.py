"""Детекторы и маскирование разметки.

Позиции символов считаются по исходной строке: маскирование заменяет
технические фрагменты пробелами, не меняя длину текста.
"""

from __future__ import annotations

import bisect
import re
from typing import Iterator, List, Tuple

LATIN_TOKEN_RE = re.compile(
    r"(?<![А-Яа-яЁё])[A-Za-z][A-Za-z0-9]*(?:[&+.'\-][A-Za-z0-9]+)*(?![А-Яа-яЁё])"
)
CYRILLIC_WORD_RE = re.compile(
    r"(?<![A-Za-z])[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*(?![A-Za-z])"
)
MIXED_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>()\"']+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
MD_LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")


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

    for pattern in (INLINE_CODE_RE, URL_RE, EMAIL_RE):
        for match in pattern.finditer(text):
            _mask(chars, match.start(), match.end())

    for match in MD_LINK_TARGET_RE.finditer(text):
        _mask(chars, match.start() + 1, match.end())

    return "".join(chars)


def _find_tag_end(text: str, start: int) -> int:
    quote = None
    index = start
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == ">":
            return index
        index += 1
    return -1


def mask_html(text: str, jsx: bool = False) -> str:
    """Скрывает теги, атрибуты, комментарии, script/style и (для JSX) выражения."""

    chars = list(text)
    index = 0
    length = len(text)

    while index < length:
        if text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            end = length if end < 0 else end + 3
            _mask(chars, index, end)
            index = end
            continue

        if text[index] == "<" and index + 1 < length and (
            text[index + 1].isalpha() or text[index + 1] in "/!"
        ):
            end = _find_tag_end(text, index + 1)
            if end < 0:
                _mask(chars, index, length)
                break
            tag = text[index + 1 : end].strip().lower()
            _mask(chars, index, end + 1)
            name = tag.lstrip("/").split(" ")[0].rstrip("/>") if tag else ""
            if not tag.startswith("/") and name in ("script", "style"):
                close = text.lower().find("</" + name, end + 1)
                if close < 0:
                    _mask(chars, end + 1, length)
                    index = length
                else:
                    close_end = _find_tag_end(text, close + 1)
                    close_end = length - 1 if close_end < 0 else close_end
                    _mask(chars, end + 1, close_end + 1)
                    index = close_end + 1
            else:
                index = end + 1
            continue

        if jsx and text[index] == "{":
            depth = 0
            cursor = index
            while cursor < length:
                if text[cursor] == "{":
                    depth += 1
                elif text[cursor] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                cursor += 1
            _mask(chars, index, min(cursor + 1, length))
            index = cursor + 1
            continue

        index += 1

    return "".join(chars)


def mask_for(text: str, input_format: str) -> str:
    if input_format == "html":
        return mask_html(text)
    if input_format == "jsx":
        return mask_html(text, jsx=True)
    if input_format == "markdown":
        return mask_markdown(text)
    return text


def iter_latin(masked: str, original: str) -> Iterator[Tuple[int, int, str]]:
    for match in LATIN_TOKEN_RE.finditer(masked):
        yield match.start(), match.end(), original[match.start() : match.end()]


def iter_cyrillic(masked: str, original: str) -> Iterator[Tuple[int, int, str]]:
    for match in CYRILLIC_WORD_RE.finditer(masked):
        yield match.start(), match.end(), original[match.start() : match.end()]


def iter_mixed(masked: str, original: str) -> Iterator[Tuple[int, int, str]]:
    for match in MIXED_TOKEN_RE.finditer(masked):
        yield match.start(), match.end(), original[match.start() : match.end()]
