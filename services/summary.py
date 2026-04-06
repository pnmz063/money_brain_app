import calendar
from datetime import date
import pandas as pd

from repositories.transactions_repo import read_transactions
from repositories.obligations_repo import read_obligations
from repositories.settings_repo import get_setting
from services.prepayment import allocate_prepayment
from services.debt_priority import classify_obligation, action_label
from services.utils import to_float, estimate_payoff_months


def month_bounds(any_day: date):
    start = any_day.replace(day=1)
    end = any_day.replace(day=calendar.monthrange(any_day.year, any_day.month)[1])
    return start, end


def monthly_summary(selected_day: date, user_id: int):
    start, end = month_bounds(selected_day)
    df = read_transactions(start, end, user_id)
    obligations = read_obligations(user_id)

    today = date.today()

    if df.empty:
        income_total = 0.0
        expense_total = 0.0
        prepayment_total = 0.0
        savings_total = 0.0
        fixed_expense_total = 0.0
        variable_mandatory_total = 0.0
        variable_life_total = 0.0
        spent_today = 0.0
    else:
        income_total = df.loc[df["kind"] == "income", "amount"].sum()
        expense_total = df.loc[df["kind"] == "expense", "amount"].sum()
        prepayment_total = df.loc[df["kind"] == "prepayment", "amount"].sum()
        savings_total = df.loc[df["kind"] == "savings", "amount"].sum()

        expense_df = df[df["kind"] == "expense"].copy()
        fixed_expense_total = expense_df.loc[expense_df["is_fixed"] == True, "amount"].sum()  # noqa: E712
        variable_mandatory_total = expense_df.loc[expense_df["expense_scope"] == "variable_mandatory", "amount"].sum()
        variable_life_total = expense_df.loc[expense_df["expense_scope"] == "variable_life", "amount"].sum()

        today_mask = df["tx_date"] == today.isoformat()
        today_life = df[(today_mask) & (df["kind"] == "expense") & (df["expense_scope"] == "variable_life")]
        spent_today = float(today_life["amount"].sum()) if not today_life.empty else 0.0

    mandatory_total = fixed_expense_total + variable_mandatory_total
    free_cash_flow = max(income_total - mandatory_total, 0)

    life_pct = float(get_setting("strategy_life_pct", user_id, "60")) / 100.0
    prepayment_pct = float(get_setting("strategy_prepayment_pct", user_id, "25")) / 100.0
    savings_pct = float(get_setting("strategy_savings_pct", user_id, "15")) / 100.0

    recommended_life_budget = free_cash_flow * life_pct
    recommended_prepayment = free_cash_flow * prepayment_pct
    recommended_savings = free_cash_flow * savings_pct

    life_budget = recommended_life_budget
    life_budget_left = max(life_budget - variable_life_total, 0)

    remaining_days = max((end - today).days + 1, 1) if today <= end else 0
    daily_limit = life_budget_left / remaining_days if remaining_days > 0 else 0

    obligation_records = obligations.to_dict("records") if not obligations.empty else []
    prepayment_allocations = allocate_prepayment(obligation_records, recommended_prepayment)

    prepayment_target = None
    for item in prepayment_allocations:
        if item["allocated_prepayment"] > 0:
            prepayment_target = {
                **item,
                "total_payment": item["monthly_payment"] + item["allocated_prepayment"],
            }
            break

    priority_debts = []
    total_debt = 0.0
    total_monthly_payments = 0.0
    total_interest = 0.0
    max_payoff_months = 0
    for item in obligation_records:
        classified = classify_obligation(item)
        merged = {**item, **classified}
        merged["recommended_action"] = action_label(merged.get("recommended_action", "minimum_only"))
        priority_debts.append(merged)

        bal = to_float(item.get("balance", 0))
        mp = to_float(item.get("monthly_payment", 0))
        total_debt += bal
        total_monthly_payments += mp
        total_interest += to_float(classified.get("total_interest", 0))
        pm = classified.get("payoff_months")
        if pm is not None and pm > max_payoff_months:
            max_payoff_months = pm

    strategy_name = get_setting("strategy_name", user_id, "balanced")

    def _r(v):
        return round(float(v), 2)

    return {
        "df": df,
        "income_total": _r(income_total),
        "expense_total": _r(expense_total),
        "prepayment_total": _r(prepayment_total),
        "savings_total": _r(savings_total),
        "fixed_expense_total": _r(fixed_expense_total),
        "variable_mandatory_total": _r(variable_mandatory_total),
        "variable_life_total": _r(variable_life_total),
        "mandatory_total": _r(mandatory_total),
        "free_cash_flow": _r(free_cash_flow),
        "life_budget": _r(life_budget),
        "life_budget_left": _r(life_budget_left),
        "recommended_prepayment": _r(recommended_prepayment),
        "recommended_savings": _r(recommended_savings),
        "daily_limit": _r(daily_limit),
        "spent_today": _r(spent_today),
        "remaining_days": remaining_days,
        "prepayment_target": prepayment_target,
        "prepayment_allocations": prepayment_allocations,
        "priority_debts": priority_debts,
        "strategy_label": strategy_name.capitalize(),
        "strategy_life_pct": life_pct * 100,
        "strategy_prepayment_pct": prepayment_pct * 100,
        "strategy_savings_pct": savings_pct * 100,
        "total_debt": _r(total_debt),
        "total_monthly_payments": _r(total_monthly_payments),
        "total_interest": _r(total_interest),
        "max_payoff_months": max_payoff_months,
    }


def fmt_rub(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v == int(v):
        return f"{int(v):,} \u20BD".replace(",", "\u202F")
    return f"{v:,.2f} \u20BD".replace(",", "\u202F")
