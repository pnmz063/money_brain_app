from datetime import date
import streamlit as st

from db.migrations import init_db, seed_defaults_for_user
from repositories.admin_repo import reset_user_data
from repositories.settings_repo import get_setting, bulk_set_settings
from repositories.transactions_repo import add_transaction, delete_transaction
from repositories.obligations_repo import read_obligations, add_obligation, disable_obligation
from repositories.categories_repo import read_categories, add_category, disable_category, ensure_category
from services.summary import monthly_summary, fmt_rub
from services.debt_priority import classify_obligation, action_label, _to_float
from services.onboarding import STRATEGIES


OBLIGATION_TYPE_LABELS = {
    "mortgage": "Ипотека",
    "loan": "Потребительский кредит",
    "credit_card": "Кредитная карта",
    "installment": "Рассрочка",
    "car_loan": "Автокредит",
    "other": "Другое",
}

MANUAL_MODE_LABELS = {
    "auto": "Авто",
    "minimum_only": "Только минимум",
    "skip_prepayment": "Не трогать",
}

STRATEGY_LABELS = {
    "aggressive": "Aggressive",
    "balanced": "Balanced",
    "soft": "Soft",
}


def _apply_strategy(strategy_name: str, user_id: int):
    strategy = STRATEGIES[strategy_name]
    bulk_set_settings(
        {
            "strategy_name": strategy_name,
            "strategy_life_pct": strategy["life_pct"],
            "strategy_prepayment_pct": strategy["prepayment_pct"],
            "strategy_savings_pct": strategy["savings_pct"],
        },
        user_id=user_id,
    )


def _reset_and_return_to_onboarding(user_id: int):
    reset_user_data(user_id)
    seed_defaults_for_user(user_id)
    # Keep auth keys, clear the rest
    keep_keys = {"user_id", "display_name", "username"}
    for key in list(st.session_state.keys()):
        if key not in keep_keys:
            del st.session_state[key]
    st.rerun()


# --- helpers ---

def _get_default_expense_cat_id(user_id: int):
    cats = read_categories("expense", user_id=user_id)
    life = cats[cats["expense_scope"] == "variable_life"]
    if not life.empty:
        return int(life.iloc[0]["id"])
    if not cats.empty:
        return int(cats.iloc[0]["id"])
    return None


def _get_default_income_cat_id(user_id: int):
    cats = read_categories("income", user_id=user_id)
    if not cats.empty:
        return int(cats.iloc[0]["id"])
    return None


# --- main render ---

def render_dashboard(selected_month: date, user_id: int):
    # -- Sidebar --
    with st.sidebar:
        st.header("Период")
        selected_month = st.date_input(
            "Месяц анализа", value=selected_month, format="DD.MM.YYYY"
        )

        st.divider()
        st.header("Стратегия")
        strategy_name = get_setting("strategy_name", user_id, "balanced")
        strategy = st.radio(
            "Текущая",
            options=list(STRATEGY_LABELS.keys()),
            index=list(STRATEGY_LABELS.keys()).index(strategy_name),
            format_func=lambda x: (
                f"{STRATEGY_LABELS[x]} · жизнь {STRATEGIES[x]['life_pct']}%"
                f" · досрочка {STRATEGIES[x]['prepayment_pct']}%"
                f" · накопления {STRATEGIES[x]['savings_pct']}%"
            ),
        )
        if st.button("Применить"):
            _apply_strategy(strategy, user_id)
            st.rerun()

        st.divider()
        with st.expander("Опасная зона"):
            confirm_reset = st.checkbox("Да, стереть все данные")
            if st.button("Сброс", type="secondary", disabled=not confirm_reset):
                _reset_and_return_to_onboarding(user_id)

    summary = monthly_summary(selected_month, user_id)

    # ---- БЛОК 1 — Дневной трекер ----
    st.markdown("## Сегодня")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Лимит на день", fmt_rub(summary["daily_limit"]))
    m2.metric("Потрачено сегодня", fmt_rub(summary["spent_today"]))
    m3.metric("Осталось на месяц", fmt_rub(summary["life_budget_left"]))
    m4.metric("Дней осталось", summary["remaining_days"])

    if summary["daily_limit"] <= 0 < summary["life_budget"]:
        st.warning("Бюджет на жизнь в этом месяце исчерпан.")

    # -- Быстрый ввод расхода --
    with st.form("quick_expense", clear_on_submit=True):
        qc1, qc2, qc3 = st.columns([3, 2, 1])
        with qc1:
            qe_name = st.text_input(
                "Расход", placeholder="Продукты, кофе, такси…", label_visibility="collapsed"
            )
        with qc2:
            qe_amount = st.number_input(
                "₽", min_value=0.0, value=0.0, step=100.0,
                label_visibility="collapsed", key="qe_amt"
            )
        with qc3:
            qe_submit = st.form_submit_button("+ Расход", type="primary")

    if qe_submit and qe_amount > 0:
        cat_id = _get_default_expense_cat_id(user_id)
        if cat_id is None:
            st.error("Нет категорий расходов. Добавь на вкладке «Ещё».")
        else:
            label = qe_name.strip() if qe_name.strip() else "Расход"
            add_transaction(
                date.today().isoformat(), label, float(qe_amount),
                "expense", cat_id, user_id, False, ""
            )
            st.rerun()
    elif qe_submit and qe_amount <= 0:
        st.error("Введи сумму.")

    # -- Приоритетный долг --
    target = summary["prepayment_target"]
    if target:
        with st.container(border=True):
            st.markdown(
                f"**Гасить первым -> {target['name']}**"
                f"  ·  {OBLIGATION_TYPE_LABELS.get(target['obligation_type'], target['obligation_type'])}"
                f"  ·  {target['rate']}%"
            )
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Обязательный платёж", fmt_rub(target["monthly_payment"]))
            p2.metric("Досрочка", fmt_rub(target["allocated_prepayment"]))
            p3.metric("Итого в месяц", fmt_rub(target["total_payment"]))
            p4.metric("Остаток долга", fmt_rub(target["balance"]))

    st.divider()

    # ---- БЛОК 2 — Табы ----
    tab1, tab2, tab3 = st.tabs(["Операции", "Сводка", "Ещё"])

    # -- Таб «Операции» --
    with tab1:
        tx_df = summary["df"]
        if tx_df.empty:
            st.info("За этот месяц операций пока нет.")
        else:
            row_idx = 0
            for tx_date_val, day_group in tx_df.groupby("tx_date", sort=False):
                st.caption(tx_date_val)
                for _, row in day_group.iterrows():
                    kind = row["kind"]
                    amt = _to_float(row["amount"])
                    sign = "+" if kind == "income" else "-"
                    color = "green" if kind == "income" else "red"

                    rc1, rc2, rc3 = st.columns([5, 2, 1])
                    with rc1:
                        cat_label = row.get("category_name") or ""
                        if cat_label and cat_label != row["name"]:
                            st.markdown(f"**{row['name']}** · {cat_label}")
                        else:
                            st.markdown(f"**{row['name']}**")
                    with rc2:
                        st.markdown(f":{color}[{sign}{fmt_rub(amt)}]")
                    with rc3:
                        if st.button("X", key=f"del_{row['id']}_{row_idx}"):
                            delete_transaction(int(row["id"]), user_id)
                            st.rerun()
                    row_idx += 1

        # Быстрый ввод дохода
        with st.expander("Добавить доход"):
            with st.form("quick_income_form", clear_on_submit=True):
                qi_name = st.text_input("Откуда", placeholder="Зарплата, фриланс, возврат…")
                qi_amount = st.number_input("Сумма, ₽", min_value=0.0, value=0.0, step=1000.0, key="qi_amt")
                qi_submit = st.form_submit_button("Добавить доход")

            if qi_submit and qi_amount > 0:
                cat_id = _get_default_income_cat_id(user_id)
                if cat_id is None:
                    st.error("Нет категорий доходов. Добавь на вкладке «Ещё».")
                else:
                    label = qi_name.strip() if qi_name.strip() else "Доход"
                    add_transaction(
                        date.today().isoformat(), label, float(qi_amount),
                        "income", cat_id, user_id, False, ""
                    )
                    st.rerun()

        # Расширенная форма
        with st.expander("Расширенная операция (досрочка, накопления и т.д.)"):
            categories = read_categories(user_id=user_id)
            income_cats = categories[categories["kind"] == "income"]
            expense_cats = categories[categories["kind"] == "expense"]
            transfer_cats = categories[categories["kind"] == "transfer"]

            with st.form("add_tx_form", clear_on_submit=True):
                tx_date = st.date_input("Дата", value=date.today(), format="DD.MM.YYYY")
                tx_kind = st.selectbox(
                    "Тип", ["income", "expense", "prepayment", "savings"],
                    format_func=lambda x: {
                        "income": "Доход", "expense": "Расход",
                        "prepayment": "Досрочка", "savings": "Накопления",
                    }[x],
                )
                if tx_kind == "income":
                    cat_options = income_cats
                elif tx_kind == "expense":
                    cat_options = expense_cats
                else:
                    cat_options = transfer_cats

                if cat_options.empty:
                    st.warning("Нет категорий для этого типа.")
                    submitted = st.form_submit_button("Добавить", disabled=True)
                    category_id = None
                    name = ""
                    amount = 0.0
                    is_fixed = False
                    note = ""
                else:
                    cat_map = {int(r["id"]): r["name"] for _, r in cat_options.iterrows()}
                    category_id = st.selectbox(
                        "Категория", options=list(cat_map.keys()),
                        format_func=lambda x: cat_map.get(x, "—"),
                    )
                    name = st.text_input("Название")
                    amount = st.number_input("Сумма, ₽", min_value=0.0, value=0.0, step=1000.0)
                    is_fixed = st.checkbox("Фиксированный", value=False, disabled=(tx_kind != "expense"))
                    note = st.text_input("Комментарий")
                    submitted = st.form_submit_button("Добавить")

            if submitted and amount > 0 and name and name.strip():
                add_transaction(
                    tx_date.isoformat(), name.strip(), float(amount),
                    tx_kind, int(category_id), user_id, bool(is_fixed), (note or "").strip(),
                )
                st.success("Операция добавлена.")
                st.rerun()

    # -- Таб «Сводка» --
    with tab2:
        st.caption(
            f"Стратегия: {summary['strategy_label']}"
            f" · жизнь {summary['strategy_life_pct']:.0f}%"
            f" · досрочка {summary['strategy_prepayment_pct']:.0f}%"
            f" · накопления {summary['strategy_savings_pct']:.0f}%"
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Доход (net)", fmt_rub(summary["income_total"]))
        c2.metric("Обязательные расходы", fmt_rub(summary["mandatory_total"]))
        c3.metric("Свободный cash flow", fmt_rub(summary["free_cash_flow"]))

        c4, c5, c6 = st.columns(3)
        c4.metric("Бюджет на жизнь", fmt_rub(summary["life_budget"]))
        c5.metric("На досрочку", fmt_rub(summary["recommended_prepayment"]))
        c6.metric("В накопления", fmt_rub(summary["recommended_savings"]))

        st.markdown("#### Структура расходов")
        s1, s2, s3 = st.columns(3)
        s1.metric("Фиксированные", fmt_rub(summary["fixed_expense_total"]))
        s2.metric("Переменные обязательные", fmt_rub(summary["variable_mandatory_total"]))
        s3.metric("На жизнь (факт)", fmt_rub(summary["variable_life_total"]))

        st.markdown("#### Все долговые обязательства")
        if not summary["priority_debts"]:
            st.info("Долговых обязательств нет.")
        else:
            for item in summary["priority_debts"]:
                with st.container(border=True):
                    st.markdown(f"**{item['name']}** — {item['recommended_action']}")
                    st.write(
                        f"Ставка: {item['rate']}%"
                        f" · Платёж: {fmt_rub(item['monthly_payment'])}"
                        f" · Score: {item['priority_score']:.1f}"
                    )
                    if item["recommendation_reason"]:
                        st.caption(item["recommendation_reason"])

    # -- Таб «Ещё» --
    with tab3:
        st.markdown("### Обязательства")
        ob_df = read_obligations(user_id)
        if ob_df.empty:
            st.info("Обязательств нет.")
        else:
            show_df = ob_df[["name", "obligation_type", "rate", "balance", "monthly_payment", "recommended_action"]].copy()
            show_df.columns = ["Название", "Тип", "Ставка %", "Остаток", "Платёж/мес", "Действие"]
            show_df["Тип"] = show_df["Тип"].map(lambda x: OBLIGATION_TYPE_LABELS.get(x, x))
            show_df["Действие"] = show_df["Действие"].map(lambda x: action_label(x or "minimum_only"))
            st.dataframe(show_df, use_container_width=True, hide_index=True)

        with st.expander("Добавить обязательство"):
            with st.form("add_obligation_form", clear_on_submit=True):
                name = st.text_input("Название", placeholder="Кредитная карта Т-Банк")
                obligation_type = st.selectbox(
                    "Тип", options=list(OBLIGATION_TYPE_LABELS.keys()),
                    format_func=lambda x: OBLIGATION_TYPE_LABELS[x],
                )
                rate = st.number_input("Ставка, %", min_value=0.0, value=0.0, step=0.1)
                balance = st.number_input("Остаток, ₽", min_value=0.0, value=0.0, step=10000.0)
                monthly_payment = st.number_input("Платёж, ₽/мес", min_value=0.0, value=0.0, step=1000.0)
                prepayment_allowed = st.checkbox("Досрочка разрешена", value=True)
                manual_mode = st.selectbox(
                    "Режим", options=list(MANUAL_MODE_LABELS.keys()),
                    format_func=lambda x: MANUAL_MODE_LABELS[x],
                )
                note = st.text_input("Комментарий")
                submitted = st.form_submit_button("Добавить")

            if submitted and name and name.strip():
                ranked = classify_obligation({
                    "obligation_type": obligation_type,
                    "rate": float(rate),
                    "balance": float(balance),
                    "monthly_payment": float(monthly_payment),
                    "prepayment_allowed": bool(prepayment_allowed),
                    "manual_prepayment_mode": manual_mode,
                })
                add_obligation(
                    name.strip(), obligation_type, float(rate), float(balance),
                    float(monthly_payment), int(ranked["priority"]),
                    user_id,
                    (note or "").strip(), float(ranked["priority_score"]),
                    ranked["recommended_action"], ranked["recommendation_reason"],
                    bool(prepayment_allowed), manual_mode,
                )
                st.success("Обязательство добавлено.")
                st.rerun()

        if not ob_df.empty:
            with st.expander("Отключить обязательство"):
                ob_options = {
                    int(r["id"]): f"{r['name']} · {fmt_rub(_to_float(r['monthly_payment']))}/мес"
                    for _, r in ob_df.iterrows()
                }
                ob_to_disable = st.selectbox(
                    "Выбери", options=list(ob_options.keys()),
                    format_func=lambda x: ob_options[x],
                )
                if st.button("Отключить", type="secondary"):
                    disable_obligation(int(ob_to_disable), user_id)
                    st.success("Отключено.")
                    st.rerun()

        st.markdown("### Категории")
        cat_df = read_categories(user_id=user_id)
        if not cat_df.empty:
            show_cat = cat_df[["name", "kind", "expense_scope"]].copy()
            show_cat.columns = ["Название", "Тип", "Роль"]
            kind_map = {"income": "Доход", "expense": "Расход", "transfer": "Перемещение"}
            scope_map = {"fixed": "Фикс.", "variable_mandatory": "Обязат.", "variable_life": "На жизнь"}
            show_cat["Тип"] = show_cat["Тип"].map(lambda x: kind_map.get(x, x))
            show_cat["Роль"] = show_cat["Роль"].map(lambda x: scope_map.get(x, "—") if x else "—")
            st.dataframe(show_cat, use_container_width=True, hide_index=True)

        with st.expander("Добавить категорию"):
            with st.form("add_cat_form", clear_on_submit=True):
                cat_name = st.text_input("Название", placeholder="ЖКХ, Марк, Транспорт…")
                cat_kind = st.selectbox(
                    "Тип", ["income", "expense", "transfer"],
                    format_func=lambda x: {"income": "Доход", "expense": "Расход", "transfer": "Перемещения"}[x],
                )
                expense_scope = None
                if cat_kind == "expense":
                    expense_scope = st.selectbox(
                        "Роль", ["variable_life", "fixed", "variable_mandatory", "none"],
                        format_func=lambda x: {
                            "fixed": "Фиксированный обязательный",
                            "variable_mandatory": "Переменный обязательный",
                            "variable_life": "На жизнь",
                            "none": "Без роли",
                        }[x],
                    )
                submitted = st.form_submit_button("Добавить")

            if submitted and cat_name and cat_name.strip():
                try:
                    add_category(
                        cat_name.strip(), cat_kind, user_id,
                        None if expense_scope in (None, "none") else expense_scope,
                        False,
                    )
                    st.success("Категория добавлена.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка: {e}")

        if not cat_df.empty:
            with st.expander("Отключить категорию"):
                cat_options = {
                    int(r["id"]): f"{r['name']} · {r['kind']}"
                    for _, r in cat_df.iterrows()
                }
                cat_to_disable = st.selectbox(
                    "Выбери", options=list(cat_options.keys()),
                    format_func=lambda x: cat_options[x],
                )
                if st.button("Отключить категорию", type="secondary"):
                    disable_category(int(cat_to_disable), user_id)
                    st.success("Отключена.")
                    st.rerun()
