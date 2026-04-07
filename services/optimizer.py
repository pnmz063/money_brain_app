"""Plan optimizer — greedy debt avalanche allocator.

Takes the user's recommended_prepayment budget and distributes it across debts:
1. Sort obligations by interest rate (highest first) — debt avalanche
2. All extra goes into the most expensive debt until it's closed
3. Then freed-up payment + extra rolls into the next most expensive debt
4. Repeat

Compares baseline (minimum payments only) vs optimal (with avalanche prepayment)
and computes the savings — that's the "value of having a plan".
"""
from __future__ import annotations

from services.utils import to_float, estimate_payoff_months


# Maximum simulation horizon in months — safety bound for the rolling simulation.
MAX_MONTHS = 600  # 50 years


def _baseline_total(obligations: list[dict]) -> dict:
    """Total interest + total paid + max months across all debts at minimum payment."""
    total_paid = 0.0
    total_interest = 0.0
    max_months = 0

    for ob in obligations:
        balance = to_float(ob.get("balance"))
        rate = to_float(ob.get("rate"))
        mp = to_float(ob.get("monthly_payment"))
        if balance <= 0 or mp <= 0:
            continue

        months = estimate_payoff_months(balance, rate, mp)
        if months is None:
            continue

        paid = mp * months
        total_paid += paid
        total_interest += paid - balance
        if months > max_months:
            max_months = months

    return {
        "total_paid": total_paid,
        "total_interest": total_interest,
        "max_months": max_months,
    }


def _simulate_avalanche(obligations: list[dict], extra_budget: float) -> dict:
    """Month-by-month simulation: extra budget rolls into highest-rate debt.

    When a debt closes, its monthly payment is freed and added to the avalanche budget.
    """
    # Build mutable state list — only debts with positive balance & payment
    debts = []
    for ob in obligations:
        balance = to_float(ob.get("balance"))
        rate = to_float(ob.get("rate"))
        mp = to_float(ob.get("monthly_payment"))
        if balance <= 0 or mp <= 0:
            continue
        debts.append({
            "name": str(ob.get("name", "Долг")),
            "balance": balance,
            "rate": rate,
            "min_payment": mp,
            "paid": 0.0,
            "closed_month": None,
        })

    if not debts:
        return {"total_paid": 0.0, "total_interest": 0.0, "max_months": 0, "debts": []}

    available_extra = float(extra_budget)
    initial_balance_sum = sum(d["balance"] for d in debts)

    for month in range(1, MAX_MONTHS + 1):
        # All debts accrue monthly interest first
        active = [d for d in debts if d["balance"] > 0]
        if not active:
            break

        for d in active:
            d["balance"] += d["balance"] * (d["rate"] / 100.0 / 12.0)

        # Pay minimums
        for d in active:
            pay = min(d["min_payment"], d["balance"])
            d["balance"] -= pay
            d["paid"] += pay

        # Direct all extra into the highest-rate still-open debt
        # (after a debt closes, its min_payment also rolls into the avalanche)
        remaining_active = [d for d in debts if d["balance"] > 0]
        if not remaining_active:
            break

        # Avalanche budget = explicit extra + freed minimums from closed debts
        freed = sum(d["min_payment"] for d in debts if d["balance"] <= 0 and d["closed_month"] is not None)
        avalanche_budget = available_extra + freed

        if avalanche_budget > 0:
            remaining_active.sort(key=lambda x: x["rate"], reverse=True)
            for target in remaining_active:
                if avalanche_budget <= 0:
                    break
                pay = min(avalanche_budget, target["balance"])
                target["balance"] -= pay
                target["paid"] += pay
                avalanche_budget -= pay

        # Mark newly-closed debts
        for d in debts:
            if d["balance"] <= 0 and d["closed_month"] is None:
                d["closed_month"] = month
                d["balance"] = 0.0

    total_paid = sum(d["paid"] for d in debts)
    total_interest = total_paid - initial_balance_sum
    max_months = max((d["closed_month"] or MAX_MONTHS) for d in debts)

    return {
        "total_paid": total_paid,
        "total_interest": max(total_interest, 0.0),
        "max_months": max_months,
        "debts": [
            {
                "name": d["name"],
                "closed_month": d["closed_month"],
                "total_paid": d["paid"],
            }
            for d in debts
        ],
    }


def build_optimal_plan(obligations: list[dict], extra_budget: float) -> dict:
    """Compare baseline vs optimal avalanche plan.

    Returns dict with both scenarios and the savings (interest + months).
    """
    baseline = _baseline_total(obligations)
    optimal = _simulate_avalanche(obligations, extra_budget)

    interest_saved = max(baseline["total_interest"] - optimal["total_interest"], 0.0)
    months_saved = max(baseline["max_months"] - optimal["max_months"], 0)

    # Order in which debts get closed (avalanche order)
    closing_order = sorted(
        [d for d in optimal["debts"] if d["closed_month"] is not None],
        key=lambda x: x["closed_month"],
    )

    return {
        "extra_budget": float(extra_budget),
        "baseline": baseline,
        "optimal": optimal,
        "interest_saved": interest_saved,
        "months_saved": months_saved,
        "closing_order": closing_order,
    }
