"""fz168-linter — предварительная проверка языковых рисков по 168-ФЗ."""

from .checker import check_text
from .models import Context, Finding, Report, Status

__all__ = ["check_text", "Context", "Finding", "Report", "Status", "__version__"]
__version__ = "0.3.0"
