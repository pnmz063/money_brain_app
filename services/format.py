"""Formatting helpers shared across domain and UI layers.

Kept deliberately tiny — only pure string formatters with no domain logic.
"""
from __future__ import annotations


def fmt_amount_compact(value: float) -> str:
    """Format a money amount in compact Russian style (млн / тыс / ₽)."""
    if value is None or value <= 0:
        return "0 ₽"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн ₽"
    if value >= 1_000:
        return f"{value / 1_000:.0f} тыс ₽"
    return f"{value:.0f} ₽"
