"""Insights engine — loss-aversion framed insights about debt costs.

For each active obligation:
- Computes daily interest cost (rate/365 * balance) — "this debt costs you X ₽/day"
- Simulates "what if you added +1000/2000/5000 ₽ to monthly payment" scenarios
- Returns top insights sorted by total potential savings

Each insight is framed as a LOSS (Kahneman): "You are losing X ₽ because you don't do Y"
rather than a gain ("You could save X ₽ by doing Y") — losses are ~2x more motivating.
"""
from __future__ import annotations

from typing import Any

from services.utils import to_float, estimate_payoff_months


# Extra payment scenarios to simulate (in rubles per month)
SCENARIO_AMOUNTS = (1_000, 2_000, 5_000, 10_000)


def daily_interest_cost(balance: float, rate: float) -> float:
    """How many rubles of interest accrue per day on this debt."""
    if balance <= 0 or rate <= 0:
        return 0.0
    return (rate / 100.0 / 365.0) * balance


def _baseline_total_paid(balance: float, rate: float, monthly_payment: float) -> float | None:
    """Total amount paid over the life of the loan at minimum payment."""
    months = estimate_payoff_months(balance, rate, monthly_payment)
    if months is None:
        return None
    return monthly_payment * months


def simulate_scenario(obligation: dict, extra: float) -> dict | None:
    """Simulate adding `extra` rubles to monthly payment.

    Returns dict with savings vs baseline, or None if scenario doesn't help.
    """
    balance = to_float(obligation.get("balance"))
    rate = to_float(obligation.get("rate"))
    mp = to_float(obligation.get("monthly_payment"))

    if balance <= 0 or mp <= 0:
        return None

    baseline_months = estimate_payoff_months(balance, rate, mp)
    new_months = estimate_payoff_months(balance, rate, mp + extra)

    if baseline_months is None or new_months is None:
        return None

    baseline_total = mp * baseline_months
    new_total = (mp + extra) * new_months

    savings = baseline_total - new_total
    if savings <= 0:
        return None

    return {
        "extra": extra,
        "new_payment": mp + extra,
        "baseline_months": baseline_months,
        "new_months": new_months,
        "months_saved": baseline_months - new_months,
        "savings": savings,
    }


def build_insight(obligation: dict) -> dict | None:
    """Build a single loss-aversion insight for one obligation.

    Picks the best scenario (highest savings) from SCENARIO_AMOUNTS.
    """
    name = str(obligation.get("name", "Долг"))
    balance = to_float(obligation.get("balance"))
    rate = to_float(obligation.get("rate"))
    mp = to_float(obligation.get("monthly_payment"))

    if balance <= 0 or mp <= 0:
        return None

    best = None
    for extra in SCENARIO_AMOUNTS:
        sc = simulate_scenario(obligation, extra)
        if sc is None:
            continue
        if best is None or sc["savings"] > best["savings"]:
            best = sc

    if best is None:
        return None

    daily = daily_interest_cost(balance, rate)

    return {
        "obligation_id": obligation.get("id"),
        "name": name,
        "rate": rate,
        "balance": balance,
        "monthly_payment": mp,
        "daily_cost": daily,
        "extra": best["extra"],
        "new_payment": best["new_payment"],
        "months_saved": best["months_saved"],
        "savings": best["savings"],
        "title": f"Ты теряешь {int(best['savings']):,} ₽ на «{name}»".replace(",", "\u202f"),
        "action": f"Добавь +{int(best['extra']):,} ₽/мес — закроешь на {best['months_saved']} мес. раньше".replace(",", "\u202f"),
    }


def build_insights(obligations: list[dict], top_n: int = 3) -> list[dict]:
    """Build top-N insights across all obligations, sorted by savings (largest first)."""
    insights = []
    for ob in obligations or []:
        ins = build_insight(ob)
        if ins is not None:
            insights.append(ins)

    insights.sort(key=lambda x: x["savings"], reverse=True)
    return insights[:top_n]
