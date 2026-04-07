"""Tests for services/insights.py"""
import tests.conftest  # noqa: F401
import unittest

from services.insights import (
    daily_interest_cost,
    simulate_scenario,
    build_insight,
    build_insights,
    temperature,
    cost_per_100k_per_month,
    cost_of_inaction_year,
    most_expensive_debt,
)


class TestDailyCost(unittest.TestCase):
    def test_credit_card(self):
        # 80k @ 28% → ~61.4 ₽/day
        d = daily_interest_cost(80_000, 28)
        self.assertAlmostEqual(d, 80_000 * 0.28 / 365, places=2)

    def test_zero_balance(self):
        self.assertEqual(daily_interest_cost(0, 28), 0.0)

    def test_zero_rate(self):
        self.assertEqual(daily_interest_cost(80_000, 0), 0.0)


class TestSimulateScenario(unittest.TestCase):
    def test_extra_payment_saves_money(self):
        ob = {"balance": 80_000, "rate": 28, "monthly_payment": 5_000}
        sc = simulate_scenario(ob, 2_000)
        self.assertIsNotNone(sc)
        self.assertGreater(sc["savings"], 0)
        self.assertGreater(sc["months_saved"], 0)
        self.assertEqual(sc["new_payment"], 7_000)

    def test_zero_balance_returns_none(self):
        ob = {"balance": 0, "rate": 28, "monthly_payment": 5_000}
        self.assertIsNone(simulate_scenario(ob, 2_000))

    def test_payment_doesnt_cover_interest(self):
        # 1M @ 50%, paying only 100 ₽/mo → never pays off
        ob = {"balance": 1_000_000, "rate": 50, "monthly_payment": 100}
        self.assertIsNone(simulate_scenario(ob, 500))


class TestBuildInsight(unittest.TestCase):
    def test_credit_card_insight(self):
        ob = {
            "id": 1, "name": "Кредитка", "balance": 80_000,
            "rate": 28, "monthly_payment": 5_000,
        }
        ins = build_insight(ob)
        self.assertIsNotNone(ins)
        self.assertEqual(ins["name"], "Кредитка")
        self.assertEqual(ins["temperature"], "hot")
        self.assertGreater(ins["savings"], 0)
        self.assertGreater(ins["daily_cost"], 0)
        self.assertGreater(ins["cost_per_100k"], 0)
        self.assertIn("дорог", ins["title"].lower())
        self.assertIn("Добавь", ins["action"])

    def test_mortgage_not_called_expensive(self):
        ob = {"id": 1, "name": "Ипотека", "balance": 4_000_000,
              "rate": 5, "monthly_payment": 30_000, "obligation_type": "mortgage"}
        ins = build_insight(ob)
        self.assertIsNotNone(ins)
        self.assertEqual(ins["temperature"], "mortgage")
        self.assertNotIn("теряешь", ins["title"].lower())
        self.assertIn("дешёв", ins["title"].lower() + ins["subtitle"].lower())

    def test_no_balance_returns_none(self):
        ob = {"id": 1, "name": "X", "balance": 0, "rate": 10, "monthly_payment": 1000}
        self.assertIsNone(build_insight(ob))

    def test_picks_best_scenario(self):
        ob = {"id": 1, "name": "Долг", "balance": 200_000, "rate": 20, "monthly_payment": 10_000}
        ins = build_insight(ob)
        self.assertIsNotNone(ins)
        # The best scenario should have the highest savings of all SCENARIO_AMOUNTS
        from services.insights import SCENARIO_AMOUNTS, simulate_scenario as sc_fn
        all_savings = []
        for e in SCENARIO_AMOUNTS:
            sc = sc_fn(ob, e)
            if sc:
                all_savings.append(sc["savings"])
        self.assertAlmostEqual(ins["savings"], max(all_savings), places=2)


class TestBuildInsights(unittest.TestCase):
    def test_sorted_by_rate_not_savings(self):
        # KEY FIX: high-balance low-rate mortgage must NOT outrank a credit card
        obs = [
            {"id": 1, "name": "Ипотека", "balance": 4_000_000, "rate": 5,
             "monthly_payment": 30_000, "obligation_type": "mortgage"},
            {"id": 2, "name": "Кредитка", "balance": 80_000, "rate": 28, "monthly_payment": 5_000},
            {"id": 3, "name": "Кредит", "balance": 300_000, "rate": 18, "monthly_payment": 10_000},
        ]
        insights = build_insights(obs, top_n=3)
        self.assertEqual(len(insights), 3)
        # First must be the credit card (highest rate)
        self.assertEqual(insights[0]["name"], "Кредитка")
        self.assertEqual(insights[1]["name"], "Кредит")
        self.assertEqual(insights[2]["name"], "Ипотека")
        for i in range(len(insights) - 1):
            self.assertGreaterEqual(insights[i]["rate"], insights[i + 1]["rate"])

    def test_top_n_limits(self):
        obs = [
            {"id": i, "name": f"D{i}", "balance": 100_000, "rate": 20, "monthly_payment": 5_000}
            for i in range(10)
        ]
        insights = build_insights(obs, top_n=3)
        self.assertEqual(len(insights), 3)

    def test_empty_list(self):
        self.assertEqual(build_insights([]), [])

    def test_skips_invalid(self):
        obs = [
            {"id": 1, "name": "OK", "balance": 80_000, "rate": 28, "monthly_payment": 5_000},
            {"id": 2, "name": "Empty", "balance": 0, "rate": 10, "monthly_payment": 1000},
        ]
        insights = build_insights(obs)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["name"], "OK")


class TestTemperature(unittest.TestCase):
    def test_hot(self):
        self.assertEqual(temperature(28), "hot")
        self.assertEqual(temperature(20), "hot")
    def test_warm(self):
        self.assertEqual(temperature(15), "warm")
        self.assertEqual(temperature(12), "warm")
    def test_cold(self):
        self.assertEqual(temperature(8), "cold")
    def test_mortgage_overrides(self):
        # Even at hot rate, mortgage gets its own bucket
        self.assertEqual(temperature(25, "mortgage"), "mortgage")
        self.assertEqual(temperature(5, "mortgage"), "mortgage")


class TestCostPer100k(unittest.TestCase):
    def test_credit_card_27pct(self):
        # 27% / 12 * 1000 = 2250
        self.assertAlmostEqual(cost_per_100k_per_month(27), 2250, places=2)
    def test_mortgage_5pct(self):
        # 5 * 1000 / 12 ≈ 416.67
        self.assertAlmostEqual(cost_per_100k_per_month(5), 416.666, places=2)
    def test_credit_card_5x_more_than_mortgage(self):
        # The crucial product comparison
        cc = cost_per_100k_per_month(27)
        mortgage = cost_per_100k_per_month(5)
        self.assertAlmostEqual(cc / mortgage, 27 / 5, places=2)


class TestCostOfInaction(unittest.TestCase):
    def test_excludes_mortgage(self):
        obs = [
            {"name": "Ипотека", "balance": 4_000_000, "rate": 5,
             "monthly_payment": 30_000, "obligation_type": "mortgage"},
            {"name": "Кредитка", "balance": 80_000, "rate": 28, "monthly_payment": 5_000},
        ]
        result = cost_of_inaction_year(obs)
        # Mortgage excluded
        self.assertEqual(len(result["breakdown"]), 1)
        self.assertEqual(result["breakdown"][0]["name"], "Кредитка")
        # Credit card year interest ≈ 80000 * 0.28 = 22400
        self.assertAlmostEqual(result["total_year_interest"], 22_400, places=0)

    def test_excludes_cheap(self):
        obs = [{"name": "Дешёвый", "balance": 100_000, "rate": 8, "monthly_payment": 5_000}]
        result = cost_of_inaction_year(obs)
        self.assertEqual(result["total_year_interest"], 0)

    def test_empty(self):
        self.assertEqual(cost_of_inaction_year([])["total_year_interest"], 0)


class TestMostExpensive(unittest.TestCase):
    def test_picks_highest_rate(self):
        obs = [
            {"name": "Ипотека", "balance": 4_000_000, "rate": 5, "monthly_payment": 30_000},
            {"name": "Кредитка", "balance": 80_000, "rate": 28, "monthly_payment": 5_000},
            {"name": "Кредит", "balance": 300_000, "rate": 18, "monthly_payment": 10_000},
        ]
        result = most_expensive_debt(obs)
        self.assertEqual(result["name"], "Кредитка")
        self.assertAlmostEqual(result["multiplier_vs_cheapest"], 28 / 5, places=2)

    def test_empty(self):
        self.assertIsNone(most_expensive_debt([]))


if __name__ == "__main__":
    unittest.main()
