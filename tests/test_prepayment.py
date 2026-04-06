"""Tests for services/prepayment.py — prepayment allocation logic."""
import unittest
from services.prepayment import normalize_obligation, choose_prepayment_target, allocate_prepayment


def _ob(name="Test", rate=15, balance=500_000, payment=15_000, action="medium",
        allowed=True, exclude=False, mode="auto", order=None, score=50):
    return {
        "name": name,
        "obligation_type": "loan",
        "rate": rate,
        "balance": balance,
        "monthly_payment": payment,
        "priority_score": score,
        "recommended_action": action,
        "prepayment_allowed": allowed,
        "exclude_from_prepayment": exclude,
        "manual_prepayment_mode": mode,
        "prepayment_order": order,
    }


class TestNormalizeObligation(unittest.TestCase):
    def test_converts_decimals(self):
        from decimal import Decimal
        ob = _ob()
        ob["balance"] = Decimal("500000.00")
        ob["rate"] = Decimal("15.0")
        result = normalize_obligation(ob)
        self.assertIsInstance(result["balance"], float)
        self.assertIsInstance(result["rate"], float)


class TestChoosePrepaymentTarget(unittest.TestCase):
    def test_picks_highest_rate(self):
        obs = [
            _ob("Low", rate=10, score=50, action="medium"),
            _ob("High", rate=25, score=100, action="fast"),
        ]
        target = choose_prepayment_target(obs)
        self.assertEqual(target["name"], "High")

    def test_respects_manual_order(self):
        obs = [
            _ob("Auto", rate=25, score=100, action="fast"),
            _ob("Manual", rate=10, score=50, action="medium", order=1),
        ]
        target = choose_prepayment_target(obs)
        self.assertEqual(target["name"], "Manual")

    def test_skips_excluded(self):
        obs = [
            _ob("Excluded", rate=25, action="fast", exclude=True),
            _ob("Included", rate=10, action="medium"),
        ]
        target = choose_prepayment_target(obs)
        self.assertEqual(target["name"], "Included")

    def test_skips_zero_balance(self):
        obs = [
            _ob("Zero", rate=25, balance=0, action="fast"),
            _ob("HasBalance", rate=10, balance=100_000, action="medium"),
        ]
        target = choose_prepayment_target(obs)
        self.assertEqual(target["name"], "HasBalance")

    def test_skips_skip_actions(self):
        obs = [
            _ob("Skip", rate=3, action="skip"),
            _ob("MinOnly", rate=8, action="minimum_only"),
        ]
        target = choose_prepayment_target(obs)
        self.assertIsNone(target)

    def test_no_candidates_returns_none(self):
        target = choose_prepayment_target([])
        self.assertIsNone(target)


class TestAllocatePrepayment(unittest.TestCase):
    def test_allocates_to_target(self):
        obs = [_ob("Target", rate=25, balance=200_000, action="fast")]
        result = allocate_prepayment(obs, 50_000)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["allocated_prepayment"], 50_000)

    def test_capped_by_balance(self):
        obs = [_ob("Target", rate=25, balance=10_000, action="fast")]
        result = allocate_prepayment(obs, 50_000)
        self.assertAlmostEqual(result[0]["allocated_prepayment"], 10_000)

    def test_zero_budget(self):
        obs = [_ob("Target", rate=25, action="fast")]
        result = allocate_prepayment(obs, 0)
        self.assertAlmostEqual(result[0]["allocated_prepayment"], 0)

    def test_negative_budget_treated_as_zero(self):
        obs = [_ob("Target", rate=25, action="fast")]
        result = allocate_prepayment(obs, -100)
        self.assertAlmostEqual(result[0]["allocated_prepayment"], 0)


if __name__ == "__main__":
    unittest.main()
