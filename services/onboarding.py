from datetime import date

from repositories.categories_repo import ensure_category
from repositories.transactions_repo import add_transaction
from repositories.obligations_repo import add_obligation
from repositories.settings_repo import bulk_set_settings
from services.tax import calc_monthly_net_income
from services.debt_priority import rank_obligations, classify_obligation


STRATEGIES = {
    "aggressive": {"life_pct": 45, "prepayment_pct": 40, "savings_pct": 15},
    "balanced": {"life_pct": 60, "prepayment_pct": 25, "savings_pct": 15},
    "soft": {"life_pct": 70, "prepayment_pct": 10, "savings_pct": 20},
}


OBLIGATION_CATEGORY_BY_TYPE = {
    "mortgage": "Ипотека",
    "loan": "Кредит",
    "credit_card": "Кредитная карта",
    "installment": "Рассрочка",
    "car_loan": "Автокредит",
    "other": "Долг",
}


def _create_income_transactions(today: str, incomes: list, user_id: int):
    for item in incomes:
        if float(item["amount"]) <= 0:
            continue

        category_id = ensure_category(item["category_name"], "income", user_id)
        add_transaction(
            tx_date=today,
            name=item["name"],
            amount=float(item["amount"]),
            kind="income",
            category_id=category_id,
            user_id=user_id,
            is_fixed=False,
            note=item.get("note", "")
        )


def _create_fixed_expense_transactions(today: str, expenses: list, user_id: int):
    for item in expenses:
        if float(item["amount"]) <= 0:
            continue

        category_id = ensure_category(
            item["category_name"],
            "expense",
            user_id,
            expense_scope="fixed",
            is_fixed_default=True
        )
        add_transaction(
            tx_date=today,
            name=item["name"],
            amount=float(item["amount"]),
            kind="expense",
            category_id=category_id,
            user_id=user_id,
            is_fixed=True,
            note=item.get("note", "")
        )



def _create_variable_mandatory_transactions(today: str, expenses: list, user_id: int):
    for item in expenses:
        if float(item["amount"]) <= 0:
            continue

        category_id = ensure_category(
            item["category_name"],
            "expense",
            user_id,
            expense_scope="variable_mandatory",
            is_fixed_default=False
        )
        add_transaction(
            tx_date=today,
            name=item["name"],
            amount=float(item["amount"]),
            kind="expense",
            category_id=category_id,
            user_id=user_id,
            is_fixed=False,
            note=item.get("note", "")
        )



def _create_obligations(obligations: list, user_id: int):
    for item in obligations:
        if float(item["monthly_payment"]) <= 0:
            continue

        classification = classify_obligation(item)

        add_obligation(
            name=item["name"],
            obligation_type=item["obligation_type"],
            rate=float(item.get("rate", 0) or 0),
            balance=float(item.get("balance", 0) or 0),
            monthly_payment=float(item["monthly_payment"]),
            priority=int(classification["priority"]),
            user_id=user_id,
            note=item.get("note", ""),
            priority_score=float(classification["priority_score"]),
            recommended_action=classification["recommended_action"],
            recommendation_reason=classification.get("recommendation_reason"),
            prepayment_allowed=bool(item.get("prepayment_allowed", True)),
            manual_prepayment_mode=item.get("manual_prepayment_mode", "auto"),
            prepayment_order=item.get("prepayment_order"),
            exclude_from_prepayment=bool(item.get("exclude_from_prepayment", False)),
        )


def _build_income_transactions(payload: dict) -> tuple[list, float, float, float]:
    """Build income transactions storing NET (after-tax) amounts.

    Returns (income_transactions, taxable_monthly, non_taxable_monthly, annual_threshold).
    Each transaction's 'amount' is already net-of-tax so that downstream
    calculations (free cashflow, daily limit) work from real money on hand.
    """
    income = payload["income"]
    salary_gross = float(income.get("salary_gross", 0) or 0)
    benefits = float(income.get("benefits", 0) or 0)
    other_regular_income = float(income.get("other_regular_income", 0) or 0)
    bonuses = float(income.get("bonuses", 0) or 0)
    annual_threshold = float(income.get("annual_threshold", 5_000_000) or 5_000_000)

    taxable_monthly = 0.0
    non_taxable_monthly = 0.0
    raw_items = []  # (name, gross_amount, is_taxable, category_name)

    def collect(name, amount, taxable, category_name):
        nonlocal taxable_monthly, non_taxable_monthly
        amount = float(amount)
        if amount <= 0:
            return
        if taxable:
            taxable_monthly += amount
        else:
            non_taxable_monthly += amount
        raw_items.append((name, amount, taxable, category_name))

    collect("Зарплата", salary_gross, bool(income.get("salary_taxable", True)), "Зарплата")
    collect("Пособие", benefits, bool(income.get("benefits_taxable", False)), "Пособие")
    collect("Другой регулярный доход", other_regular_income, bool(income.get("other_regular_taxable", False)), "Другой доход")
    collect("Премия", bonuses, bool(income.get("bonuses_taxable", True)), "Премия")

    # Compute effective tax rate from progressive NDFL and convert each
    # taxable income line to its net value so the DB always stores net.
    effective_tax_rate = 0.0
    if taxable_monthly > 0:
        tax_result = calc_monthly_net_income(
            monthly_taxable_income=taxable_monthly,
            monthly_non_taxable_income=0,
            annual_threshold=annual_threshold,
        )
        effective_tax_rate = tax_result["tax_monthly"] / taxable_monthly

    income_transactions = []
    for name, gross, is_taxable, cat_name in raw_items:
        net_amount = gross * (1 - effective_tax_rate) if is_taxable else gross
        income_transactions.append({
            "name": name,
            "amount": round(net_amount, 2),
            "category_name": cat_name,
            "note": "Создано onboarding wizard (net после НДФЛ)" if is_taxable else "Создано onboarding wizard",
        })

    return income_transactions, taxable_monthly, non_taxable_monthly, annual_threshold


def build_onboarding_result(payload: dict):
    income_transactions, taxable_monthly, non_taxable_monthly, annual_threshold = \
        _build_income_transactions(payload)

    tax_result = calc_monthly_net_income(
        monthly_taxable_income=taxable_monthly,
        monthly_non_taxable_income=non_taxable_monthly,
        annual_threshold=annual_threshold,
    )

    fixed_expenses_total = sum(float(x["amount"]) for x in payload["fixed_expenses"])
    variable_mandatory_total = sum(float(x["amount"]) for x in payload["variable_expenses"])
    mandatory_total = fixed_expenses_total + variable_mandatory_total

    strategy = STRATEGIES[payload["strategy"]]
    net_income = tax_result["net_total_monthly"]
    free_cashflow = max(net_income - mandatory_total, 0)

    life_pct = strategy["life_pct"] / 100.0
    prepayment_pct = strategy["prepayment_pct"] / 100.0
    savings_pct = strategy["savings_pct"] / 100.0

    life_budget = free_cashflow * life_pct
    recommended_prepayment = free_cashflow * prepayment_pct
    recommended_savings = free_cashflow * savings_pct

    total_expense_plan = mandatory_total + life_budget
    balance_after_plan = net_income - total_expense_plan - recommended_prepayment - recommended_savings

    ranked_obligations = rank_obligations(payload.get("obligations", []))

    return {
        "net_income": round(net_income, 2),
        "tax_monthly": round(tax_result["tax_monthly"], 2),
        "fixed_expenses_total": round(fixed_expenses_total, 2),
        "variable_mandatory_total": round(variable_mandatory_total, 2),
        "mandatory_total": round(mandatory_total, 2),
        "free_cashflow": round(free_cashflow, 2),
        "life_budget": round(life_budget, 2),
        "total_expense": round(total_expense_plan, 2),
        "balance_after_plan": round(balance_after_plan, 2),
        "recommended_prepayment": round(recommended_prepayment, 2),
        "recommended_savings": round(recommended_savings, 2),
        "strategy_life_pct": strategy["life_pct"],
        "strategy_prepayment_pct": strategy["prepayment_pct"],
        "strategy_savings_pct": strategy["savings_pct"],
        "income_transactions": income_transactions,
        "ranked_obligations": ranked_obligations,
    }



def persist_onboarding(payload: dict, user_id: int):
    today = date.today().isoformat()
    result = build_onboarding_result(payload)

    _create_income_transactions(today, result["income_transactions"], user_id)
    _create_fixed_expense_transactions(today, payload["fixed_expenses"], user_id)
    _create_variable_mandatory_transactions(today, payload["variable_expenses"], user_id)
    _create_obligations(payload["obligations"], user_id)

    bulk_set_settings({
        "strategy_name": payload["strategy"],
        "strategy_life_pct": result["strategy_life_pct"],
        "strategy_prepayment_pct": result["strategy_prepayment_pct"],
        "strategy_savings_pct": result["strategy_savings_pct"],
        "default_life_budget": result["life_budget"],
        "tax_annual_threshold": payload["income"].get("annual_threshold", 5_000_000),
        "onboarding_completed": "true",
    }, user_id=user_id)

    return result
