"""Tests for services/optimizer.py — debt avalanche planner."""
import tests.conftest  # noqa: F401
import unittest

from services.optimizer import build_optimal_plan, _baseline_total, _simulate_avalanche


def _credit_card():
    return {"name": "Кредитка", "balance": 80_000, "rate": 28, "monthly_payment": 5_000}


def _loan():
    return {"name": "Кредит", "balance": 300_000, "rate": 18, "monthly_payment": 10_000}


def _mortgage():
    return {"name": "Ипотека", "balance": 4_000_000, "rate": 10, "monthly_payment": 45_000}


class TestBaseline(unittest.TestCase):
    def test_single_debt(self):
        b = _baseline_total([_credit_card()])
        self.assertGreater(b["total_paid"], 80_000)  # principal + interest
        self.assertGreater(b["total_interest"], 0)
        self.assertGreater(b["max_months"], 0)

    def test_skips_zero(self):
        b = _baseline_total([{"balance": 0, "rate": 10, "monthly_payment": 1000}])
        self.assertEqual(b["total_paid"], 0.0)


class TestSimulateAvalanche(unittest.TestCase):
    def test_extra_payment_reduces_interest(self):
        obs = [_credit_card(), _loan()]
        no_extra = _simulate_avalanche(obs, 0)
        with_extra = _simulate_avalanche(obs, 5_000)
        self.assertLess(with_extra["total_interest"], no_extra["total_interest"])
        self.assertLessEqual(with_extra["max_months"], no_extra["max_months"])

    def test_highest_rate_closes_first(self):
        # Credit card 28% should close before loan 18%
        obs = [_loan(), _credit_card()]
        result = _simulate_avalanche(obs, 5_000)
        cc = next(d for d in result["debts"] if d["name"] == "Кредитка")
        ln = next(d for d in result["debts"] if d["name"] == "Кредит")
        self.assertIsNotNone(cc["closed_month"])
        self.assertIsNotNone(ln["closed_month"])
        self.assertLess(cc["closed_month"], ln["closed_month"])

    def test_empty_list(self):
        r = _simulate_avalanche([], 5_000)
        self.assertEqual(r["total_paid"], 0.0)
        self.assertEqual(r["max_months"], 0)


class TestBuildOptimalPlan(unittest.TestCase):
    def test_savings_positive(self):
        plan = build_optimal_plan([_credit_card(), _loan()], 5_000)
        self.assertGreater(plan["interest_saved"], 0)
        self.assertGreaterEqual(plan["months_saved"], 0)

    def test_zero_budget_single_debt(self):
        # Single debt, zero extra → baseline ≈ optimal (no rollover possible)
        plan = build_optimal_plan([_credit_card()], 0)
        self.assertLess(abs(plan["interest_saved"]), 5_000)

    def test_full_scenario_with_mortgage(self):
        plan = build_optimal_plan([_credit_card(), _loan(), _mortgage()], 10_000)
        self.assertGreater(plan["interest_saved"], 0)
        # Closing order: credit card first (highest rate), then loan, then mortgage
        names = [d["name"] for d in plan["closing_order"]]
        self.assertEqual(names[0], "Кредитка")

    def test_returns_required_fields(self):
        plan = build_optimal_plan([_credit_card()], 2_000)
        for key in ("baseline", "optimal", "interest_saved", "months_saved", "closing_order"):
            self.assertIn(key, plan)


if __name__ == "__main__":
    unittest.main()
