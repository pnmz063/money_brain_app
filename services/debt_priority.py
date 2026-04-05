from typing import Any, Dict


def classify_obligation(obligation: Dict[str, Any]) -> Dict[str, Any]:
    rate = float(obligation.get("rate", 0) or 0)
    obligation_type = obligation.get("obligation_type", "loan")
    prepayment_allowed = bool(obligation.get("prepayment_allowed", True))
    manual_mode = obligation.get("manual_prepayment_mode", "auto")
    balance = float(obligation.get("balance", 0) or 0)
    monthly_payment = float(obligation.get("monthly_payment", 0) or 0)

    if manual_mode == "skip_prepayment":
        return {
            "priority_score": -1,
            "recommended_action": "skip",
            "recommendation_reason": "Пользователь пометил долг как нецелевой для досрочного погашения.",
            "priority": 5,
        }

    if manual_mode == "minimum_only":
        return {
            "priority_score": 0,
            "recommended_action": "minimum_only",
            "recommendation_reason": "Пользователь выбрал платить только обязательный минимум.",
            "priority": 4,
        }

    if not prepayment_allowed:
        return {
            "priority_score": 0,
            "recommended_action": "minimum_only",
            "recommendation_reason": "По долгу есть ограничение на досрочное погашение или досрочка сейчас нежелательна.",
            "priority": 4,
        }

    if obligation_type == "installment" or rate <= 6:
        return {
            "priority_score": 5 + rate,
            "recommended_action": "skip",
            "recommendation_reason": "Низкая ставка или рассрочка: досрочка не в приоритете, важнее ликвидность и подушка.",
            "priority": 5,
        }

    score = 0.0
    if obligation_type == "credit_card":
        score += 120
    elif obligation_type == "loan":
        score += 80
    elif obligation_type == "car_loan":
        score += 55
    elif obligation_type == "mortgage":
        score += 20
    else:
        score += 40

    score += rate * 2.0
    if balance > 0:
        score += min(balance / 100000, 25)
    if monthly_payment > 0:
        score += min(monthly_payment / 10000, 10)

    if obligation_type == "mortgage" and rate < 10:
        score -= 20

    if rate >= 20 or obligation_type == "credit_card":
        return {
            "priority_score": round(score, 2),
            "recommended_action": "fast",
            "recommendation_reason": "Высокая стоимость долга: его стоит гасить в первую очередь.",
            "priority": 1,
        }

    if rate >= 12:
        return {
            "priority_score": round(score, 2),
            "recommended_action": "medium",
            "recommendation_reason": "Ставка заметная: досрочка полезна, но не обязательно забирать туда весь остаток.",
            "priority": 2,
        }

    return {
        "priority_score": round(score, 2),
        "recommended_action": "minimum_only",
        "recommendation_reason": "Ставка умеренная или низкая: достаточно платить по графику или направлять небольшую досрочку.",
        "priority": 3,
    }


def rank_obligations(obligations: list[dict]) -> list[dict]:
    ranked = []
    for item in obligations:
        result = classify_obligation(item)
        merged = {**item, **result}
        ranked.append(merged)
    return sorted(ranked, key=lambda x: (x["priority_score"], -x["priority"]), reverse=True)


def action_label(action: str) -> str:
    mapping = {
        "fast": "Гасить в первую очередь",
        "medium": "Гасить умеренно",
        "minimum_only": "Платить по графику / минимум",
        "skip": "Не гасить досрочно",
    }
    return mapping.get(action, action)
