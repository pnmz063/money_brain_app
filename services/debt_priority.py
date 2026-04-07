from __future__ import annotations

from typing import Dict, Any, List

from services.utils import to_float, estimate_payoff_months
from services.format import fmt_amount_compact

# Re-export for backward compatibility (dashboard.py imports _to_float from here)
_to_float = to_float
# Backward-compat alias — historical name used inside this module.
_fmt_amount = fmt_amount_compact


def classify_obligation(obligation: Dict[str, Any]) -> Dict[str, Any]:
    rate = to_float(obligation.get("rate", 0))
    obligation_type = str(obligation.get("obligation_type", "loan") or "loan").strip()
    prepayment_allowed = bool(obligation.get("prepayment_allowed", True))
    manual_mode = str(obligation.get("manual_prepayment_mode", "auto") or "auto").strip()
    balance = to_float(obligation.get("balance", 0))
    monthly_payment = to_float(obligation.get("monthly_payment", 0))

    # Estimate payoff timeline
    payoff_months = estimate_payoff_months(balance, rate, monthly_payment)

    if manual_mode == "skip_prepayment":
        return {
            "priority_score": -1.0,
            "recommended_action": "skip",
            "recommendation_reason": "Долг исключён из досрочного погашения вручную.",
            "priority": 5,
            "payoff_months": payoff_months,
        }

    if manual_mode == "minimum_only":
        return {
            "priority_score": 0.0,
            "recommended_action": "minimum_only",
            "recommendation_reason": "Пользователь выбрал платить только обязательный минимум.",
            "priority": 4,
            "payoff_months": payoff_months,
        }

    if not prepayment_allowed:
        return {
            "priority_score": 0.0,
            "recommended_action": "minimum_only",
            "recommendation_reason": "Для этого долга досрочное погашение отключено.",
            "priority": 4,
            "payoff_months": payoff_months,
        }

    # Calculate total interest cost = how much you'll overpay
    total_interest = 0.0
    if payoff_months and payoff_months > 0 and monthly_payment > 0:
        total_interest = max(monthly_payment * payoff_months - balance, 0)

    if obligation_type == "installment" or rate <= 6:
        return {
            "priority_score": 10.0 + rate,
            "recommended_action": "skip",
            "recommendation_reason": "Ставка низкая: досрочка не в приоритете.",
            "priority": 5,
            "payoff_months": payoff_months,
            "total_interest": round(total_interest, 2),
        }

    # Base score from rate
    base_score = rate

    # Boost score by total interest cost (higher overpay = more urgent to prepay)
    if total_interest > 0:
        # Add up to 50 points based on total interest cost
        # 100k interest -> +10, 500k -> +30, 1M+ -> +50
        interest_bonus = min(total_interest / 20_000, 50.0)
        base_score += interest_bonus

    if obligation_type == "credit_card" or rate >= 20:
        return {
            "priority_score": 100.0 + base_score,
            "recommended_action": "fast",
            "recommendation_reason": f"Высокая стоимость долга: гасить первым. Переплата ~{_fmt_amount(total_interest)}.",
            "priority": 1,
            "payoff_months": payoff_months,
            "total_interest": round(total_interest, 2),
        }

    if rate >= 12:
        return {
            "priority_score": 50.0 + base_score,
            "recommended_action": "medium",
            "recommendation_reason": f"Средняя ставка: можно гасить после самых дорогих. Переплата ~{_fmt_amount(total_interest)}.",
            "priority": 2,
            "payoff_months": payoff_months,
            "total_interest": round(total_interest, 2),
        }

    return {
        "priority_score": 20.0 + base_score,
        "recommended_action": "minimum_only",
        "recommendation_reason": f"Ставка умеренная: достаточно платить по графику. Переплата ~{_fmt_amount(total_interest)}.",
        "priority": 3,
        "payoff_months": payoff_months,
        "total_interest": round(total_interest, 2),
    }


def rank_obligations(obligations: List[Dict]) -> List[Dict]:
    ranked = []
    for item in obligations:
        result = classify_obligation(item)
        merged = {**item, **result}
        ranked.append(merged)
    return sorted(ranked, key=lambda x: (-to_float(x.get("priority_score", 0)), x.get("priority", 3)))


def action_label(action: str) -> str:
    mapping = {
        "fast": "Гасить в первую очередь",
        "medium": "Гасить умеренно",
        "minimum_only": "Платить по графику / минимум",
        "skip": "Не гасить досрочно",
    }
    return mapping.get(action, action)
