from __future__ import annotations

from typing import List, Dict, Any


def normalize_obligation(ob: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **ob,
        "balance": float(ob.get("balance", 0) or 0),
        "monthly_payment": float(ob.get("monthly_payment", 0) or 0),
        "priority_score": float(ob.get("priority_score", 0) or 0),
        "prepayment_allowed": bool(ob.get("prepayment_allowed", True)),
        "exclude_from_prepayment": bool(ob.get("exclude_from_prepayment", False)),
        "prepayment_order": ob.get("prepayment_order"),
        "recommended_action": ob.get("recommended_action"),
        "manual_prepayment_mode": ob.get("manual_prepayment_mode", "auto"),
    }


def choose_prepayment_target(obligations: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    items = [normalize_obligation(x) for x in obligations]

    candidates = [
        x for x in items
        if x["prepayment_allowed"]
        and not x["exclude_from_prepayment"]
        and x["manual_prepayment_mode"] != "skip_prepayment"
        and x["recommended_action"] not in ("skip", "minimum_only")
        and x["balance"] > 0
    ]

    if not candidates:
        return None

    manual_ranked = [x for x in candidates if x["prepayment_order"] is not None]
    if manual_ranked:
        manual_ranked.sort(
            key=lambda x: (
                int(x["prepayment_order"]),
                -float(x["balance"]),
            )
        )
        return manual_ranked[0]

    # Гасим самый дорогой кредит первым (highest rate → highest score)
    candidates.sort(
        key=lambda x: (
            -float(x.get("rate", 0) or 0),
            -float(x["priority_score"]),
        )
    )
    return candidates[0]


def allocate_prepayment(obligations: List[Dict[str, Any]], prepayment_budget: float) -> List[Dict[str, Any]]:
    budget = max(float(prepayment_budget), 0.0)
    items = [normalize_obligation(x) for x in obligations]
    target = choose_prepayment_target(items)

    result = []
    for ob in items:
        allocated = 0.0
        if target and ob["name"] == target["name"]:
            allocated = min(budget, ob["balance"]) if ob["balance"] > 0 else budget

        result.append({
            **ob,
            "allocated_prepayment": round(allocated, 2),
        })

    return sorted(
        result,
        key=lambda x: (
            -float(x["allocated_prepayment"]),
            x["prepayment_order"] if x["prepayment_order"] is not None else 999999,
            -float(x["balance"]),
            -float(x["priority_score"]),
        )
    )