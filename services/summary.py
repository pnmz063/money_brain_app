import calendar
from datetime import date
import pandas as pd

from repositories.transactions_repo import read_transactions
from repositories.obligations_repo import read_obligations
from repositories.settings_repo import get_setting
from services.prepayment import allocate_prepayment
from services.debt_priority import classify_obligation, action_label


def month_bounds(any_day: date):
    start = any_day.replace(day=1)
    end = any_day.replace(day=calendar.monthrange(any_day.year, any_day.month)[1])
    return start, end


def monthly_summary(selected_day: date):
    start, end = month_bounds(selected_day)
    df = read_transactions(start, end)
    obligations = read_obligations()

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
        fixed_expense_total = expense_df.loc[expense_df["is_fixed"] == 1, "amount"].sum()
        variable_mandatory_total = expense_df.loc[expense_df["expense_scope"] == "variable_mandatory", "amount"].sum()
        variable_life_total = expense_df.loc[expense_df["expense_scope"] == "variable_life", "amount"].sum()

        # Потрачено сегодня (расходы «на жизнь» за сегодня)
        today_mask = df["tx_date"] == today.isoformat()
        today_life = df[(today_mask) & (df["kind"] == "expense") & (df["expense_scope"] == "variable_life")]
        spent_today = float(today_life["amount"].sum()) if not today_life.empty else 0.0

    mandatory_total = fixed_expense_total + variable_mandatory_total
    free_cash_flow = max(income_total - mandatory_total, 0)

    life_pct = float(get_setting("strategy_life_pct", "60")) / 100.0
    prepayment_pct = float(get_setting("strategy_prepayment_pct", "25")) / 100.0
    savings_pct = float(get_setting("strategy_savings_pct", "15")) / 100.0

    recommended_life_budget = free_cash_flow * life_pct
    recommended_prepayment = free_cash_flow * prepayment_pct
    recommended_savings = free_cash_flow * savings_pct

    month_balance = income_total - expense_total
    after_transfers_balance = month_balance - prepayment_total - savings_total

    days_in_month = end.day
    remaining_days = max((end - today).days + 1, 1) if (today.year == selected_day.year and today.month == selected_day.month) else days_in_month

    life_budget = recommended_life_budget
    life_spent = variable_life_total
    life_budget_left = life_budget - life_spent
    life_budget_per_day_left = life_budget_left / remaining_days if remaining_days > 0 else 0

    obligations_records = obligations.to_dict("records") if not obligations.empty else []
    prepayment_plan = allocate_prepayment(obligations_records, recommended_prepayment)

    # Найти ОДИН приоритетный долг для досрочного погашения
    from services.prepayment import choose_prepayment_target
    target_ob = choose_prepayment_target(obligations_records)
    prepayment_target = None
    if target_ob:
        alloc = next((p for p in prepayment_plan if p["name"] == target_ob["name"]), None)
        allocated = float(alloc["allocated_prepayment"]) if alloc else 0.0
        mp = float(target_ob["monthly_payment"])
        prepayment_target = {
            "name": target_ob["name"],
            "obligation_type": target_ob.get("obligation_type", ""),
            "rate": float(target_ob.get("rate", 0) or 0),
            "balance": float(target_ob.get("balance", 0) or 0),
            "monthly_payment": mp,
            "allocated_prepayment": allocated,
            "total_payment": mp + allocated,
        }

    strategy_name = get_setting("strategy_name", "balanced")
    strategy_labels = {"aggressive": "Aggressive", "balanced": "Balanced", "soft": "Soft"}

    priority_debts = []
    for ob in obligations_records:
        classified = classify_obligation(ob)
        priority_debts.append({
            "name": ob.get("name", ""),
            "rate": float(ob.get("rate", 0) or 0),
            "monthly_payment": float(ob.get("monthly_payment", 0) or 0),
            "priority_score": float(classified["priority_score"]),
            "recommended_action": action_label(classified["recommended_action"]),
            "recommendation_reason": classified.get("recommendation_reason", ""),
        })
    priority_debts.sort(key=lambda x: (-x["priority_score"],))

    return {
        "start": start,
        "end": end,
        "df": df,
        "obligations": obligations,
        "income_total": float(income_total),
        "expense_total": float(expense_total),
        "fixed_expense_total": float(fixed_expense_total),
        "variable_mandatory_total": float(variable_mandatory_total),
        "variable_life_total": float(variable_life_total),
        "mandatory_total": float(mandatory_total),
        "free_cash_flow": float(free_cash_flow),
        "prepayment_total": float(prepayment_total),
        "savings_total": float(savings_total),
        "month_balance": float(month_balance),
        "after_transfers_balance": float(after_transfers_balance),
        "life_budget": float(life_budget),
        "life_spent": float(life_spent),
        "life_budget_left": float(life_budget_left),
        "life_budget_per_day_left": float(life_budget_per_day_left),
        "remaining_days": int(remaining_days),
        "recommended_prepayment": float(recommended_prepayment),
        "recommended_savings": float(recommended_savings),
        "prepayment_plan": prepayment_plan,
        "strategy_label": strategy_labels.get(strategy_name, strategy_name),
        "strategy_life_pct": life_pct * 100,
        "strategy_prepayment_pct": prepayment_pct * 100,
        "strategy_savings_pct": savings_pct * 100,
        "priority_debts": priority_debts,
        "prepayment_target": prepayment_target,
        "spent_today": float(spent_today),
        "daily_limit": float(life_budget_per_day_left),
    }


def fmt_rub(value: float):
    return f"{value:,.0f} ₽".replace(",", " ")