"""
Comprehensive test suite for the budget MVP application.
Run: python tests.py
"""
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Force a fresh temp DB for every test run
TEST_DB = f"/tmp/budget_test_{os.getpid()}.db"


def _reset_db():
    """Point the app at a fresh in-memory-like temp DB."""
    import db.connection as conn_mod
    conn_mod.DB_PATH = Path(TEST_DB)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    from db.migrations import init_db
    init_db()


# ─────────────────────────────────────────────────────────────────────
#  1. Tax calculations
# ─────────────────────────────────────────────────────────────────────

class TestTax(unittest.TestCase):

    def test_ndfl_13_below_threshold(self):
        from services.tax import calc_progressive_ndfl_13_15
        r = calc_progressive_ndfl_13_15(2_400_000, 5_000_000)
        self.assertAlmostEqual(r["tax_annual"], 2_400_000 * 0.13, places=2)

    def test_ndfl_progressive_above_threshold(self):
        from services.tax import calc_progressive_ndfl_13_15
        r = calc_progressive_ndfl_13_15(6_000_000, 5_000_000)
        expected = 5_000_000 * 0.13 + 1_000_000 * 0.15
        self.assertAlmostEqual(r["tax_annual"], expected, places=2)

    def test_ndfl_zero_income(self):
        from services.tax import calc_progressive_ndfl_13_15
        r = calc_progressive_ndfl_13_15(0)
        self.assertEqual(r["tax_annual"], 0.0)
        self.assertEqual(r["net_taxable_annual"], 0.0)

    def test_ndfl_negative_treated_as_zero(self):
        from services.tax import calc_progressive_ndfl_13_15
        r = calc_progressive_ndfl_13_15(-100_000)
        self.assertEqual(r["tax_annual"], 0.0)

    def test_monthly_net_income(self):
        from services.tax import calc_monthly_net_income
        r = calc_monthly_net_income(200_000, 10_000, 5_000_000)
        self.assertGreater(r["net_total_monthly"], 0)
        self.assertAlmostEqual(r["net_total_monthly"], r["net_taxable_monthly"] + 10_000, places=2)
        self.assertAlmostEqual(r["tax_monthly"], 200_000 * 0.13, places=2)  # under threshold

    def test_monthly_net_non_taxable_only(self):
        from services.tax import calc_monthly_net_income
        r = calc_monthly_net_income(0, 50_000)
        self.assertEqual(r["tax_monthly"], 0.0)
        self.assertEqual(r["net_total_monthly"], 50_000.0)


# ─────────────────────────────────────────────────────────────────────
#  2. Debt priority & classification
# ─────────────────────────────────────────────────────────────────────

class TestDebtPriority(unittest.TestCase):

    def test_credit_card_is_fast(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "credit_card", "rate": 25,
            "balance": 100_000, "monthly_payment": 5000,
            "prepayment_allowed": True, "manual_prepayment_mode": "auto",
        })
        self.assertEqual(r["recommended_action"], "fast")
        self.assertEqual(r["priority"], 1)

    def test_high_rate_loan_is_fast(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "loan", "rate": 22,
            "balance": 200_000, "monthly_payment": 10_000,
            "prepayment_allowed": True, "manual_prepayment_mode": "auto",
        })
        self.assertEqual(r["recommended_action"], "fast")

    def test_medium_rate_loan(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "loan", "rate": 14,
            "balance": 300_000, "monthly_payment": 15_000,
            "prepayment_allowed": True, "manual_prepayment_mode": "auto",
        })
        self.assertEqual(r["recommended_action"], "medium")

    def test_low_rate_installment_is_skip(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "installment", "rate": 0,
            "balance": 50_000, "monthly_payment": 5_000,
            "prepayment_allowed": True, "manual_prepayment_mode": "auto",
        })
        self.assertEqual(r["recommended_action"], "skip")

    def test_skip_prepayment_manual_mode(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "loan", "rate": 18,
            "balance": 500_000, "monthly_payment": 20_000,
            "prepayment_allowed": True, "manual_prepayment_mode": "skip_prepayment",
        })
        self.assertEqual(r["recommended_action"], "skip")
        self.assertEqual(r["priority"], 5)

    def test_minimum_only_manual_mode(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "loan", "rate": 18,
            "balance": 500_000, "monthly_payment": 20_000,
            "prepayment_allowed": True, "manual_prepayment_mode": "minimum_only",
        })
        self.assertEqual(r["recommended_action"], "minimum_only")

    def test_prepayment_not_allowed(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "loan", "rate": 18,
            "balance": 500_000, "monthly_payment": 20_000,
            "prepayment_allowed": False, "manual_prepayment_mode": "auto",
        })
        self.assertEqual(r["recommended_action"], "minimum_only")

    def test_low_rate_is_minimum(self):
        from services.debt_priority import classify_obligation
        r = classify_obligation({
            "obligation_type": "mortgage", "rate": 8,
            "balance": 3_000_000, "monthly_payment": 40_000,
            "prepayment_allowed": True, "manual_prepayment_mode": "auto",
        })
        self.assertEqual(r["recommended_action"], "minimum_only")

    def test_rank_obligations_sorted(self):
        from services.debt_priority import rank_obligations
        obs = [
            {"obligation_type": "mortgage", "rate": 9, "balance": 3_000_000,
             "monthly_payment": 40_000, "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
            {"obligation_type": "credit_card", "rate": 30, "balance": 80_000,
             "monthly_payment": 5_000, "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
        ]
        ranked = rank_obligations(obs)
        self.assertEqual(ranked[0]["obligation_type"], "credit_card")

    def test_action_label(self):
        from services.debt_priority import action_label
        self.assertIn("первую", action_label("fast"))
        self.assertIn("минимум", action_label("minimum_only"))
        self.assertEqual(action_label("unknown_action"), "unknown_action")


# ─────────────────────────────────────────────────────────────────────
#  3. Prepayment target selection
# ─────────────────────────────────────────────────────────────────────

class TestPrepayment(unittest.TestCase):

    def test_highest_rate_selected(self):
        from services.prepayment import choose_prepayment_target
        obs = [
            {"name": "Ипотека", "rate": 9.5, "balance": 4_000_000, "monthly_payment": 50_000,
             "priority_score": 49, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "medium", "manual_prepayment_mode": "auto"},
            {"name": "Автокредит", "rate": 16, "balance": 600_000, "monthly_payment": 18_000,
             "priority_score": 93, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "medium", "manual_prepayment_mode": "auto"},
            {"name": "Кредитка", "rate": 30, "balance": 80_000, "monthly_payment": 5_000,
             "priority_score": 180, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "fast", "manual_prepayment_mode": "auto"},
        ]
        target = choose_prepayment_target(obs)
        self.assertEqual(target["name"], "Кредитка")

    def test_manual_order_overrides_rate(self):
        from services.prepayment import choose_prepayment_target
        obs = [
            {"name": "Дешёвый", "rate": 5, "balance": 100_000, "monthly_payment": 5_000,
             "priority_score": 10, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": 1, "recommended_action": "medium", "manual_prepayment_mode": "auto"},
            {"name": "Дорогой", "rate": 25, "balance": 200_000, "monthly_payment": 10_000,
             "priority_score": 150, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "fast", "manual_prepayment_mode": "auto"},
        ]
        target = choose_prepayment_target(obs)
        self.assertEqual(target["name"], "Дешёвый")

    def test_no_candidates_returns_none(self):
        from services.prepayment import choose_prepayment_target
        obs = [
            {"name": "Рассрочка", "rate": 0, "balance": 50_000, "monthly_payment": 5_000,
             "priority_score": 5, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "skip", "manual_prepayment_mode": "auto"},
        ]
        self.assertIsNone(choose_prepayment_target(obs))

    def test_empty_list_returns_none(self):
        from services.prepayment import choose_prepayment_target
        self.assertIsNone(choose_prepayment_target([]))

    def test_excluded_obligation_skipped(self):
        from services.prepayment import choose_prepayment_target
        obs = [
            {"name": "Excluded", "rate": 30, "balance": 100_000, "monthly_payment": 5_000,
             "priority_score": 180, "prepayment_allowed": True, "exclude_from_prepayment": True,
             "prepayment_order": None, "recommended_action": "fast", "manual_prepayment_mode": "auto"},
            {"name": "Allowed", "rate": 15, "balance": 200_000, "monthly_payment": 10_000,
             "priority_score": 100, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "medium", "manual_prepayment_mode": "auto"},
        ]
        target = choose_prepayment_target(obs)
        self.assertEqual(target["name"], "Allowed")

    def test_allocate_prepayment_caps_at_balance(self):
        from services.prepayment import allocate_prepayment
        obs = [
            {"name": "Small debt", "rate": 20, "balance": 5_000, "monthly_payment": 1_000,
             "priority_score": 150, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "fast", "manual_prepayment_mode": "auto"},
        ]
        result = allocate_prepayment(obs, 50_000)
        self.assertEqual(result[0]["allocated_prepayment"], 5_000)

    def test_allocate_prepayment_zero_budget(self):
        from services.prepayment import allocate_prepayment
        obs = [
            {"name": "Debt", "rate": 20, "balance": 100_000, "monthly_payment": 5_000,
             "priority_score": 150, "prepayment_allowed": True, "exclude_from_prepayment": False,
             "prepayment_order": None, "recommended_action": "fast", "manual_prepayment_mode": "auto"},
        ]
        result = allocate_prepayment(obs, 0)
        self.assertEqual(result[0]["allocated_prepayment"], 0)


# ─────────────────────────────────────────────────────────────────────
#  4. DB migrations
# ─────────────────────────────────────────────────────────────────────

class TestMigrations(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_tables_created(self):
        from db.connection import get_conn
        conn = get_conn()
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        for t in ("settings", "categories", "transactions", "obligations"):
            self.assertIn(t, tables)

    def test_default_settings(self):
        from repositories.settings_repo import get_setting
        self.assertEqual(get_setting("strategy_name"), "balanced")
        self.assertEqual(get_setting("onboarding_completed"), "false")

    def test_default_categories(self):
        from repositories.categories_repo import read_categories
        cats = read_categories()
        names = list(cats["name"])
        self.assertIn("Зарплата", names)
        self.assertIn("Расход", names)
        self.assertIn("Досрочка", names)

    def test_raskhod_has_variable_life_scope(self):
        from repositories.categories_repo import read_categories
        cats = read_categories("expense")
        raskhod = cats[cats["name"] == "Расход"]
        self.assertFalse(raskhod.empty)
        self.assertEqual(raskhod.iloc[0]["expense_scope"], "variable_life")

    def test_obligations_has_required_columns(self):
        from db.connection import get_conn
        conn = get_conn()
        cols = [c[1] for c in conn.execute("PRAGMA table_info(obligations)").fetchall()]
        conn.close()
        for col in ("prepayment_order", "exclude_from_prepayment", "recommendation_reason"):
            self.assertIn(col, cols)

    def test_idempotent_init(self):
        """init_db can be called twice without error."""
        from db.migrations import init_db
        init_db()  # already called in setUp, call again
        from repositories.settings_repo import get_setting
        self.assertEqual(get_setting("strategy_name"), "balanced")


# ─────────────────────────────────────────────────────────────────────
#  5. Repositories
# ─────────────────────────────────────────────────────────────────────

class TestRepositories(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def test_settings_crud(self):
        from repositories.settings_repo import get_setting, set_setting, bulk_set_settings
        set_setting("foo", "bar")
        self.assertEqual(get_setting("foo"), "bar")
        set_setting("foo", "baz")
        self.assertEqual(get_setting("foo"), "baz")
        bulk_set_settings({"a": "1", "b": "2"})
        self.assertEqual(get_setting("a"), "1")
        self.assertEqual(get_setting("b"), "2")

    def test_setting_default(self):
        from repositories.settings_repo import get_setting
        self.assertEqual(get_setting("nonexistent", "default_val"), "default_val")

    def test_category_crud(self):
        from repositories.categories_repo import add_category, read_categories, disable_category
        add_category("Тест", "expense", "variable_life", False)
        cats = read_categories("expense")
        test_cat = cats[cats["name"] == "Тест"]
        self.assertFalse(test_cat.empty)
        cat_id = int(test_cat.iloc[0]["id"])
        disable_category(cat_id)
        cats2 = read_categories("expense")
        self.assertTrue(cats2[cats2["name"] == "Тест"].empty)

    def test_ensure_category_idempotent(self):
        from repositories.categories_repo import ensure_category
        id1 = ensure_category("UniqueOne", "income")
        id2 = ensure_category("UniqueOne", "income")
        self.assertEqual(id1, id2)

    def test_transaction_crud(self):
        from repositories.transactions_repo import add_transaction, read_transactions, delete_transaction
        from repositories.categories_repo import ensure_category
        cat_id = ensure_category("TestIncome", "income")
        add_transaction("2026-04-05", "Salary", 100_000, "income", cat_id, False, "test")
        df = read_transactions(date(2026, 4, 1), date(2026, 4, 30))
        self.assertEqual(len(df), 1)
        self.assertEqual(float(df.iloc[0]["amount"]), 100_000)
        delete_transaction(int(df.iloc[0]["id"]))
        df2 = read_transactions(date(2026, 4, 1), date(2026, 4, 30))
        self.assertTrue(df2.empty)

    def test_obligation_crud(self):
        from repositories.obligations_repo import add_obligation, read_obligations, disable_obligation
        add_obligation("TestOb", "loan", 15.0, 200_000, 10_000, 2)
        obs = read_obligations()
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs.iloc[0]["name"], "TestOb")
        disable_obligation(int(obs.iloc[0]["id"]))
        self.assertTrue(read_obligations().empty)

    def test_reset_application_data(self):
        from repositories.settings_repo import set_setting, get_setting
        from repositories.admin_repo import reset_application_data
        set_setting("test_key", "test_value")
        reset_application_data()
        self.assertEqual(get_setting("test_key", "gone"), "gone")


# ─────────────────────────────────────────────────────────────────────
#  6. Onboarding logic
# ─────────────────────────────────────────────────────────────────────

class TestOnboarding(unittest.TestCase):

    def _make_payload(self, **overrides):
        payload = {
            "income": {
                "salary_gross": 200_000, "benefits": 10_000,
                "other_regular_income": 0, "bonuses": 0,
                "salary_taxable": True, "benefits_taxable": False,
                "other_regular_taxable": False, "bonuses_taxable": True,
                "annual_threshold": 5_000_000,
            },
            "fixed_expenses": [
                {"name": "Ипотека", "amount": 40_000, "category_name": "Ипотека", "note": ""},
            ],
            "variable_expenses": [
                {"name": "Ребёнок", "amount": 15_000, "category_name": "Ребёнок", "note": ""},
            ],
            "obligations": [],
            "strategy": "balanced",
        }
        payload.update(overrides)
        return payload

    def test_income_stored_as_net(self):
        from services.onboarding import _build_income_transactions
        payload = self._make_payload()
        txs, taxable, non_taxable, threshold = _build_income_transactions(payload)
        salary_tx = next(t for t in txs if t["name"] == "Зарплата")
        # 200k * 0.87 = 174k (13% NDFL)
        self.assertAlmostEqual(salary_tx["amount"], 174_000, delta=100)

    def test_non_taxable_income_unchanged(self):
        from services.onboarding import _build_income_transactions
        payload = self._make_payload()
        txs, _, _, _ = _build_income_transactions(payload)
        benefits_tx = next(t for t in txs if t["name"] == "Пособие")
        self.assertEqual(benefits_tx["amount"], 10_000)

    def test_transaction_sum_equals_net_income(self):
        from services.onboarding import build_onboarding_result
        payload = self._make_payload()
        r = build_onboarding_result(payload)
        tx_sum = sum(t["amount"] for t in r["income_transactions"])
        self.assertAlmostEqual(tx_sum, r["net_income"], delta=1)

    def test_strategy_percentages_correct(self):
        from services.onboarding import build_onboarding_result
        payload = self._make_payload(strategy="aggressive")
        r = build_onboarding_result(payload)
        self.assertEqual(r["strategy_life_pct"], 45)
        self.assertEqual(r["strategy_prepayment_pct"], 40)
        self.assertEqual(r["strategy_savings_pct"], 15)

    def test_life_budget_is_fraction_of_cashflow(self):
        from services.onboarding import build_onboarding_result
        payload = self._make_payload(strategy="balanced")
        r = build_onboarding_result(payload)
        expected = r["free_cashflow"] * 0.60
        self.assertAlmostEqual(r["life_budget"], expected, delta=1)

    def test_zero_income_produces_zero_budget(self):
        from services.onboarding import build_onboarding_result
        payload = self._make_payload()
        payload["income"]["salary_gross"] = 0
        payload["income"]["benefits"] = 0
        r = build_onboarding_result(payload)
        self.assertEqual(r["net_income"], 0)
        self.assertEqual(r["life_budget"], 0)

    def test_persist_onboarding(self):
        _reset_db()
        from services.onboarding import persist_onboarding
        from repositories.settings_repo import get_setting
        from repositories.transactions_repo import read_transactions
        payload = self._make_payload(obligations=[
            {"name": "Кредит", "obligation_type": "loan", "rate": 15,
             "balance": 300_000, "monthly_payment": 15_000,
             "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
        ])
        result = persist_onboarding(payload)
        self.assertEqual(get_setting("onboarding_completed"), "true")
        self.assertGreater(result["net_income"], 0)
        today = date.today()
        txs = read_transactions(today.replace(day=1), today.replace(day=28))
        self.assertGreater(len(txs), 0)

    def test_obligations_ranked_in_result(self):
        from services.onboarding import build_onboarding_result
        payload = self._make_payload(obligations=[
            {"obligation_type": "loan", "rate": 15, "balance": 100_000,
             "monthly_payment": 5_000, "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
            {"obligation_type": "credit_card", "rate": 28, "balance": 50_000,
             "monthly_payment": 3_000, "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
        ])
        r = build_onboarding_result(payload)
        self.assertEqual(len(r["ranked_obligations"]), 2)
        # Credit card should be first (higher score)
        self.assertEqual(r["ranked_obligations"][0]["obligation_type"], "credit_card")


# ─────────────────────────────────────────────────────────────────────
#  7. Monthly summary
# ─────────────────────────────────────────────────────────────────────

class TestMonthlySummary(unittest.TestCase):

    def setUp(self):
        _reset_db()

    def _run_onboarding(self):
        from services.onboarding import persist_onboarding
        return persist_onboarding({
            "income": {
                "salary_gross": 250_000, "benefits": 0,
                "other_regular_income": 0, "bonuses": 0,
                "salary_taxable": True, "benefits_taxable": False,
                "other_regular_taxable": False, "bonuses_taxable": True,
                "annual_threshold": 5_000_000,
            },
            "fixed_expenses": [
                {"name": "Ипотека", "amount": 50_000, "category_name": "Ипотека", "note": ""},
            ],
            "variable_expenses": [
                {"name": "Ребёнок", "amount": 20_000, "category_name": "Ребёнок", "note": ""},
            ],
            "obligations": [
                {"name": "Автокредит", "obligation_type": "car_loan", "rate": 16,
                 "balance": 600_000, "monthly_payment": 18_000,
                 "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
            ],
            "strategy": "balanced",
        })

    def test_summary_returns_all_keys(self):
        self._run_onboarding()
        from services.summary import monthly_summary
        s = monthly_summary(date.today())
        required_keys = [
            "income_total", "expense_total", "mandatory_total", "free_cash_flow",
            "life_budget", "life_spent", "life_budget_left", "life_budget_per_day_left",
            "daily_limit", "spent_today", "remaining_days",
            "recommended_prepayment", "recommended_savings",
            "strategy_label", "strategy_life_pct", "strategy_prepayment_pct", "strategy_savings_pct",
            "priority_debts", "prepayment_target", "prepayment_plan",
        ]
        for key in required_keys:
            self.assertIn(key, s, f"Missing key: {key}")

    def test_income_is_net(self):
        self._run_onboarding()
        from services.summary import monthly_summary
        s = monthly_summary(date.today())
        # 250k gross → ~217.5k net (13%)
        self.assertAlmostEqual(s["income_total"], 217_500, delta=100)

    def test_daily_limit_positive(self):
        self._run_onboarding()
        from services.summary import monthly_summary
        s = monthly_summary(date.today())
        self.assertGreater(s["daily_limit"], 0)

    def test_spent_today_tracks_life_expenses(self):
        self._run_onboarding()
        from repositories.categories_repo import read_categories
        from repositories.transactions_repo import add_transaction
        from services.summary import monthly_summary
        cats = read_categories("expense")
        life_cat_id = int(cats[cats["expense_scope"] == "variable_life"].iloc[0]["id"])
        add_transaction(date.today().isoformat(), "Кофе", 500, "expense", life_cat_id, False, "")
        s = monthly_summary(date.today())
        self.assertEqual(s["spent_today"], 500)

    def test_daily_limit_decreases_after_expense(self):
        self._run_onboarding()
        from repositories.categories_repo import read_categories
        from repositories.transactions_repo import add_transaction
        from services.summary import monthly_summary
        s1 = monthly_summary(date.today())
        cats = read_categories("expense")
        life_cat_id = int(cats[cats["expense_scope"] == "variable_life"].iloc[0]["id"])
        add_transaction(date.today().isoformat(), "Расход", 5_000, "expense", life_cat_id, False, "")
        s2 = monthly_summary(date.today())
        self.assertLess(s2["daily_limit"], s1["daily_limit"])

    def test_prepayment_target_is_highest_rate(self):
        _reset_db()
        from services.onboarding import persist_onboarding
        persist_onboarding({
            "income": {
                "salary_gross": 300_000, "benefits": 0,
                "other_regular_income": 0, "bonuses": 0,
                "salary_taxable": True, "benefits_taxable": False,
                "other_regular_taxable": False, "bonuses_taxable": True,
                "annual_threshold": 5_000_000,
            },
            "fixed_expenses": [],
            "variable_expenses": [],
            "obligations": [
                {"name": "Ипотека", "obligation_type": "mortgage", "rate": 9.5,
                 "balance": 4_000_000, "monthly_payment": 50_000,
                 "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
                {"name": "Кредитка", "obligation_type": "credit_card", "rate": 28,
                 "balance": 100_000, "monthly_payment": 5_000,
                 "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
            ],
            "strategy": "balanced",
        })
        from services.summary import monthly_summary
        s = monthly_summary(date.today())
        self.assertIsNotNone(s["prepayment_target"])
        self.assertEqual(s["prepayment_target"]["name"], "Кредитка")

    def test_prepayment_target_payment_breakdown(self):
        self._run_onboarding()
        from services.summary import monthly_summary
        s = monthly_summary(date.today())
        t = s["prepayment_target"]
        if t:
            self.assertGreater(t["monthly_payment"], 0)
            self.assertGreaterEqual(t["allocated_prepayment"], 0)
            self.assertAlmostEqual(
                t["total_payment"],
                t["monthly_payment"] + t["allocated_prepayment"],
                places=2,
            )

    def test_empty_month_summary(self):
        """Summary for a month with no transactions."""
        from services.summary import monthly_summary
        s = monthly_summary(date(2020, 1, 15))  # no data
        self.assertEqual(s["income_total"], 0)
        self.assertEqual(s["daily_limit"], 0)
        self.assertEqual(s["spent_today"], 0)

    def test_strategy_label_present(self):
        self._run_onboarding()
        from services.summary import monthly_summary
        s = monthly_summary(date.today())
        self.assertEqual(s["strategy_label"], "Balanced")
        self.assertEqual(s["strategy_life_pct"], 60)


# ─────────────────────────────────────────────────────────────────────
#  8. fmt_rub
# ─────────────────────────────────────────────────────────────────────

class TestFmtRub(unittest.TestCase):

    def test_positive(self):
        from services.summary import fmt_rub
        self.assertEqual(fmt_rub(1234567), "1 234 567 ₽")

    def test_zero(self):
        from services.summary import fmt_rub
        self.assertEqual(fmt_rub(0), "0 ₽")

    def test_negative(self):
        from services.summary import fmt_rub
        result = fmt_rub(-5000)
        self.assertIn("5 000", result)


# ─────────────────────────────────────────────────────────────────────
#  9. Strategies
# ─────────────────────────────────────────────────────────────────────

class TestStrategies(unittest.TestCase):

    def test_all_strategies_sum_to_100(self):
        from services.onboarding import STRATEGIES
        for name, s in STRATEGIES.items():
            total = s["life_pct"] + s["prepayment_pct"] + s["savings_pct"]
            self.assertEqual(total, 100, f"Strategy {name} sums to {total}")

    def test_all_strategies_produce_result(self):
        from services.onboarding import build_onboarding_result, STRATEGIES
        for strategy_name in STRATEGIES:
            payload = {
                "income": {
                    "salary_gross": 150_000, "benefits": 0,
                    "other_regular_income": 0, "bonuses": 0,
                    "salary_taxable": True, "benefits_taxable": False,
                    "other_regular_taxable": False, "bonuses_taxable": True,
                    "annual_threshold": 5_000_000,
                },
                "fixed_expenses": [],
                "variable_expenses": [],
                "obligations": [],
                "strategy": strategy_name,
            }
            r = build_onboarding_result(payload)
            self.assertGreater(r["net_income"], 0)
            budget_sum = r["life_budget"] + r["recommended_prepayment"] + r["recommended_savings"]
            self.assertAlmostEqual(budget_sum, r["free_cashflow"], delta=1)


# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
