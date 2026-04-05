from __future__ import annotations

from typing import Dict, Any


def _to_float(value: Any, default: float = 0.0) -> float:
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


def classify_obligation(obligation: Dict[str, Any]) -> Dict[str, Any]:
    rate = _to_float(obligation.get("rate", 0))
    obligation_type = str(obligation.get("obligation_type", "loan") or "loan").strip()
    prepayment_allowed = bool(obligation.get("prepayment_allowed", True))
    manual_mode = str(obligation.get("manual_prepayment_mode", "auto") or "auto").strip()

    if manual_mode == "skip_prepayment":
        return {
            "priority_score": -1.0,
            "recommended_action": "skip",
            "recommendation_reason": "Долг исключён из досрочного погашения вручную.",
        }

    if not prepayment_allowed:
        return {
            "priority_score": 0.0,
            "recommended_action": "minimum_only",
            "recommendation_reason": "Для этого долга досрочное погашение отключено.",
        }

    if obligation_type == "installment" or rate <= 6:
        return {
            "priority_score": 10.0 + rate,
            "recommended_action": "skip",
            "recommendation_reason": "Ставка низкая: досрочка не в приоритете.",
        }

    if obligation_type == "credit_card":
        return {
            "priority_score": 100.0 + rate,
            "recommended_action": "fast",
            "recommendation_reason": "Кредитная карта с высокой стоимостью долга.",
        }

    if rate >= 18:
        return {
            "priority_score": 80.0 + rate,
            "recommended_action": "fast",
            "recommendation_reason": "Высокая ставка: гасить в первую очередь.",
        }

    if rate >= 12:
        return {
            "priority_score": 50.0 + rate,
            "recommended_action": "medium",
            "recommendation_reason": "Средняя ставка: можно гасить после самых дорогих долгов.",
        }

    return {
        "priority_score": 20.0 + rate,
        "recommended_action": "medium",
        "recommendation_reason": "Долг можно гасить досрочно, но он не самый дорогой.",
    }