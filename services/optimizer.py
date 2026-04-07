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

from typing import TypedDict

from services.utils import to_float, estimate_payoff_months


class ClosingPhase(TypedDict):
    """View-model for one phase of the avalanche timeline.

    A "phase" = the period during which a particular debt is the avalanche
    target. Pure data, no formatting.
    """
    name: str
    rate: float
    min_payment: float
    closed_month: int
    active_payment: float          # min_payment + extra + freed minimums of already-closed debts
    cumulative_freed_after: float  # how much monthly cash flow is freed after THIS debt closes


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

        # Avalanche budget = explicit extra + freed minimums from closed debts
        freed = sum(d["min_payment"] for d in debts if d["balance"] <= 0 and d["closed_month"] is not None)
        avalanche_budget = available_extra + freed

        if remaining_active and avalanche_budget > 0:
            remaining_active.sort(key=lambda x: x["rate"], reverse=True)
            for target in remaining_active:
                if avalanche_budget <= 0:
                    break
                pay = min(avalanche_budget, target["balance"])
                target["balance"] -= pay
                target["paid"] += pay
                avalanche_budget -= pay

        # Mark newly-closed debts (must run BEFORE any break so the last
        # debt's closed_month is recorded even when the portfolio empties
        # in this iteration).
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
                "min_payment": d["min_payment"],
                "rate": d["rate"],
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


def build_closing_timeline(plan: dict, extra_budget: float) -> list[ClosingPhase]:
    """Build a UI-ready timeline of avalanche phases from an existing plan.

    Pure function — moves the per-phase arithmetic that used to live in
    the dashboard (rolling_freed_before / cumulative_freed / active_payment)
    into the domain layer where it can be tested.

    For each closed debt in avalanche order:
      active_payment = min_payment + extra_budget + sum(min_payment of all
                       previously-closed debts)
    cumulative_freed_after = sum of min_payments up to and including this debt.
    """
    extra = float(extra_budget)
    rolling_freed_before = 0.0
    cumulative = 0.0
    timeline: list[ClosingPhase] = []
    for d in plan.get("closing_order", []) or []:
        if d.get("closed_month") is None:
            continue
        min_pay = float(d.get("min_payment", 0) or 0)
        active_payment = min_pay + extra + rolling_freed_before
        cumulative += min_pay
        timeline.append({
            "name": str(d.get("name", "Долг")),
            "rate": float(d.get("rate", 0) or 0),
            "min_payment": min_pay,
            "closed_month": int(d["closed_month"]),
            "active_payment": active_payment,
            "cumulative_freed_after": cumulative,
        })
        rolling_freed_before += min_pay
    return timeline


def solve_extra_for_target_months(
    obligations: list[dict],
    target_months: int,
    *,
    lo: float = 0.0,
    hi: float | None = None,
    max_iter: int = 24,
) -> float | None:
    """Find the minimum extra ₽/month so the avalanche plan finishes within target_months.

    Inverse of build_optimal_plan: instead of "given X ₽, when do I finish?",
    answers "given a target finish date, how much do I need?".

    Strategy: binary search on extra_budget. Monotonic by construction —
    more extra never makes the plan finish later.

    Returns:
      - float: minimum extra (rounded to nearest 100 ₽) that achieves the target.
      - None:  target is unreachable even at the upper bound.
    """
    if target_months <= 0:
        return None

    # Cheap reachability checks
    base = build_optimal_plan(obligations, lo)
    if base["optimal"]["max_months"] == 0:
        return 0.0
    if base["optimal"]["max_months"] <= target_months:
        return float(lo)

    if hi is None:
        # Upper bound: 5x sum of minimum payments — heuristically "definitely enough"
        # for any realistic portfolio. If even this can't reach the target, give up.
        sum_min = sum(to_float(o.get("monthly_payment")) for o in obligations)
        hi = max(sum_min * 5.0, 100_000.0)

    top = build_optimal_plan(obligations, hi)
    if top["optimal"]["max_months"] > target_months:
        return None  # unreachable

    low, high = float(lo), float(hi)
    for _ in range(max_iter):
        mid = (low + high) / 2.0
        plan = build_optimal_plan(obligations, mid)
        if plan["optimal"]["max_months"] <= target_months:
            high = mid
        else:
            low = mid
        if high - low < 100.0:
            break

    # Round up to the nearest 100 ₽ so we never under-shoot the target.
    import math as _math
    return float(_math.ceil(high / 100.0) * 100.0)
