"""Tests for services/format.py — shared compact formatters."""
import tests.conftest  # noqa: F401
import unittest

from services.format import fmt_amount_compact


class TestFmtAmountCompact(unittest.TestCase):
    def test_zero_and_negative(self):
        self.assertEqual(fmt_amount_compact(0), "0 ₽")
        self.assertEqual(fmt_amount_compact(-100), "0 ₽")

    def test_none(self):
        self.assertEqual(fmt_amount_compact(None), "0 ₽")  # type: ignore[arg-type]

    def test_under_thousand(self):
        self.assertEqual(fmt_amount_compact(999), "999 ₽")

    def test_thousands(self):
        self.assertEqual(fmt_amount_compact(12_345), "12 тыс ₽")
        self.assertEqual(fmt_amount_compact(1_500), "2 тыс ₽")  # round to nearest

    def test_millions(self):
        self.assertEqual(fmt_amount_compact(1_500_000), "1.5 млн ₽")
        self.assertEqual(fmt_amount_compact(2_000_000), "2.0 млн ₽")


class TestDebtPriorityAlias(unittest.TestCase):
    def test_alias_still_works(self):
        # Backward-compat: debt_priority._fmt_amount must remain importable.
        from services.debt_priority import _fmt_amount
        self.assertEqual(_fmt_amount(1_500), "2 тыс ₽")


if __name__ == "__main__":
    unittest.main()
