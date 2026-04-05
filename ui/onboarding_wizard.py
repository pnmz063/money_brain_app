import streamlit as st

from services.onboarding import build_onboarding_result, persist_onboarding, STRATEGIES
from services.summary import fmt_rub
from services.debt_priority import action_label


OBLIGATION_TYPE_LABELS = {
    "mortgage": "Ипотека",
    "loan": "Потребительский кредит",
    "credit_card": "Кредитная карта",
    "installment": "Рассрочка",
    "car_loan": "Автокредит",
    "other": "Другое",
}

MANUAL_MODE_LABELS = {
    "auto": "Автоматически решить приоритет",
    "minimum_only": "Платить только минимум",
    "skip_prepayment": "Не гасить досрочно",
}

STRATEGY_LABELS = {
    "aggressive": "Aggressive — сильный фокус на досрочке",
    "balanced": "Balanced — баланс жизни, досрочки и накоплений",
    "soft": "Soft — мягкий режим с большим бюджетом на жизнь",
}


def _init_state():
    if "onboarding_step" not in st.session_state:
        st.session_state.onboarding_step = 1

    if "onboarding_data" not in st.session_state:
        st.session_state.onboarding_data = {
            "income": {
                "salary_gross": 0.0,
                "benefits": 0.0,
                "other_regular_income": 0.0,
                "bonuses": 0.0,
                "salary_taxable": True,
                "benefits_taxable": False,
                "other_regular_taxable": False,
                "bonuses_taxable": True,
                "annual_threshold": 5_000_000,
            },
            "fixed_expenses": [],
            "variable_expenses": [],
            "obligations": [],
            "strategy": "balanced",
        }

    st.session_state.setdefault("saved_mortgages", [])
    st.session_state.setdefault("saved_loans", [])
    st.session_state.setdefault("saved_fixed_items", [])
    st.session_state.setdefault("saved_variable_items", [])


def _go(step: int):
    st.session_state.onboarding_step = step
    st.rerun()


def _income_step():
    data = st.session_state.onboarding_data
    st.subheader("Шаг 1. Доходы")

    with st.form("income_form"):
        salary_gross = st.number_input("Зарплата gross в месяц, ₽", min_value=0.0, value=float(data["income"]["salary_gross"]), step=10000.0)
        benefits = st.number_input("Пособия в месяц, ₽", min_value=0.0, value=float(data["income"]["benefits"]), step=1000.0)
        other_regular_income = st.number_input("Другие регулярные доходы в месяц, ₽", min_value=0.0, value=float(data["income"]["other_regular_income"]), step=1000.0)
        bonuses = st.number_input("Средние премии в месяц, ₽", min_value=0.0, value=float(data["income"]["bonuses"]), step=5000.0)

        st.markdown("**Какие доходы облагаются НДФЛ**")
        salary_taxable = st.checkbox("Зарплата облагается", value=bool(data["income"]["salary_taxable"]))
        benefits_taxable = st.checkbox("Пособия облагаются", value=bool(data["income"]["benefits_taxable"]))
        other_regular_taxable = st.checkbox("Другие регулярные доходы облагаются", value=bool(data["income"]["other_regular_taxable"]))
        bonuses_taxable = st.checkbox("Премии облагаются", value=bool(data["income"]["bonuses_taxable"]))
        annual_threshold = st.number_input("Порог годового дохода для ставки 15%, ₽", min_value=0.0, value=float(data["income"]["annual_threshold"]), step=100000.0)

        submitted = st.form_submit_button("Сохранить и продолжить")

    if submitted:
        data["income"] = {
            "salary_gross": salary_gross,
            "benefits": benefits,
            "other_regular_income": other_regular_income,
            "bonuses": bonuses,
            "salary_taxable": salary_taxable,
            "benefits_taxable": benefits_taxable,
            "other_regular_taxable": other_regular_taxable,
            "bonuses_taxable": bonuses_taxable,
            "annual_threshold": annual_threshold,
        }
        result = build_onboarding_result(data)
        st.success("Доходы сохранены.")
        st.info(f"Оценка чистого дохода: **{fmt_rub(result['net_income'])}** в месяц")
        _go(2)


def _debt_form(form_key: str, default_name: str, default_type: str):
    with st.form(form_key, clear_on_submit=True):
        name = st.text_input("Название", value=default_name)
        obligation_type = st.selectbox("Тип", options=list(OBLIGATION_TYPE_LABELS.keys()), index=list(OBLIGATION_TYPE_LABELS.keys()).index(default_type), format_func=lambda x: OBLIGATION_TYPE_LABELS[x])
        monthly_payment = st.number_input("Платёж, ₽/мес", min_value=0.0, value=0.0, step=1000.0)
        balance = st.number_input("Остаток долга, ₽", min_value=0.0, value=0.0, step=10000.0)
        rate = st.number_input("Ставка, %", min_value=0.0, value=0.0, step=0.1)
        prepayment_allowed = st.checkbox("Досрочка разрешена и удобна", value=True)
        manual_mode = st.selectbox("Режим", options=list(MANUAL_MODE_LABELS.keys()), format_func=lambda x: MANUAL_MODE_LABELS[x])
        note = st.text_input("Комментарий", value="Создано onboarding wizard")
        saved = st.form_submit_button("Сохранить")
    return {
        "saved": saved,
        "item": {
            "name": name.strip(),
            "obligation_type": obligation_type,
            "monthly_payment": float(monthly_payment),
            "balance": float(balance),
            "rate": float(rate),
            "prepayment_allowed": bool(prepayment_allowed),
            "manual_prepayment_mode": manual_mode,
            "note": note.strip(),
        },
    }


def _expense_item_form(form_key: str, default_name: str, save_label: str):
    with st.form(form_key, clear_on_submit=True):
        name = st.text_input("Название статьи", value=default_name)
        amount = st.number_input("Сумма в месяц, ₽", min_value=0.0, value=0.0, step=1000.0)
        save = st.form_submit_button(save_label)
    return save, {"name": name.strip(), "amount": float(amount)}


def _obligations_step():
    data = st.session_state.onboarding_data
    st.subheader("Шаг 2. Обязательные платежи и долги")
    st.caption("Каждая ипотека, кредит и фиксированный платёж добавляются отдельно. В БД они попадут только после финального завершения онбординга.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Добавить ипотеку")
        res = _debt_form("add_mortgage_form", f"Ипотека {len(st.session_state.saved_mortgages) + 1}", "mortgage")
        if res["saved"]:
            item = res["item"]
            if not item["name"] or item["monthly_payment"] <= 0:
                st.error("Укажи название и платёж больше нуля.")
            else:
                st.session_state.saved_mortgages.append(item)
                st.success("Ипотека сохранена в мастер настройки.")
                st.rerun()

    with col2:
        st.markdown("### Добавить кредит")
        res = _debt_form("add_loan_form", f"Кредит {len(st.session_state.saved_loans) + 1}", "loan")
        if res["saved"]:
            item = res["item"]
            if not item["name"] or item["monthly_payment"] <= 0:
                st.error("Укажи название и платёж больше нуля.")
            else:
                st.session_state.saved_loans.append(item)
                st.success("Кредит сохранён в мастер настройки.")
                st.rerun()

    st.markdown("### Сохранённые долговые позиции")
    debts = st.session_state.saved_mortgages + st.session_state.saved_loans
    if not debts:
        st.info("Пока нет сохранённых ипотек или кредитов.")
    else:
        for idx, item in enumerate(debts):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.write(f"**{item['name']}** · {OBLIGATION_TYPE_LABELS.get(item['obligation_type'], item['obligation_type'])} · {fmt_rub(item['monthly_payment'])}/мес · {item['rate']}%")
            with c2:
                if st.button("Удалить", key=f"drop_debt_{idx}"):
                    if idx < len(st.session_state.saved_mortgages):
                        st.session_state.saved_mortgages.pop(idx)
                    else:
                        st.session_state.saved_loans.pop(idx - len(st.session_state.saved_mortgages))
                    st.rerun()

    st.markdown("### Прочие фиксированные обязательные платежи")
    save_fixed, fixed_item = _expense_item_form("add_fixed_item_form", "Например: ЖКХ", "Сохранить фиксированный платёж")
    if save_fixed:
        if not fixed_item["name"] or fixed_item["amount"] <= 0:
            st.error("Укажи название статьи и сумму больше нуля.")
        else:
            st.session_state.saved_fixed_items.append(fixed_item)
            st.success("Фиксированный платёж сохранён в мастер настройки.")
            st.rerun()

    if st.session_state.saved_fixed_items:
        for idx, item in enumerate(st.session_state.saved_fixed_items):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.write(f"**{item['name']}** · {fmt_rub(item['amount'])}/мес")
            with c2:
                if st.button("Удалить", key=f"drop_fix_{idx}"):
                    st.session_state.saved_fixed_items.pop(idx)
                    st.rerun()
    else:
        st.info("Дополнительные фиксированные платежи пока не добавлены.")

    left, right = st.columns(2)
    if left.button("Назад"):
        _go(1)
    if right.button("Сохранить и продолжить", type="primary"):
        obligations = st.session_state.saved_mortgages + st.session_state.saved_loans
        fixed_expenses = []
        for item in obligations:
            fixed_expenses.append(
                {
                    "name": item["name"],
                    "amount": float(item["monthly_payment"]),
                    "category_name": item["name"],
                    "note": "Создано onboarding wizard",
                }
            )
        for item in st.session_state.saved_fixed_items:
            fixed_expenses.append(
                {
                    "name": item["name"],
                    "amount": float(item["amount"]),
                    "category_name": item["name"],
                    "note": "Создано onboarding wizard",
                }
            )
        data["obligations"] = obligations
        data["fixed_expenses"] = fixed_expenses
        result = build_onboarding_result(data)
        st.success("Обязательные платежи сохранены.")
        st.info(f"Обязательных фиксированных расходов: **{fmt_rub(result['fixed_expenses_total'])}**")
        _go(3)


def _variable_expenses_step():
    data = st.session_state.onboarding_data
    st.subheader("Шаг 3. Переменные обязательные расходы")
    st.caption("Никаких дефолтных статей вроде няни или транспорта. Добавляй только то, что реально есть у семьи.")

    save_variable, variable_item = _expense_item_form("add_variable_item_form", "Например: ребёнок", "Сохранить переменный обязательный расход")
    if save_variable:
        if not variable_item["name"] or variable_item["amount"] <= 0:
            st.error("Укажи название статьи и сумму больше нуля.")
        else:
            st.session_state.saved_variable_items.append(variable_item)
            st.success("Переменный обязательный расход сохранён в мастер настройки.")
            st.rerun()

    if st.session_state.saved_variable_items:
        for idx, item in enumerate(st.session_state.saved_variable_items):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.write(f"**{item['name']}** · {fmt_rub(item['amount'])}/мес")
            with c2:
                if st.button("Удалить", key=f"drop_var_{idx}"):
                    st.session_state.saved_variable_items.pop(idx)
                    st.rerun()
    else:
        st.info("Переменные обязательные расходы пока не добавлены.")

    left, right = st.columns(2)
    if left.button("Назад", key="var_back"):
        _go(2)
    if right.button("Сохранить и продолжить", type="primary", key="var_next"):
        data["variable_expenses"] = [
            {
                "name": item["name"],
                "amount": float(item["amount"]),
                "category_name": item["name"],
                "note": "Переменный обязательный расход",
            }
            for item in st.session_state.saved_variable_items
        ]
        result = build_onboarding_result(data)
        st.success("Переменные обязательные расходы сохранены.")
        st.info(f"Переменных обязательных расходов: **{fmt_rub(result['variable_mandatory_total'])}**")
        _go(4)


def _strategy_step():
    data = st.session_state.onboarding_data
    st.subheader("Шаг 4. Стратегия и расчёт комфортного бюджета на жизнь")
    st.caption("Комфорт на жизнь теперь считается автоматически: чистый доход минус обязательные расходы, затем сумма делится по выбранной стратегии.")

    strategy = st.radio(
        "Выбери стратегию",
        options=list(STRATEGY_LABELS.keys()),
        index=list(STRATEGY_LABELS.keys()).index(data.get("strategy", "balanced")),
        format_func=lambda x: STRATEGY_LABELS[x],
    )
    data["strategy"] = strategy

    result = build_onboarding_result(data)
    strategy_meta = STRATEGIES[strategy]

    c1, c2, c3 = st.columns(3)
    c1.metric("Чистый доход", fmt_rub(result["net_income"]))
    c2.metric("Обязательные расходы", fmt_rub(result["mandatory_total"]))
    c3.metric("Свободный cash flow", fmt_rub(result["free_cashflow"]))

    c4, c5, c6 = st.columns(3)
    c4.metric(f"На жизнь ({strategy_meta['life_pct']}%)", fmt_rub(result["life_budget"]))
    c5.metric(f"На досрочку ({strategy_meta['prepayment_pct']}%)", fmt_rub(result["recommended_prepayment"]))
    c6.metric(f"В накопления ({strategy_meta['savings_pct']}%)", fmt_rub(result["recommended_savings"]))

    left, center, right = st.columns(3)
    if left.button("Назад", key="strategy_back"):
        _go(3)
    if center.button("Пересчитать", key="strategy_recalc"):
        st.rerun()
    if right.button("Продолжить", type="primary", key="strategy_next"):
        _go(5)


def _review_step():
    data = st.session_state.onboarding_data
    result = build_onboarding_result(data)

    st.subheader("Финальная проверка")
    st.caption("Здесь пока ещё ничего не записано в базу. Нажми сохранить, и приложение создаст стартовые записи и настройки.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Чистый доход", fmt_rub(result["net_income"]))
    c2.metric("Фиксированные обязательные", fmt_rub(result["fixed_expenses_total"]))
    c3.metric("Переменные обязательные", fmt_rub(result["variable_mandatory_total"]))

    c4, c5, c6 = st.columns(3)
    c4.metric("Свободный cash flow", fmt_rub(result["free_cashflow"]))
    c5.metric("Комфорт на жизнь", fmt_rub(result["life_budget"]))
    c6.metric("Плановый остаток после распределения", fmt_rub(result["balance_after_plan"]))

    c7, c8 = st.columns(2)
    c7.metric("Рекомендованная досрочка", fmt_rub(result["recommended_prepayment"]))
    c8.metric("Рекомендованные накопления", fmt_rub(result["recommended_savings"]))

    st.markdown("### Очередность по долгам")
    if not result["ranked_obligations"]:
        st.info("Долговых обязательств нет.")
    else:
        for item in result["ranked_obligations"]:
            with st.container(border=True):
                st.markdown(f"**{item['name']}** — {action_label(item['recommended_action'])}")
                st.write(f"Ставка: {item['rate']}% · Платёж: {fmt_rub(item['monthly_payment'])}")
                if item.get("recommendation_reason"):
                    st.caption(item["recommendation_reason"])

    left, right = st.columns(2)
    if left.button("Назад", key="review_back"):
        _go(4)
    if right.button("Сохранить и завершить", type="primary", key="review_save"):
        saved = persist_onboarding(data)
        st.success("Онбординг завершён. База заполнена стартовыми данными.")
        st.info(f"Комфортный бюджет на жизнь: **{fmt_rub(saved['life_budget'])}**, рекомендованная досрочка: **{fmt_rub(saved['recommended_prepayment'])}**")
        st.rerun()


def render_onboarding_wizard():
    _init_state()

    st.markdown("## Первичная настройка")
    st.caption("Пройди короткий мастер. После него приложение сразу покажет готовую финансовую картину семьи.")

    progress = {1: 0.2, 2: 0.45, 3: 0.65, 4: 0.85, 5: 1.0}
    st.progress(progress[st.session_state.onboarding_step])

    step = st.session_state.onboarding_step
    if step == 1:
        _income_step()
    elif step == 2:
        _obligations_step()
    elif step == 3:
        _variable_expenses_step()
    elif step == 4:
        _strategy_step()
    elif step == 5:
        _review_step()
