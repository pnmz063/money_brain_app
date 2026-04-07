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

# Temperature thresholds — what makes a debt "expensive" right now
RATE_HOT = 20.0   # >= 20% — горящий, дорогой
RATE_WARM = 12.0  # 12–20% — средний
# < 12% — дешёвый


def temperature(rate: float, obligation_type: str | None = None) -> str:
    """Classify debt by current cost.

    Returns one of: 'hot', 'warm', 'cold', 'mortgage'.
    Mortgage is special — even at higher rates we don't put it in 'hot' bucket
    because the priority logic for housing loans is different.
    """
    if obligation_type == "mortgage":
        return "mortgage"
    if rate >= RATE_HOT:
        return "hot"
    if rate >= RATE_WARM:
        return "warm"
    return "cold"


TEMPERATURE_LABELS = {
    "hot": ("🔴", "Дорогой долг", "Гасить в первую очередь"),
    "warm": ("🟡", "Средний", "После дорогих долгов"),
    "cold": ("🟢", "Дешёвый", "Гасить по графику"),
    "mortgage": ("🏠", "Ипотека", "Обычно гасится по графику"),
}


def cost_per_100k_per_month(rate: float) -> float:
    """Normalised cost: how many ₽/month interest accrues per 100 000 ₽ of debt.

    This is the ONLY honest way to compare debts of different size and term.
    Formula: (rate / 100 / 12) * 100_000 = rate * 1000 / 12
    """
    if rate <= 0:
        return 0.0
    return rate * 1000.0 / 12.0


def cost_of_inaction_year(obligations: list[dict], rate_threshold: float = RATE_WARM) -> dict:
    """Honest «cost of inaction» — interest on EXPENSIVE debts over the next 12 months only.

    We deliberately exclude mortgages and cheap loans here. The «total interest over
    30 years» framing is misleading and panic-inducing for housing loans.

    Returns dict with total interest for next year, breakdown, and biggest contributor.
    """
    total = 0.0
    breakdown = []
    for ob in obligations or []:
        rate = to_float(ob.get("rate"))
        balance = to_float(ob.get("balance"))
        if rate < rate_threshold or balance <= 0:
            continue
        if ob.get("obligation_type") == "mortgage":
            continue
        # Approximate: interest accrued on current balance over 12 months
        # (not exact for amortizing loans but close enough for an order-of-magnitude framing)
        year_interest = balance * (rate / 100.0)
        total += year_interest
        breakdown.append({
            "name": str(ob.get("name", "Долг")),
            "rate": rate,
            "year_interest": year_interest,
        })
    breakdown.sort(key=lambda x: x["year_interest"], reverse=True)
    return {
        "total_year_interest": total,
        "breakdown": breakdown,
        "biggest": breakdown[0] if breakdown else None,
    }


def most_expensive_debt(obligations: list[dict]) -> dict | None:
    """Return the obligation with highest current rate (the «truly worst» debt)."""
    candidates = []
    for ob in obligations or []:
        balance = to_float(ob.get("balance"))
        rate = to_float(ob.get("rate"))
        if balance <= 0 or rate <= 0:
            continue
        candidates.append((rate, ob))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    rate, ob = candidates[0]

    # Compare to cheapest debt for the «in N times more expensive» framing
    cheapest_rate = min(c[0] for c in candidates)
    multiplier = rate / cheapest_rate if cheapest_rate > 0 else None

    return {
        "obligation": ob,
        "name": str(ob.get("name", "Долг")),
        "rate": rate,
        "balance": to_float(ob.get("balance")),
        "monthly_payment": to_float(ob.get("monthly_payment")),
        "cost_per_100k": cost_per_100k_per_month(rate),
        "multiplier_vs_cheapest": multiplier,
        "cheapest_rate": cheapest_rate,
    }


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
    """Build a per-obligation insight focused on CURRENT cost (rate, cost per 100k),
    not on multi-decade total interest.

    Picks the best «what if +X» scenario for the action hint.
    """
    name = str(obligation.get("name", "Долг"))
    balance = to_float(obligation.get("balance"))
    rate = to_float(obligation.get("rate"))
    mp = to_float(obligation.get("monthly_payment"))
    obligation_type = obligation.get("obligation_type")

    if balance <= 0 or mp <= 0:
        return None

    best = None
    for extra in SCENARIO_AMOUNTS:
        sc = simulate_scenario(obligation, extra)
        if sc is None:
            continue
        if best is None or sc["savings"] > best["savings"]:
            best = sc

    daily = daily_interest_cost(balance, rate)
    temp = temperature(rate, obligation_type)
    icon, temp_label, temp_hint = TEMPERATURE_LABELS[temp]
    per_100k = cost_per_100k_per_month(rate)

    insight = {
        "obligation_id": obligation.get("id"),
        "name": name,
        "rate": rate,
        "balance": balance,
        "monthly_payment": mp,
        "daily_cost": daily,
        "temperature": temp,
        "temp_icon": icon,
        "temp_label": temp_label,
        "temp_hint": temp_hint,
        "cost_per_100k": per_100k,
        "obligation_type": obligation_type,
    }

    if best is not None:
        insight.update({
            "extra": best["extra"],
            "new_payment": best["new_payment"],
            "months_saved": best["months_saved"],
            "savings": best["savings"],
            "action": f"Добавь +{int(best['extra']):,} ₽/мес — закроешь на {best['months_saved']} мес. раньше".replace(",", "\u202f"),
        })
    else:
        insight.update({
            "extra": 0, "new_payment": mp, "months_saved": 0, "savings": 0.0, "action": "",
        })

    # Honest title — depends on temperature, never says «теряешь N миллионов» on a mortgage
    if temp == "mortgage":
        insight["title"] = f"🏠 {name} — дешёвый долг ({rate:.1f}%)"
        insight["subtitle"] = "Обычно гасится по графику. Сначала закрой дорогие кредиты."
    elif temp == "hot":
        insight["title"] = f"🔴 {name} — самый дорогой тип долга"
        insight["subtitle"] = f"Ставка {rate:.1f}% — каждый месяц набегает {int(per_100k):,} ₽ на каждые 100 000 ₽ остатка".replace(",", "\u202f")
    elif temp == "warm":
        insight["title"] = f"🟡 {name} — средний по дороговизне"
        insight["subtitle"] = f"Ставка {rate:.1f}% — {int(per_100k):,} ₽/мес на 100 000 ₽".replace(",", "\u202f")
    else:
        insight["title"] = f"🟢 {name} — дешёвый долг"
        insight["subtitle"] = f"Ставка {rate:.1f}% — всего {int(per_100k):,} ₽/мес на 100 000 ₽".replace(",", "\u202f")

    return insight


def build_insights(obligations: list[dict], top_n: int = 3) -> list[dict]:
    """Build top-N insights across all obligations, sorted by RATE (highest first).

    Sorting by rate (not by savings) is the key product fix: it prevents
    a long, low-rate mortgage from outranking an expensive credit card.
    """
    insights = []
    for ob in obligations or []:
        ins = build_insight(ob)
        if ins is not None:
            insights.append(ins)

    insights.sort(key=lambda x: x["rate"], reverse=True)
    return insights[:top_n]
