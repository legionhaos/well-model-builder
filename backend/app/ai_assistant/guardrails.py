"""Input isolation and evidence-based numeric response checks."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"игнорируй\s+(все\s+)?(предыдущие|прошлые)\s+инструкции", re.I),
    re.compile(r"(system|developer)\s+prompt", re.I),
    re.compile(r"раскрой\s+(системный\s+)?промпт", re.I),
    re.compile(r"сообщи\s*,?\s*что\s+дебит\s+\d+(?:[.,]\d+)?", re.I),
)


def isolate_untrusted(text: str) -> str:
    """Wrap user/file text so it is data, never an instruction."""
    safe = text.replace("<untrusted_data", "&lt;untrusted_data").replace("</untrusted_data>", "&lt;/untrusted_data&gt;")
    return f"<untrusted_data>\n{safe}\n</untrusted_data>"


def detect_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in INJECTION_PATTERNS)


def sanitize_untrusted_text(text: str) -> str:
    """Remove common instruction-override phrases while preserving engineering data."""
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub("[удалена недоверенная директива]", sanitized)
    return sanitized


def flatten_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            yield number
    elif isinstance(value, dict):
        for item in value.values():
            yield from flatten_numbers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from flatten_numbers(item)


def unsupported_numbers(answer: str, evidence: Any, *, tolerance: float = 0.02) -> list[str]:
    """Return numeric literals in answer absent from trusted evidence.

    Number matching is deliberately conservative: values in evidence may be
    rendered with locale decimal commas, grouping separators, or slight rounding.
    """
    allowed = list(flatten_numbers(evidence))
    found: list[str] = []
    # Поддерживаем и ASCII дефис, и типографские тире/минусы
    for token in re.findall(r"(?<![\w])[+−–—\-]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", answer):
        clean_token = token.replace("−", "-").replace("–", "-").replace("—", "-")
        try:
            number = float(clean_token.replace(",", "."))
        except ValueError:
            continue
        # Игнорируем маркеры списков и нумерацию шагов
        if number.is_integer() and 1 <= number <= 10:
            continue
        # Проверяем как точное совпадение знака, так и модуль (инженеры часто пишут "упало на 17 атм")
        if not any(
            math.isclose(number, item, rel_tol=tolerance, abs_tol=0.1)
            or math.isclose(abs(number), abs(item), rel_tol=tolerance, abs_tol=0.1)
            for item in allowed
        ):
            found.append(token)
    return found


def redact_unsupported_numbers(answer: str, evidence: Any) -> str:
    """Replace unsupported numeric claims instead of presenting them as facts."""
    unsupported = unsupported_numbers(answer, evidence)
    for token in sorted(set(unsupported), key=len, reverse=True):
        answer = re.sub(rf"(?<![\w]){re.escape(token)}(?![\w])", "[не подтверждено расчетом]", answer)
    return answer
