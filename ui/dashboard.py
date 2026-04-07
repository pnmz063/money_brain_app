from __future__ import annotations

from datetime import date
from dateutil.relativedelta import relativedelta
import streamlit as st

from db.migrations import init_db, seed_defaults_for_user
from repositories.admin_repo import reset_user_data
from repositories.settings_repo import get_setting, bulk_set_settings
from repositories.transactions_repo import add_transaction, delete_transaction
from repositories.obligations_repo import read_obligations, add_obligation, disable_obligation
from repositories.categories_repo import read_categories, add_category, disable_category, ensure_category
from services.summary import monthly_summary, fmt_rub
from services.debt_priority import classify_obligation, action_label
from services.utils import to_float as _to_float
from services.onboarding import STRATEGIES
from services.insights import (
    build_insights,
    most_expensive_debt,
    cost_of_inaction_year,
    cost_per_100k_per_month,
    simulate_scenario,
)
from services.optimizer import build_optimal_plan


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


def _fmt_payoff(months: int | None) -> str:
    if months is None:
        return "не погасится"
    if months == 0:
        return "—"
    years = months // 12
    rem = months % 12
    if years > 0:
        return f"{years} г. {rem} мес."
    return f"{months} мес."


def _render_plan_tab(summary: dict, user_id: int):
    """Render the «План» tab — honest debt analysis + plan builder.

    Key product principle: rank by RATE, not by total interest.
    Total interest is misleading for long mortgages.
    """
    obligations_records = [
        {
            "id": d.get("id"),
            "name": d.get("name"),
            "balance": d.get("balance"),
            "rate": d.get("rate"),
            "monthly_payment": d.get("monthly_payment"),
            "obligation_type": d.get("obligation_type"),
        }
        for d in summary.get("priority_debts", [])
    ]

    if not obligations_records:
        st.info("Добавь обязательства — и я покажу, какой долг самый дорогой и что с ним делать.")
        return

    # ---- HERO: самый дорогой долг ----
    worst = most_expensive_debt(obligations_records)
    if worst is not None:
        with st.container(border=True):
            st.markdown(f"### 🔴 Самый дорогой долг — {worst['name']}")
            multiplier = worst.get("multiplier_vs_cheapest")
            if multiplier and multiplier >= 1.5:
                st.markdown(
                    f"Ставка **{worst['rate']:.1f}%** — каждый месяц набегает "
                    f"**{int(worst['cost_per_100k']):,} ₽** процентов на каждые 100 000 ₽ остатка. "
                    f"Это в **{multiplier:.1f} раза** дороже самого дешёвого твоего долга.".replace(",", "\u202f")
                )
            else:
                st.markdown(
                    f"Ставка **{worst['rate']:.1f}%** — каждый месяц набегает "
                    f"**{int(worst['cost_per_100k']):,} ₽** процентов на каждые 100 000 ₽ остатка.".replace(",", "\u202f")
                )
            st.caption("Гасить его в первую очередь — даёт максимальный эффект на каждый рубль досрочки.")

    # ---- SUMMARY-полоса ----
    recommended_prepayment = summary.get("recommended_prepayment", 0.0)
    inaction = cost_of_inaction_year(obligations_records)

    col1, col2, col3 = st.columns(3)
    col1.metric("Свободно на досрочку", f"{fmt_rub(recommended_prepayment)}/мес")
    col2.metric(
        "Самый дорогой",
        worst["name"] if worst else "—",
        delta=f"{worst['rate']:.1f}%" if worst else None,
        delta_color="off",
    )
    col3.metric(
        "Дорогие долги съедят за год",
        fmt_rub(round(inaction["total_year_interest"], 0)),
        help="Сколько процентов набежит за следующие 12 месяцев на твоих кредитах и кредитках (без ипотеки).",
    )

    st.divider()

    # ---- ПЛАН (теперь сразу под hero) ----
    _render_plan_builder(obligations_records, recommended_prepayment)

    st.divider()

    # ---- Карточки долгов: отсортированы по ставке ----
    st.subheader("Гаси в этом порядке")
    st.caption("Долги отсортированы от самого дорогого к самому дешёвому. Сначала закрывай красные.")

    insights = build_insights(obligations_records, top_n=10)

    # Дефолт для досрочки в карточках — берём из плана пользователя.
    # Если по плану 0 (нет свободных), даём минимальный дефолт 1000, чтобы было что показать.
    default_extra = max(int(round(recommended_prepayment)), 1000)

    for i, ins in enumerate(insights, 1):
        with st.container(border=True):
            badge_col, title_col = st.columns([1, 9])
            badge_col.markdown(f"### #{i}")
            title_col.markdown(f"### {ins['title']}")
            title_col.caption(ins["subtitle"])

            mcol1, mcol2, mcol3 = st.columns(3)
            mcol1.metric("Ставка", f"{ins['rate']:.1f}%")
            mcol2.metric(
                "Цена 100к/мес",
                fmt_rub(int(ins["cost_per_100k"])),
                help="Сколько процентов набегает за месяц на каждые 100 000 ₽ остатка. Сравнимо между долгами.",
            )
            mcol3.metric("Текущий платёж", fmt_rub(ins["monthly_payment"]))

            if ins.get("action") and ins["temperature"] != "mortgage":
                st.caption(f"💡 {ins['action']}")
            elif ins["temperature"] == "mortgage":
                st.caption("💡 Сначала закрой дорогие кредиты, потом думай про досрочку по ипотеке.")

            with st.expander("Подробнее о долге"):
                st.write(f"Остаток: **{fmt_rub(ins['balance'])}**")
                st.write(f"Цена в день (проценты): **{fmt_rub(round(ins['daily_cost'], 2))}**")

                if ins["temperature"] != "mortgage":
                    st.markdown("**Что будет, если добавить досрочку именно в этот долг?**")
                    extra = st.number_input(
                        "Сколько ₽/мес добавишь к платежу",
                        min_value=0,
                        max_value=1_000_000,
                        value=default_extra,
                        step=1000,
                        key=f"extra_{ins.get('obligation_id', i)}",
                        help=(
                            "По умолчанию подставлена сумма, которую твой план выделяет "
                            "на досрочку в месяц. Можешь задать своё значение."
                        ),
                    )
                    if extra > 0:
                        sc = simulate_scenario(
                            {
                                "balance": ins["balance"],
                                "rate": ins["rate"],
                                "monthly_payment": ins["monthly_payment"],
                            },
                            extra,
                        )
                        if sc is not None:
                            sc1, sc2 = st.columns(2)
                            sc1.metric(
                                "Сэкономишь процентов",
                                fmt_rub(round(sc["savings"], 0)),
                            )
                            sc2.metric(
                                "Закроешь раньше",
                                f"{sc['months_saved']} мес.",
                                delta=f"вместо {_fmt_payoff(sc['baseline_months'])}",
                                delta_color="off",
                            )
                            st.caption(
                                f"Новый платёж: **{fmt_rub(round(sc['new_payment'], 0))}/мес**, "
                                f"закроется через **{_fmt_payoff(sc['new_months'])}** "
                                f"вместо {_fmt_payoff(sc['baseline_months'])}."
                            )


def _months_to_date(months: int) -> str:
    """Convert months-from-now into a Russian-formatted month/year label."""
    if not months or months <= 0:
        return "—"
    target = date.today() + relativedelta(months=int(months))
    months_ru = ["янв", "фев", "мар", "апр", "май", "июн",
                 "июл", "авг", "сен", "окт", "ноя", "дек"]
    return f"{months_ru[target.month - 1]} {target.year}"


def _render_plan_builder(obligations_records: list[dict], recommended_prepayment: float):
    """Plan optimizer block — now placed right under the hero, with rich output."""
    st.subheader("⚡ Собери оптимальный план")

    if recommended_prepayment <= 0:
        st.warning(
            "Сейчас на досрочку не остаётся свободных денег. "
            "Пересмотри стратегию или расходы — и приложение распределит их по «лавине»."
        )
        return

    st.caption(
        f"По твоей стратегии на досрочку доступно **{fmt_rub(recommended_prepayment)}/мес**. "
        f"Я направлю их в самые дорогие долги — это лавинная стратегия."
    )

    if st.button("⚡ Собрать оптимальный план", type="primary", use_container_width=True):
        st.session_state["_plan_built"] = True

    if not st.session_state.get("_plan_built"):
        return

    plan = build_optimal_plan(obligations_records, recommended_prepayment)
    baseline = plan["baseline"]
    optimal = plan["optimal"]

    # ---- Главный результат: 4 outcome-метрики ----
    interest_saved = round(plan["interest_saved"], 0)
    pct_saved = (
        plan["interest_saved"] / baseline["total_interest"] * 100
        if baseline["total_interest"] > 0 else 0
    )

    with st.container(border=True):
        st.markdown("#### 🎯 Результат плана")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Debt-free",
            _months_to_date(optimal["max_months"]),
            delta=f"−{plan['months_saved']} мес." if plan["months_saved"] > 0 else None,
            help="Когда закроешь все долги по плану. Дельта — на сколько раньше, чем без плана.",
        )
        c2.metric(
            "Сэкономишь",
            fmt_rub(interest_saved),
            delta=f"−{pct_saved:.0f}% переплаты" if pct_saved > 0 else None,
            help="Сколько процентов не уйдёт банкам за весь срок благодаря лавине.",
        )
        c3.metric(
            "Закроешь всё за",
            _fmt_payoff(optimal["max_months"]),
            delta=f"вместо {_fmt_payoff(baseline['max_months'])}",
            delta_color="off",
        )
        first_freed = next(
            (d for d in plan["closing_order"] if d.get("closed_month")),
            None,
        )
        if first_freed:
            c4.metric(
                "Первая разгрузка",
                f"+{fmt_rub(first_freed.get('min_payment', 0))}/мес",
                delta=f"через {_fmt_payoff(first_freed['closed_month'])}",
                delta_color="off",
                help="Сколько освободится в бюджете после закрытия первого долга.",
            )

    # ---- Таймлайн закрытия с освобождаемым cash flow ----
    if plan["closing_order"]:
        st.markdown("#### 📅 Когда какой долг закроется")
        st.caption("После каждого закрытия его минимальный платёж освобождается в семейном бюджете.")

        cumulative_freed = 0.0
        rolling_freed_before = 0.0  # минимумы УЖЕ закрытых долгов до этого
        for i, d in enumerate(plan["closing_order"], 1):
            min_pay = d.get("min_payment", 0)
            # Сколько реально летит в этот долг, пока он — цель лавины
            active_payment = min_pay + recommended_prepayment + rolling_freed_before
            cumulative_freed += min_pay
            with st.container(border=True):
                t1, t2, t3, t4 = st.columns([3, 3, 2, 3])
                t1.markdown(f"**#{i} {d['name']}**")
                t1.caption(f"Ставка {d.get('rate', 0):.1f}%")
                t2.metric(
                    "Платить в месяц",
                    f"{fmt_rub(round(active_payment, 0))}",
                    delta=(
                        f"мин. {fmt_rub(min_pay)} + досрочка {fmt_rub(round(active_payment - min_pay, 0))}"
                    ),
                    delta_color="off",
                    help="Минимальный платёж + вся свободная досрочка + минимумы уже закрытых долгов.",
                )
                t3.metric(
                    "Закроется",
                    _months_to_date(d["closed_month"]),
                    delta=_fmt_payoff(d["closed_month"]),
                    delta_color="off",
                )
                t4.metric(
                    "Потом освободит",
                    f"+{fmt_rub(min_pay)}/мес",
                    delta=f"всего свободно: {fmt_rub(cumulative_freed)}/мес",
                    delta_color="off",
                    help=f"Это +{int(min_pay/30):,} ₽ к ежедневному лимиту трат.".replace(",", "\u202f"),
                )
            rolling_freed_before += min_pay

    # ---- Сравнение baseline vs optimal ----
    st.markdown("#### 📊 С планом vs без плана")

    cmp_col1, cmp_col2 = st.columns(2)
    with cmp_col1:
        with st.container(border=True):
            st.markdown("**Без плана** (только минимумы)")
            st.metric("Переплата", fmt_rub(round(baseline["total_interest"], 0)))
            st.metric("Срок", _fmt_payoff(baseline["max_months"]))
            st.caption(f"Закроешь всё к {_months_to_date(baseline['max_months'])}")
    with cmp_col2:
        with st.container(border=True):
            st.markdown(f"**С планом** (+{fmt_rub(recommended_prepayment)}/мес лавиной)")
            st.metric(
                "Переплата",
                fmt_rub(round(optimal["total_interest"], 0)),
                delta=f"−{fmt_rub(interest_saved)}",
                delta_color="inverse",
            )
            st.metric(
                "Срок",
                _fmt_payoff(optimal["max_months"]),
                delta=f"−{plan['months_saved']} мес.",
                delta_color="inverse",
            )
            st.caption(f"Закроешь всё к {_months_to_date(optimal['max_months'])}")

    # ---- Объяснение «почему именно так» ----
    with st.expander("Почему именно такой план"):
        st.write(
            "**Лавинная стратегия** (debt avalanche): вся свободная сумма идёт в долг "
            "с самой высокой ставкой, пока он не закроется. Потом его минимальный платёж "
            "тоже добавляется к лавине и катится в следующий по дороговизне долг — и так далее."
        )
        st.write(
            "Это математически оптимальный способ: на каждый рубль ты экономишь "
            "максимум процентов. Альтернатива (\"снежный ком\" — гасить мелкие долги первыми) "
            "психологически приятнее, но обходится дороже."
        )
        if first_freed:
            st.write(
                f"В твоём случае первым закрывается **{first_freed['name']}** "
                f"(ставка {first_freed.get('rate', 0):.1f}%) — через "
                f"{_fmt_payoff(first_freed['closed_month'])}. "
                f"После этого +{fmt_rub(first_freed.get('min_payment', 0))}/мес "
                f"автоматически перекатываются в следующий долг."
            )


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

    # ---- Блок долговой нагрузки ----
    if summary["total_debt"] > 0:
        st.markdown("## Долговая нагрузка")

        if summary["has_mortgage"] and summary["consumer_debt"] > 0:
            # Show consumer debts first (actionable), mortgage separately
            st.caption("Кредиты и карты (без ипотеки)")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Долг", fmt_rub(summary["consumer_debt"]))
            d2.metric("Платежи / мес", fmt_rub(summary["consumer_monthly"]))
            cm = summary["consumer_max_months"]
            d3.metric("До погашения", _fmt_payoff(cm) if cm > 0 else "—")
            d4.metric("Переплата", fmt_rub(summary["consumer_interest"]) if summary["consumer_interest"] > 0 else "—")

            st.caption("Итого с ипотекой")
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Общий долг", fmt_rub(summary["total_debt"]))
            e2.metric("Все платежи / мес", fmt_rub(summary["total_monthly_payments"]))
            months = summary["max_payoff_months"]
            e3.metric("До полного погашения", _fmt_payoff(months) if months > 0 else "—")
            e4.metric("Вся переплата", fmt_rub(summary["total_interest"]) if summary["total_interest"] > 0 else "—")
        else:
            # No mortgage or no consumer debts — show single row
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Общий долг", fmt_rub(summary["total_debt"]))
            d2.metric("Платежи / мес", fmt_rub(summary["total_monthly_payments"]))
            months = summary["max_payoff_months"]
            d3.metric("До погашения", _fmt_payoff(months) if months > 0 else "—")
            d4.metric("Переплата", fmt_rub(summary["total_interest"]) if summary["total_interest"] > 0 else "—")

    st.divider()

    # ---- БЛОК 2 — Табы ----
    tab1, tab_plan, tab2, tab3 = st.tabs(["Операции", "План", "Сводка", "Ещё"])

    # -- Таб «План» --
    with tab_plan:
        _render_plan_tab(summary, user_id)

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
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Фиксированные", fmt_rub(summary["fixed_expense_total"]))
        s2.metric("Переменные обязательные", fmt_rub(summary["variable_mandatory_total"]))
        s3.metric("Платежи по долгам", fmt_rub(summary["obligation_payments_total"]))
        s4.metric("На жизнь (факт)", fmt_rub(summary["variable_life_total"]))

        st.markdown("#### Все долговые обязательства")
        if not summary["priority_debts"]:
            st.info("Долговых обязательств нет.")
        else:
            for item in summary["priority_debts"]:
                with st.container(border=True):
                    st.markdown(f"**{item['name']}** — {item['recommended_action']}")
                    payoff = item.get("payoff_months")
                    payoff_str = _fmt_payoff(payoff)
                    ic1, ic2, ic3, ic4 = st.columns(4)
                    ic1.metric("Ставка", f"{_to_float(item['rate']):.1f}%")
                    ic2.metric("Остаток", fmt_rub(_to_float(item.get('balance', 0))))
                    ic3.metric("Платёж/мес", fmt_rub(_to_float(item['monthly_payment'])))
                    ic4.metric("Срок", payoff_str)
                    if item.get("recommendation_reason"):
                        st.caption(item["recommendation_reason"])

    # -- Таб «Ещё» --
    with tab3:
        st.markdown("### Обязательства")
        ob_df = read_obligations(user_id)
        if ob_df.empty:
            st.info("Обязательств нет.")
        else:
            from services.utils import estimate_payoff_months
            show_df = ob_df[["name", "obligation_type", "rate", "balance", "monthly_payment", "recommended_action"]].copy()
            show_df.columns = ["Название", "Тип", "Ставка %", "Остаток", "Платёж/мес", "Действие"]
            show_df["Тип"] = show_df["Тип"].map(lambda x: OBLIGATION_TYPE_LABELS.get(x, x))
            show_df["Действие"] = show_df["Действие"].map(lambda x: action_label(x or "minimum_only"))
            # Add payoff timeline column
            show_df["Срок"] = ob_df.apply(
                lambda r: _fmt_payoff(estimate_payoff_months(
                    _to_float(r["balance"]), _to_float(r["rate"]), _to_float(r["monthly_payment"])
                )), axis=1
            )
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
