"""Tests for services/tax.py — НДФЛ progressive tax calculation."""
import unittest
from services.tax import calc_progressive_ndfl_13_15, calc_monthly_net_income


class TestProgressiveNDFL(unittest.TestCase):
    def test_below_threshold_13_percent(self):
        result = calc_progressive_ndfl_13_15(1_000_000, 5_000_000)
        self.assertAlmostEqual(result["tax_annual"], 130_000.0, places=2)
        self.assertAlmostEqual(result["net_taxable_annual"], 870_000.0, places=2)

    def test_at_threshold_exactly(self):
        result = calc_progressive_ndfl_13_15(5_000_000, 5_000_000)
        self.assertAlmostEqual(result["tax_annual"], 650_000.0, places=2)

    def test_above_threshold_mixed_rate(self):
        result = calc_progressive_ndfl_13_15(6_000_000, 5_000_000)
        expected_tax = 5_000_000 * 0.13 + 1_000_000 * 0.15  # 650k + 150k = 800k
        self.assertAlmostEqual(result["tax_annual"], expected_tax, places=2)

    def test_zero_income(self):
        result = calc_progressive_ndfl_13_15(0, 5_000_000)
        self.assertAlmostEqual(result["tax_annual"], 0.0)
        self.assertAlmostEqual(result["net_taxable_annual"], 0.0)


class TestMonthlyNetIncome(unittest.TestCase):
    def test_basic_salary(self):
        result = calc_monthly_net_income(100_000, 0, 5_000_000)
        # 100k/mo * 12 = 1.2M annual, all below 5M threshold → 13%
        self.assertAlmostEqual(result["tax_monthly"], 13_000.0, places=2)
        self.assertAlmostEqual(result["net_total_monthly"], 87_000.0, places=2)

    def test_with_non_taxable(self):
        result = calc_monthly_net_income(100_000, 20_000, 5_000_000)
        self.assertAlmostEqual(result["tax_monthly"], 13_000.0, places=2)
        # net = 87k taxable + 20k non-taxable = 107k
        self.assertAlmostEqual(result["net_total_monthly"], 107_000.0, places=2)

    def test_zero_taxable(self):
        result = calc_monthly_net_income(0, 50_000, 5_000_000)
        self.assertAlmostEqual(result["tax_monthly"], 0.0)
        self.assertAlmostEqual(result["net_total_monthly"], 50_000.0, places=2)

    def test_high_income_mixed_rate(self):
        # 500k/mo * 12 = 6M annual → above 5M threshold
        result = calc_monthly_net_income(500_000, 0, 5_000_000)
        annual_tax = 5_000_000 * 0.13 + 1_000_000 * 0.15  # 800k
        monthly_tax = annual_tax / 12
        self.assertAlmostEqual(result["tax_monthly"], round(monthly_tax, 2), places=2)


if __name__ == "__main__":
    unittest.main()
