import unittest

from recuite_billing.formatting import date_uk, money_uk, quantity_uk, rate_uk


class TestPrintFormatting(unittest.TestCase):
	def test_preserves_ukrainian_money_rate_and_quantity_precision(self):
		self.assertEqual(money_uk("8820.00"), "8 820,00")
		self.assertEqual(money_uk("28866.67"), "28 866,67")
		self.assertEqual(rate_uk("0.1234"), "0,1234")
		self.assertEqual(rate_uk("1000"), "1 000,00")
		self.assertEqual(quantity_uk("1"), "1,000")
		self.assertEqual(quantity_uk("0.000001"), "0,000001")

	def test_ukrainian_dates_are_independent_of_ui_language(self):
		self.assertEqual(date_uk("2026-08-03"), "03 серпня 2026 року")
		self.assertEqual(date_uk("2025-08-04"), "04 серпня 2025 року")
		self.assertEqual(date_uk(None), "")
