from __future__ import annotations

from typing import Any
import math


def to_float(value: Any, default: float = 0.0) -> float:
    """Safely convert any value (including Decimal, None, comma-formatted strings) to float."""
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()

    if not s:
        return default

    lowered = s.lower()
    if lowered in {"none", "null", "nan"}:
        return default

    s = s.replace(" ", "").replace("\xa0", "").replace("%", "")

    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        s = s.replace(",", "")

    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def estimate_payoff_months(balance: float, rate: float, monthly_payment: float) -> int | None:
    """Estimate how many months until a debt is fully paid off.

    Uses amortization formula. Returns None if the payment doesn't cover interest
    (i.e. the debt will never be paid off at this rate).
    """
    if balance <= 0 or monthly_payment <= 0:
        return 0

    if rate <= 0:
        return max(math.ceil(balance / monthly_payment), 1)

    monthly_rate = rate / 100.0 / 12.0
    interest_per_month = balance * monthly_rate

    if monthly_payment <= interest_per_month:
        return None  # Payment doesn't cover interest

    # n = -log(1 - balance * r / P) / log(1 + r)
    try:
        n = -math.log(1 - balance * monthly_rate / monthly_payment) / math.log(1 + monthly_rate)
        return max(math.ceil(n), 1)
    except (ValueError, ZeroDivisionError):
        return None
