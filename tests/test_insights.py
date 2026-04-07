"""Tests for services/insights.py"""
import tests.conftest  # noqa: F401
import unittest

from services.insights import (
    daily_interest_cost,
    simulate_scenario,
    build_insight,
    build_insights,
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
        self.assertGreater(ins["savings"], 0)
        self.assertGreater(ins["daily_cost"], 0)
        self.assertIn("теряешь", ins["title"])
        self.assertIn("Добавь", ins["action"])

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
    def test_sorted_by_savings(self):
        obs = [
            {"id": 1, "name": "Маленький", "balance": 20_000, "rate": 10, "monthly_payment": 2_000},
            {"id": 2, "name": "Большой", "balance": 500_000, "rate": 25, "monthly_payment": 15_000},
            {"id": 3, "name": "Средний", "balance": 100_000, "rate": 18, "monthly_payment": 5_000},
        ]
        insights = build_insights(obs, top_n=3)
        self.assertEqual(len(insights), 3)
        # Sorted descending by savings
        for i in range(len(insights) - 1):
            self.assertGreaterEqual(insights[i]["savings"], insights[i + 1]["savings"])

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


if __name__ == "__main__":
    unittest.main()
