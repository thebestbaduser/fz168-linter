"""Валидатор для моделей и форм Django.

Django импортируется лениво: пакет должен устанавливаться и работать без него.
"""

from __future__ import annotations

from typing import Any

from .checker import check_text
from .models import Context, Status


class FZ168Validator:
    """Блокирует сохранение при ``LIKELY_VIOLATION``.

    ``NEEDS_REVIEW`` не блокируется — это сигнал редактору.
    """

    def __init__(self, **context_kwargs: Any) -> None:
        context = Context(**context_kwargs)
        self.context_kwargs = {key: getattr(context, key) for key in context_kwargs}

    def __call__(self, value: Any) -> None:
        from django.core.exceptions import ValidationError

        report = check_text(str(value), Context(**self.context_kwargs))
        violations = report.by_status(Status.LIKELY_VIOLATION)
        if not violations:
            return
        details = "; ".join(f"«{item.text}»: {item.message}" for item in violations[:3])
        basis = "; ".join(sorted({b for item in violations for b in item.legal_basis}))
        raise ValidationError(
            "Текст содержит языковой риск по 168-ФЗ: %(details)s. Основание: %(basis)s.",
            params={"details": details, "basis": basis or "см. отчёт линтера"},
            code="fz168",
        )

    def deconstruct(self):
        path = f"{self.__class__.__module__}.{self.__class__.__name__}"
        return path, [], dict(self.context_kwargs)

    def __eq__(self, other: Any) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented
        return Context(**self.context_kwargs) == Context(**other.context_kwargs)
