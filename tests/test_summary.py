"""Tests for services/summary.py — monthly summary logic.

Uses mocks to avoid needing a real database.
Tests verify the CORE BUG FIXES:
- Obligation payments from obligations table are included in mandatory_total
- free_cash_flow is correctly reduced by obligation payments
- No double counting between transactions and obligations
"""
import tests.conftest  # noqa: F401 — mock psycopg2 before importing services
import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import pandas as pd

from services.summary import monthly_summary, month_bounds, fmt_rub


class TestMonthBounds(unittest.TestCase):
    def test_january(self):
        s, e = month_bounds(date(2026, 1, 15))
        self.assertEqual(s, date(2026, 1, 1))
        self.assertEqual(e, date(2026, 1, 31))

    def test_february_non_leap(self):
        s, e = month_bounds(date(2025, 2, 10))
        self.assertEqual(e, date(2025, 2, 28))

    def test_february_leap(self):
        s, e = month_bounds(date(2024, 2, 10))
        self.assertEqual(e, date(2024, 2, 29))


class TestFmtRub(unittest.TestCase):
    def test_integer_value(self):
        self.assertIn("1", fmt_rub(1000))
        self.assertIn("₽", fmt_rub(1000))

    def test_float_value(self):
        result = fmt_rub(1234.56)
        self.assertIn("₽", result)

    def test_none(self):
        self.assertEqual(fmt_rub(None), "—")

    def test_bad_string(self):
        self.assertEqual(fmt_rub("abc"), "—")


def _empty_df():
    return pd.DataFrame(columns=[
        "id", "tx_date", "name", "amount", "kind", "is_fixed", "note",
        "category_name", "expense_scope"
    ])


def _sample_transactions():
    """Create transactions: income 174k, fixed expense 10k, variable_mandatory 25k."""
    data = [
        {"id": 1, "tx_date": "2026-04-01", "name": "Зарплата", "amount": 174_000.0,
         "kind": "income", "is_fixed": False, "note": "", "category_name": "Зарплата",
         "expense_scope": None},
        {"id": 2, "tx_date": "2026-04-01", "name": "ЖКХ", "amount": 10_000.0,
         "kind": "expense", "is_fixed": True, "note": "", "category_name": "ЖКХ",
         "expense_scope": "fixed"},
        {"id": 3, "tx_date": "2026-04-01", "name": "Продукты", "amount": 25_000.0,
         "kind": "expense", "is_fixed": False, "note": "", "category_name": "Продукты",
         "expense_scope": "variable_mandatory"},
    ]
    return pd.DataFrame(data)


def _sample_obligations():
    """Obligations: mortgage 45k/mo, credit card 5k/mo."""
    data = [
        {"id": 1, "name": "Ипотека", "obligation_type": "mortgage", "rate": 10.0,
         "balance": 4_000_000.0, "monthly_payment": 45_000.0, "priority": 3,
         "priority_score": 30.0, "recommended_action": "minimum_only",
         "recommendation_reason": "", "prepayment_allowed": True,
         "manual_prepayment_mode": "auto", "prepayment_order": None,
         "exclude_from_prepayment": False, "is_active": True, "note": "",
         "user_id": 1},
        {"id": 2, "name": "Кредитка", "obligation_type": "credit_card", "rate": 28.0,
         "balance": 80_000.0, "monthly_payment": 5_000.0, "priority": 1,
         "priority_score": 128.0, "recommended_action": "fast",
         "recommendation_reason": "", "prepayment_allowed": True,
         "manual_prepayment_mode": "auto", "prepayment_order": None,
         "exclude_from_prepayment": False, "is_active": True, "note": "",
         "user_id": 1},
    ]
    return pd.DataFrame(data)


class TestMonthlySummary(unittest.TestCase):
    """Integration-style tests with mocked DB calls."""

    @patch("services.summary.get_setting")
    @patch("services.summary.read_obligations")
    @patch("services.summary.read_transactions")
    def test_obligations_in_mandatory_total(self, mock_tx, mock_ob, mock_setting):
        """CORE FIX: obligation payments must be included in mandatory_total."""
        mock_tx.return_value = _sample_transactions()
        mock_ob.return_value = _sample_obligations()
        mock_setting.side_effect = lambda key, uid, default: {
            "strategy_life_pct": "60",
            "strategy_prepayment_pct": "25",
            "strategy_savings_pct": "15",
            "strategy_name": "balanced",
        }.get(key, default)

        result = monthly_summary(date(2026, 4, 6), user_id=1)

        # Transaction expenses: ЖКХ 10k + Продукты 25k = 35k
        self.assertAlmostEqual(result["fixed_expense_total"], 10_000.0)
        self.assertAlmostEqual(result["variable_mandatory_total"], 25_000.0)

        # Obligation payments: 45k + 5k = 50k
        self.assertAlmostEqual(result["obligation_payments_total"], 50_000.0)

        # mandatory_total = 10k + 25k + 50k = 85k
        self.assertAlmostEqual(result["mandatory_total"], 85_000.0)

        # FCF = income(174k) - mandatory(85k) = 89k
        self.assertAlmostEqual(result["free_cash_flow"], 89_000.0)

    @patch("services.summary.get_setting")
    @patch("services.summary.read_obligations")
    @patch("services.summary.read_transactions")
    def test_no_double_count_without_obligation_transactions(self, mock_tx, mock_ob, mock_setting):
        """After fix, no transaction is created for obligation payments."""
        # Only income transaction, no expense transactions for obligations
        income_only = pd.DataFrame([{
            "id": 1, "tx_date": "2026-04-01", "name": "Зарплата", "amount": 174_000.0,
            "kind": "income", "is_fixed": False, "note": "", "category_name": "Зарплата",
            "expense_scope": None,
        }])
        mock_tx.return_value = income_only
        mock_ob.return_value = _sample_obligations()
        mock_setting.side_effect = lambda key, uid, default: {
            "strategy_life_pct": "60",
            "strategy_prepayment_pct": "25",
            "strategy_savings_pct": "15",
            "strategy_name": "balanced",
        }.get(key, default)

        result = monthly_summary(date(2026, 4, 6), user_id=1)

        # No expense transactions → fixed_expense_total = 0, variable_mandatory = 0
        self.assertAlmostEqual(result["fixed_expense_total"], 0.0)
        self.assertAlmostEqual(result["variable_mandatory_total"], 0.0)

        # But obligation payments (50k) still count
        self.assertAlmostEqual(result["obligation_payments_total"], 50_000.0)
        self.assertAlmostEqual(result["mandatory_total"], 50_000.0)

        # FCF = 174k - 50k = 124k
        self.assertAlmostEqual(result["free_cash_flow"], 124_000.0)

    @patch("services.summary.get_setting")
    @patch("services.summary.read_obligations")
    @patch("services.summary.read_transactions")
    def test_empty_month_still_counts_obligations(self, mock_tx, mock_ob, mock_setting):
        """CORE FIX: Even with no transactions (e.g. month 2), obligations count."""
        mock_tx.return_value = _empty_df()
        mock_ob.return_value = _sample_obligations()
        mock_setting.side_effect = lambda key, uid, default: {
            "strategy_life_pct": "60",
            "strategy_prepayment_pct": "25",
            "strategy_savings_pct": "15",
            "strategy_name": "balanced",
        }.get(key, default)

        result = monthly_summary(date(2026, 5, 1), user_id=1)

        # No income, no expense transactions
        self.assertAlmostEqual(result["income_total"], 0.0)
        self.assertAlmostEqual(result["fixed_expense_total"], 0.0)

        # But obligation payments still exist
        self.assertAlmostEqual(result["obligation_payments_total"], 50_000.0)
        self.assertAlmostEqual(result["mandatory_total"], 50_000.0)

        # FCF = max(0 - 50k, 0) = 0 (can't go negative)
        self.assertAlmostEqual(result["free_cash_flow"], 0.0)

    @patch("services.summary.get_setting")
    @patch("services.summary.read_obligations")
    @patch("services.summary.read_transactions")
    def test_no_obligations(self, mock_tx, mock_ob, mock_setting):
        """Works correctly with no obligations."""
        mock_tx.return_value = _sample_transactions()
        mock_ob.return_value = pd.DataFrame()
        mock_setting.side_effect = lambda key, uid, default: {
            "strategy_life_pct": "60",
            "strategy_prepayment_pct": "25",
            "strategy_savings_pct": "15",
            "strategy_name": "balanced",
        }.get(key, default)

        result = monthly_summary(date(2026, 4, 6), user_id=1)
        self.assertAlmostEqual(result["obligation_payments_total"], 0.0)
        # mandatory = only from transactions: 10k + 25k = 35k
        self.assertAlmostEqual(result["mandatory_total"], 35_000.0)
        # FCF = 174k - 35k = 139k
        self.assertAlmostEqual(result["free_cash_flow"], 139_000.0)

    @patch("services.summary.get_setting")
    @patch("services.summary.read_obligations")
    @patch("services.summary.read_transactions")
    def test_daily_limit(self, mock_tx, mock_ob, mock_setting):
        """Daily limit = life_budget_left / remaining_days."""
        mock_tx.return_value = _sample_transactions()
        mock_ob.return_value = pd.DataFrame()
        mock_setting.side_effect = lambda key, uid, default: {
            "strategy_life_pct": "60",
            "strategy_prepayment_pct": "25",
            "strategy_savings_pct": "15",
            "strategy_name": "balanced",
        }.get(key, default)

        result = monthly_summary(date(2026, 4, 6), user_id=1)
        # life_budget = FCF * 60%
        fcf = result["free_cash_flow"]
        life_budget = fcf * 0.60
        self.assertAlmostEqual(result["life_budget"], life_budget, places=2)
        self.assertGreater(result["daily_limit"], 0)
        self.assertGreater(result["remaining_days"], 0)

    @patch("services.summary.get_setting")
    @patch("services.summary.read_obligations")
    @patch("services.summary.read_transactions")
    def test_total_debt_stats(self, mock_tx, mock_ob, mock_setting):
        mock_tx.return_value = _sample_transactions()
        mock_ob.return_value = _sample_obligations()
        mock_setting.side_effect = lambda key, uid, default: {
            "strategy_life_pct": "60",
            "strategy_prepayment_pct": "25",
            "strategy_savings_pct": "15",
            "strategy_name": "balanced",
        }.get(key, default)

        result = monthly_summary(date(2026, 4, 6), user_id=1)
        self.assertAlmostEqual(result["total_debt"], 4_080_000.0)
        self.assertAlmostEqual(result["total_monthly_payments"], 50_000.0)
        self.assertGreater(result["max_payoff_months"], 0)


if __name__ == "__main__":
    unittest.main()
