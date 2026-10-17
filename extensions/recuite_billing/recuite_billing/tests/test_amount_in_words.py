import unittest
from decimal import Decimal

from recuite_billing.amount_in_words import amount_in_words_uk


class TestAmountInWords(unittest.TestCase):
	def test_ukrainian_amounts(self):
		for amount, expected in {
			"8820.00": "Вісім тисяч вісімсот двадцять гривень 00 копійок",
			"28866.67": "Двадцять вісім тисяч вісімсот шістдесят шість гривень 67 копійок",
			"0.00": "Нуль гривень 00 копійок",
			"1.01": "Одна гривня 01 копійка",
			"2.02": "Дві гривні 02 копійки",
			"5.05": "П'ять гривень 05 копійок",
			"11.11": "Одинадцять гривень 11 копійок",
			"21.21": "Двадцять одна гривня 21 копійка",
			"2000.00": "Дві тисячі гривень 00 копійок",
			"1000000.00": "Один мільйон гривень 00 копійок",
		}.items():
			with self.subTest(amount=amount):
				self.assertEqual(amount_in_words_uk(Decimal(amount)), expected)

	def test_rejects_invalid_or_unrounded_money(self):
		for amount in ["-1", "NaN", "Infinity", "1.001", "1000000000"]:
			with self.subTest(amount=amount), self.assertRaises(ValueError):
				amount_in_words_uk(Decimal(amount))
