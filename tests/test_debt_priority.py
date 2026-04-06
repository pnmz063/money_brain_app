"""Tests for services/debt_priority.py — obligation classification and ranking."""
import unittest
from services.debt_priority import classify_obligation, rank_obligations, action_label, _to_float


class TestClassifyObligation(unittest.TestCase):
    def _make(self, **overrides):
        base = {
            "name": "Test",
            "obligation_type": "loan",
            "rate": 15.0,
            "balance": 500_000,
            "monthly_payment": 15_000,
            "prepayment_allowed": True,
            "manual_prepayment_mode": "auto",
        }
        base.update(overrides)
        return base

    def test_skip_prepayment_mode(self):
        r = classify_obligation(self._make(manual_prepayment_mode="skip_prepayment"))
        self.assertEqual(r["recommended_action"], "skip")
        self.assertEqual(r["priority_score"], -1.0)

    def test_minimum_only_mode(self):
        r = classify_obligation(self._make(manual_prepayment_mode="minimum_only"))
        self.assertEqual(r["recommended_action"], "minimum_only")
        self.assertEqual(r["priority_score"], 0.0)

    def test_prepayment_not_allowed(self):
        r = classify_obligation(self._make(prepayment_allowed=False))
        self.assertEqual(r["recommended_action"], "minimum_only")

    def test_low_rate_installment(self):
        r = classify_obligation(self._make(obligation_type="installment", rate=5))
        self.assertEqual(r["recommended_action"], "skip")
        self.assertEqual(r["priority"], 5)

    def test_low_rate_below_6(self):
        r = classify_obligation(self._make(rate=4))
        self.assertEqual(r["recommended_action"], "skip")

    def test_high_rate_credit_card(self):
        r = classify_obligation(self._make(obligation_type="credit_card", rate=25))
        self.assertEqual(r["recommended_action"], "fast")
        self.assertEqual(r["priority"], 1)

    def test_high_rate_over_20(self):
        r = classify_obligation(self._make(rate=22))
        self.assertEqual(r["recommended_action"], "fast")

    def test_medium_rate(self):
        r = classify_obligation(self._make(rate=15))
        self.assertEqual(r["recommended_action"], "medium")
        self.assertEqual(r["priority"], 2)

    def test_moderate_rate(self):
        r = classify_obligation(self._make(rate=8))
        self.assertEqual(r["recommended_action"], "minimum_only")
        self.assertEqual(r["priority"], 3)

    def test_payoff_months_present(self):
        r = classify_obligation(self._make(rate=15, balance=500_000, monthly_payment=15_000))
        self.assertIn("payoff_months", r)
        self.assertIsNotNone(r["payoff_months"])
        self.assertGreater(r["payoff_months"], 0)

    def test_balance_affects_score(self):
        """Higher balance = more total interest = higher priority score."""
        small = classify_obligation(self._make(rate=15, balance=100_000, monthly_payment=15_000))
        big = classify_obligation(self._make(rate=15, balance=2_000_000, monthly_payment=30_000))
        # Both medium priority, but big balance should have higher score
        self.assertGreater(big["priority_score"], small["priority_score"])

    def test_total_interest_calculated(self):
        r = classify_obligation(self._make(rate=15, balance=500_000, monthly_payment=15_000))
        self.assertIn("total_interest", r)
        self.assertGreater(r["total_interest"], 0)

    def test_zero_balance_zero_interest(self):
        r = classify_obligation(self._make(rate=15, balance=0, monthly_payment=15_000))
        self.assertIn("payoff_months", r)
        self.assertEqual(r["payoff_months"], 0)


class TestRankObligations(unittest.TestCase):
    def test_sorted_by_priority_score(self):
        obs = [
            {"name": "Low", "obligation_type": "loan", "rate": 8,
             "balance": 100_000, "monthly_payment": 5000,
             "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
            {"name": "High", "obligation_type": "credit_card", "rate": 25,
             "balance": 200_000, "monthly_payment": 10000,
             "prepayment_allowed": True, "manual_prepayment_mode": "auto"},
        ]
        ranked = rank_obligations(obs)
        self.assertEqual(ranked[0]["name"], "High")
        self.assertEqual(ranked[1]["name"], "Low")


class TestActionLabel(unittest.TestCase):
    def test_known_labels(self):
        self.assertIn("первую", action_label("fast"))
        self.assertIn("умеренно", action_label("medium"))

    def test_unknown_returns_as_is(self):
        self.assertEqual(action_label("unknown"), "unknown")


class TestBackwardCompatToFloat(unittest.TestCase):
    def test_to_float_alias(self):
        self.assertEqual(_to_float("123.45"), 123.45)


if __name__ == "__main__":
    unittest.main()
