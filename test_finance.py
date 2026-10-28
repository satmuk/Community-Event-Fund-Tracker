import unittest
from decimal import Decimal

from finance import calculate_summary, parse_transactions, suggest_category


class FinanceTests(unittest.TestCase):
    def test_parse_csv_with_signs_and_categories(self):
        rows = parse_transactions(
            "date,description,amount\n"
            "2026-01-15,GoFundMe donation,250.00\n"
            "02/02/2026,Tent rental,-400.00\n"
        )
        self.assertEqual(rows[0].type, "income")
        self.assertEqual(rows[0].category, "Donations")
        self.assertEqual(rows[1].type, "expense")
        self.assertEqual(rows[1].category, "Tent & equipment rental")
        self.assertEqual(rows[1].amount, Decimal("400.00"))

    def test_calculates_only_2026_transactions_and_includes_other_income(self):
        rows = parse_transactions(
            "date,description,amount,type\n"
            "2025-12-31,Prior-year purchase,999,expense\n"
            "2026-01-15,GoFundMe donation,250,income\n"
            "2026-02-01,Raffle proceeds,50,income\n"
            "2026-02-02,Tent rental,400,expense\n"
        )
        summary = calculate_summary(rows, Decimal("1000"))
        self.assertEqual(summary["donations"], Decimal("250"))
        self.assertEqual(summary["other_income"], Decimal("50"))
        self.assertEqual(summary["expenses"], Decimal("400"))
        self.assertEqual(summary["ending_reserve"], Decimal("900"))

    def test_rejects_missing_required_columns(self):
        with self.assertRaisesRegex(ValueError, "Missing: amount"):
            parse_transactions("date,description\n2026-01-01,Donation\n")

    def test_rejects_category_that_conflicts_with_transaction_type(self):
        with self.assertRaisesRegex(ValueError, "does not match type"):
            parse_transactions(
                "date,description,amount,type,category\n"
                "2026-01-01,GoFundMe donation,20,income,Food\n"
            )

    def test_suggest_category_for_common_event_items(self):
        self.assertEqual(suggest_category("Truck rental", "expense"), "Truck & transportation")
        self.assertEqual(suggest_category("Plates and spoons", "expense"), "Plates & utensils")


if __name__ == "__main__":
    unittest.main()
