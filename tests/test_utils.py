"""Tests for services/utils.py — shared utilities."""
import unittest
from decimal import Decimal
from services.utils import to_float, estimate_payoff_months


class TestToFloat(unittest.TestCase):
    def test_none(self):
        self.assertEqual(to_float(None), 0.0)

    def test_int(self):
        self.assertEqual(to_float(42), 42.0)

    def test_float(self):
        self.assertEqual(to_float(3.14), 3.14)

    def test_decimal(self):
        self.assertAlmostEqual(to_float(Decimal("123.45")), 123.45)

    def test_string_comma_decimal(self):
        self.assertAlmostEqual(to_float("1234,56"), 1234.56)

    def test_string_thousand_sep(self):
        self.assertAlmostEqual(to_float("1,234.56"), 1234.56)

    def test_string_nbsp(self):
        self.assertAlmostEqual(to_float("1\xa0234.56"), 1234.56)

    def test_empty_string(self):
        self.assertEqual(to_float(""), 0.0)

    def test_none_string(self):
        self.assertEqual(to_float("none"), 0.0)
        self.assertEqual(to_float("None"), 0.0)

    def test_nan_string(self):
        self.assertEqual(to_float("nan"), 0.0)

    def test_percent(self):
        self.assertAlmostEqual(to_float("12.5%"), 12.5)

    def test_default(self):
        self.assertEqual(to_float("garbage", default=-1.0), -1.0)


class TestEstimatePayoffMonths(unittest.TestCase):
    def test_zero_balance(self):
        self.assertEqual(estimate_payoff_months(0, 12, 10_000), 0)

    def test_zero_rate_simple_division(self):
        self.assertEqual(estimate_payoff_months(100_000, 0, 10_000), 10)

    def test_zero_rate_with_remainder(self):
        # 100k / 30k = 3.33 → ceil = 4
        self.assertEqual(estimate_payoff_months(100_000, 0, 30_000), 4)

    def test_normal_loan(self):
        # 1M at 12%, 20k/mo
        months = estimate_payoff_months(1_000_000, 12.0, 20_000)
        self.assertIsNotNone(months)
        self.assertGreater(months, 0)
        # Should be around 70 months
        self.assertAlmostEqual(months, 70, delta=2)

    def test_payment_too_low_returns_none(self):
        # 1M at 24%, 5k/mo → interest alone is 20k/mo
        result = estimate_payoff_months(1_000_000, 24.0, 5_000)
        self.assertIsNone(result)

    def test_payment_equals_interest_returns_none(self):
        # 1M at 12%, interest = 10k/mo, payment = 10k/mo → never pays off
        result = estimate_payoff_months(1_000_000, 12.0, 10_000)
        self.assertIsNone(result)

    def test_zero_payment(self):
        self.assertEqual(estimate_payoff_months(100_000, 12, 0), 0)

    def test_negative_balance(self):
        self.assertEqual(estimate_payoff_months(-1, 12, 10_000), 0)


if __name__ == "__main__":
    unittest.main()
