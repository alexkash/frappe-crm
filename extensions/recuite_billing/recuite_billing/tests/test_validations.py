import unittest

from recuite_billing.validations import validate_iban, validate_registration_code


class TestRequisites(unittest.TestCase):
	def test_iban_normalizes_spaces_and_validates_checksum(self):
		self.assertEqual(validate_iban("ua27 300001 0000000000000000001"), "UA273000010000000000000000001")
		for value in [
			"UA003000010000000000000000001",
			"GB273000010000000000000000001",
			"UA27",
			"https://example.invalid",
		]:
			with self.subTest(value=value), self.assertRaises(ValueError):
				validate_iban(value)

	def test_registration_codes_keep_leading_zeroes(self):
		self.assertEqual(validate_registration_code("00000001", "ТОВ"), "00000001")
		self.assertEqual(validate_registration_code("0000000001", "ФОП"), "0000000001")
		for value, kind in [("00000001", "ФОП"), ("0000000001", "ТОВ"), ("123", None), ("abcdefgh", None)]:
			with self.subTest(value=value, kind=kind), self.assertRaises(ValueError):
				validate_registration_code(value, kind)
