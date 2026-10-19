"""Модели данных линтера: контекст, находка, отчёт."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple


class Status(str, Enum):
    """Статус находки. «OK» как «юридически разрешено» намеренно не используется."""

    LIKELY_VIOLATION = "LIKELY_VIOLATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NO_ISSUE_FOUND = "NO_ISSUE_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"


SURFACES = ("advertisement", "public_information", "internal", "unknown")
OBJECT_TYPES = ("residential_complex", "building", "other", "unknown")
TRADEMARK_STATUSES = ("registered", "application", "none", "unknown")
INPUT_FORMATS = ("text", "html", "jsx", "markdown")


@dataclass
class Context:
    """Правовой и технический контекст проверки.

    Флаги независимы: одна компания может быть застройщиком, продавцом
    и рекламодателем одновременно.
    """

    legal_surface: str = "unknown"
    entity_roles: Tuple[str, ...] = field(default_factory=tuple)
    object_type: str = "unknown"
    ddu_fundraising_ad: Optional[bool] = None
    commissioned_before: Optional[str] = None
    trademark_status: str = "unknown"
    input_format: str = "text"

    def __post_init__(self) -> None:
        if self.legal_surface not in SURFACES:
            raise ValueError(f"legal_surface: {self.legal_surface!r} не из {SURFACES}")
        if self.object_type not in OBJECT_TYPES:
            raise ValueError(f"object_type: {self.object_type!r} не из {OBJECT_TYPES}")
        if self.trademark_status not in TRADEMARK_STATUSES:
            raise ValueError(f"trademark_status: {self.trademark_status!r} не из {TRADEMARK_STATUSES}")
        if self.input_format not in INPUT_FORMATS:
            raise ValueError(f"input_format: {self.input_format!r} не из {INPUT_FORMATS}")
        if self.ddu_fundraising_ad is not None and type(self.ddu_fundraising_ad) is not bool:
            raise ValueError("ddu_fundraising_ad должен быть bool или None")
        if self.commissioned_before is not None:
            try:
                value = date.fromisoformat(self.commissioned_before)
                if value.isoformat() != self.commissioned_before:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError("commissioned_before: нужна дата YYYY-MM-DD") from None
        if not isinstance(self.entity_roles, (tuple, list)) or not all(
            isinstance(role, str) and role for role in self.entity_roles
        ):
            raise ValueError("entity_roles должен быть списком или кортежем непустых строк")
        self.entity_roles = tuple(self.entity_roles)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Context":
        if not isinstance(data, dict):
            raise TypeError("context должен быть словарём")
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "legal_surface": self.legal_surface,
            "entity_roles": list(self.entity_roles),
            "object_type": self.object_type,
            "ddu_fundraising_ad": self.ddu_fundraising_ad,
            "commissioned_before": self.commissioned_before,
            "trademark_status": self.trademark_status,
            "input_format": self.input_format,
        }


@dataclass
class Finding:
    """Одно срабатывание. Позиции считаются по исходной строке."""

    code: str
    status: Status
    message: str
    start: int
    end: int
    line: int
    column: int
    text: str
    rule_id: Optional[str] = None
    legal_basis: Tuple[str, ...] = field(default_factory=tuple)
    confidence: str = "medium"
    replacements: Tuple[str, ...] = field(default_factory=tuple)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "status": self.status.value,
            "message": self.message,
            "start": self.start,
            "end": self.end,
            "line": self.line,
            "column": self.column,
            "text": self.text,
            "rule_id": self.rule_id,
            "legal_basis": list(self.legal_basis),
            "confidence": self.confidence,
            "replacements": list(self.replacements),
            "details": self.details,
        }


@dataclass
class Report:
    findings: List[Finding]
    context: Context
    rules_version: str
    dictionary_version: str

    @property
    def has_likely_violation(self) -> bool:
        return any(f.status is Status.LIKELY_VIOLATION for f in self.findings)

    def by_status(self, status: Status) -> List[Finding]:
        return [f for f in self.findings if f.status is status]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rules_version": self.rules_version,
            "dictionary_version": self.dictionary_version,
            "context": self.context.to_dict(),
            "has_likely_violation": self.has_likely_violation,
            "findings": [f.to_dict() for f in self.findings],
        }

    def __iter__(self) -> Iterable[Finding]:
        return iter(self.findings)
