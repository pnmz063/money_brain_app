from __future__ import annotations

from typing import Dict, Any, List


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
    balance = _to_float(obligation.get("balance", 0))
    monthly_payment = _to_float(obligation.get("monthly_payment", 0))

    if manual_mode == "skip_prepayment":
        return {
            "priority_score": -1.0,
            "recommended_action": "skip",
            "recommendation_reason": "Долг исключён из досрочного погашения вручную.",
            "priority": 5,
        }

    if manual_mode == "minimum_only":
        return {
            "priority_score": 0.0,
            "recommended_action": "minimum_only",
            "recommendation_reason": "Пользователь выбрал платить только обязательный минимум.",
            "priority": 4,
        }

    if not prepayment_allowed:
        return {
            "priority_score": 0.0,
            "recommended_action": "minimum_only",
            "recommendation_reason": "Для этого долга досрочное погашение отключено.",
            "priority": 4,
        }

    if obligation_type == "installment" or rate <= 6:
        return {
            "priority_score": 10.0 + rate,
            "recommended_action": "skip",
            "recommendation_reason": "Ставка низкая: досрочка не в приоритете.",
            "priority": 5,
        }

    if obligation_type == "credit_card" or rate >= 20:
        return {
            "priority_score": 100.0 + rate,
            "recommended_action": "fast",
            "recommendation_reason": "Высокая стоимость долга: гасить в первую очередь.",
            "priority": 1,
        }

    if rate >= 12:
        return {
            "priority_score": 50.0 + rate,
            "recommended_action": "medium",
            "recommendation_reason": "Средняя ставка: можно гасить после самых дорогих долгов.",
            "priority": 2,
        }

    return {
        "priority_score": 20.0 + rate,
        "recommended_action": "minimum_only",
        "recommendation_reason": "Ставка умеренная: достаточно платить по графику.",
        "priority": 3,
    }


def rank_obligations(obligations: List[Dict]) -> List[Dict]:
    ranked = []
    for item in obligations:
        result = classify_obligation(item)
        merged = {**item, **result}
        ranked.append(merged)
    return sorted(ranked, key=lambda x: (-_to_float(x.get("priority_score", 0)), x.get("priority", 3)))


def action_label(action: str) -> str:
    mapping = {
        "fast": "Гасить в первую очередь",
        "medium": "Гасить умеренно",
        "minimum_only": "Платить по графику / минимум",
        "skip": "Не гасить досрочно",
    }
    return mapping.get(action, action)
