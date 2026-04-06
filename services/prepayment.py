from __future__ import annotations

from typing import List, Dict, Any

from services.utils import to_float as _to_float


def normalize_obligation(ob: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **ob,
        "balance": _to_float(ob.get("balance", 0)),
        "monthly_payment": _to_float(ob.get("monthly_payment", 0)),
        "priority_score": _to_float(ob.get("priority_score", 0)),
        "rate": _to_float(ob.get("rate", 0)),
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
                -x["balance"],
            )
        )
        return manual_ranked[0]

    # По умолчанию — самый дорогой долг
    candidates.sort(
        key=lambda x: (
            -x["rate"],
            -x["priority_score"],
            -x["balance"],
        )
    )
    return candidates[0]


def allocate_prepayment(obligations: List[Dict[str, Any]], prepayment_budget: float) -> List[Dict[str, Any]]:
    budget = max(_to_float(prepayment_budget), 0.0)
    items = [normalize_obligation(x) for x in obligations]
    target = choose_prepayment_target(items)

    result = []
    for ob in items:
        allocated = 0.0
        if target and ob.get("name") == target.get("name"):
            allocated = min(budget, ob["balance"]) if ob["balance"] > 0 else budget

        result.append({
            **ob,
            "allocated_prepayment": round(allocated, 2),
        })

    return sorted(
        result,
        key=lambda x: (
            -_to_float(x.get("allocated_prepayment", 0)),
            x["prepayment_order"] if x["prepayment_order"] is not None else 999999,
            -_to_float(x.get("balance", 0)),
            -_to_float(x.get("priority_score", 0)),
        )
    )