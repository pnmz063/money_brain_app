"""Tests for services/onboarding.py — onboarding result builder.

These tests verify the CORE BUG FIXES:
- Obligation payments are included in mandatory_total
- No double counting (obligations are separate from fixed_expenses)
- FCF calculation is correct
"""
import tests.conftest  # noqa: F401 — mock psycopg2 before importing services
import unittest
from services.onboarding import build_onboarding_result, STRATEGIES


def _payload(salary_gross=200_000, fixed_expenses=None, variable_expenses=None,
             obligations=None, strategy="balanced"):
    return {
        "income": {
            "salary_gross": salary_gross,
            "benefits": 0,
            "other_regular_income": 0,
            "bonuses": 0,
            "salary_taxable": True,
            "benefits_taxable": False,
            "other_regular_taxable": False,
            "bonuses_taxable": True,
            "annual_threshold": 5_000_000,
        },
        "fixed_expenses": fixed_expenses or [],
        "variable_expenses": variable_expenses or [],
        "obligations": obligations or [],
        "strategy": strategy,
    }


class TestBuildOnboardingResult(unittest.TestCase):

    def test_no_expenses_no_debts(self):
        """With no expenses or debts, free cashflow = full net income."""
        result = build_onboarding_result(_payload(salary_gross=200_000))
        # 200k * 12 = 2.4M < 5M → 13% tax → net = 174k
        self.assertAlmostEqual(result["net_income"], 174_000.0, places=0)
        self.assertAlmostEqual(result["mandatory_total"], 0.0)
        self.assertAlmostEqual(result["free_cashflow"], 174_000.0, places=0)

    def test_fixed_expenses_reduce_fcf(self):
        result = build_onboarding_result(_payload(
            salary_gross=200_000,
            fixed_expenses=[{"name": "ЖКХ", "amount": 10_000, "category_name": "ЖКХ"}],
        ))
        self.assertAlmostEqual(result["fixed_expenses_total"], 10_000.0)
        self.assertAlmostEqual(result["mandatory_total"], 10_000.0)
        expected_fcf = result["net_income"] - 10_000
        self.assertAlmostEqual(result["free_cashflow"], expected_fcf, places=2)

    def test_obligation_payments_reduce_fcf(self):
        """CORE FIX: obligation monthly_payment must reduce free cashflow."""
        result = build_onboarding_result(_payload(
            salary_gross=200_000,
            obligations=[{
                "name": "Ипотека",
                "obligation_type": "mortgage",
                "rate": 10,
                "balance": 3_000_000,
                "monthly_payment": 30_000,
                "prepayment_allowed": True,
                "manual_prepayment_mode": "auto",
            }],
        ))
        self.assertAlmostEqual(result["obligation_payments_total"], 30_000.0)
        self.assertAlmostEqual(result["mandatory_total"], 30_000.0)
        expected_fcf = result["net_income"] - 30_000
        self.assertAlmostEqual(result["free_cashflow"], expected_fcf, places=2)

    def test_no_double_counting(self):
        """Obligation payments must NOT be double-counted with fixed expenses."""
        result = build_onboarding_result(_payload(
            salary_gross=200_000,
            fixed_expenses=[{"name": "ЖКХ", "amount": 10_000, "category_name": "ЖКХ"}],
            obligations=[{
                "name": "Кредит",
                "obligation_type": "loan",
                "rate": 15,
                "balance": 500_000,
                "monthly_payment": 15_000,
                "prepayment_allowed": True,
                "manual_prepayment_mode": "auto",
            }],
        ))
        self.assertAlmostEqual(result["fixed_expenses_total"], 10_000.0)
        self.assertAlmostEqual(result["obligation_payments_total"], 15_000.0)
        self.assertAlmostEqual(result["mandatory_total"], 25_000.0)

        expected_fcf = result["net_income"] - 25_000
        self.assertAlmostEqual(result["free_cashflow"], expected_fcf, places=2)

    def test_strategy_split(self):
        """Balanced strategy: 60% life, 25% prepay, 15% savings."""
        result = build_onboarding_result(_payload(
            salary_gross=200_000,
            strategy="balanced",
        ))
        fcf = result["free_cashflow"]
        self.assertAlmostEqual(result["life_budget"], fcf * 0.60, places=2)
        self.assertAlmostEqual(result["recommended_prepayment"], fcf * 0.25, places=2)
        self.assertAlmostEqual(result["recommended_savings"], fcf * 0.15, places=2)

    def test_full_scenario(self):
        """Full realistic scenario: salary + mortgage + ЖКХ + groceries."""
        result = build_onboarding_result(_payload(
            salary_gross=250_000,
            fixed_expenses=[
                {"name": "ЖКХ", "amount": 8_000, "category_name": "ЖКХ"},
            ],
            variable_expenses=[
                {"name": "Продукты", "amount": 25_000, "category_name": "Продукты"},
            ],
            obligations=[
                {
                    "name": "Ипотека",
                    "obligation_type": "mortgage",
                    "rate": 10,
                    "balance": 4_000_000,
                    "monthly_payment": 45_000,
                    "prepayment_allowed": True,
                    "manual_prepayment_mode": "auto",
                },
                {
                    "name": "Кредитка",
                    "obligation_type": "credit_card",
                    "rate": 28,
                    "balance": 80_000,
                    "monthly_payment": 5_000,
                    "prepayment_allowed": True,
                    "manual_prepayment_mode": "auto",
                },
            ],
            strategy="balanced",
        ))
        # net income = 250k - 13% = 217.5k
        self.assertAlmostEqual(result["net_income"], 217_500.0, places=0)
        # mandatory = ЖКХ(8k) + Продукты(25k) + Ипотека(45k) + Кредитка(5k) = 83k
        self.assertAlmostEqual(result["mandatory_total"], 83_000.0, places=0)
        # FCF = 217.5k - 83k = 134.5k
        self.assertAlmostEqual(result["free_cashflow"], 134_500.0, places=0)
        # Life budget = 134.5k * 60% = 80.7k
        self.assertAlmostEqual(result["life_budget"], 134_500 * 0.60, places=0)


class TestStrategies(unittest.TestCase):
    def test_percentages_sum_to_100(self):
        for name, s in STRATEGIES.items():
            total = s["life_pct"] + s["prepayment_pct"] + s["savings_pct"]
            self.assertEqual(total, 100, f"Strategy {name} sums to {total}, not 100")


if __name__ == "__main__":
    unittest.main()
