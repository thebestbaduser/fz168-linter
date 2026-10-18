"""Обнаружение гомоглифов: латинские символы внутри кириллических слов."""

from __future__ import annotations

from typing import Dict, List, Optional

CYRILLIC_LETTERS = set(
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
)

# Латинская буква -> вероятная кириллическая, которую подменяли.
LATIN_TO_CYRILLIC: Dict[str, str] = {
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к",
    "m": "м", "o": "о", "p": "р", "t": "т", "x": "х", "y": "у",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К",
    "M": "М", "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
}


def is_cyrillic(char: str) -> bool:
    return char in CYRILLIC_LETTERS


def is_latin(char: str) -> bool:
    return ("A" <= char <= "Z") or ("a" <= char <= "z")


def find_mixed_script(token: str) -> List[Dict[str, Optional[str]]]:
    """Возвращает список латинских символов внутри слова со смешанными алфавитами.

    Пустой список означает, что слово моноалфавитное. Это важно: латинское слово
    в русском тексте — не гомоглиф, а обычная латиница.
    """

    has_cyrillic = any(is_cyrillic(c) for c in token)
    has_latin = any(is_latin(c) for c in token)
    if not (has_cyrillic and has_latin):
        return []

    result: List[Dict[str, Optional[str]]] = []
    for index, char in enumerate(token):
        if not is_latin(char):
            continue
        expected = LATIN_TO_CYRILLIC.get(char)
        result.append(
            {
                "index": index,
                "char": char,
                "codepoint": f"U+{ord(char):04X}",
                "expected": expected,
                "expected_codepoint": f"U+{ord(expected):04X}" if expected else None,
            }
        )
    return result
