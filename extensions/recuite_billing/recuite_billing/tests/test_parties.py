import copy
import unittest

from recuite_billing.parties import make_party_snapshot

IBAN = "UA273000010000000000000000001"


class TestPartySnapshots(unittest.TestCase):
	def setUp(self):
		self.issuer = {
			"name": "SUPPLIER",
			"issuer_type": "ФОП",
			"legal_name": "ФОП Тест",
			"registration_code": "0000000001",
			"legal_address": "Адреса виконавця",
			"signatory": "Тестовий Виконавець",
			"signatory_position": "ФОП",
			"vat_registered": 0,
			"income_tax_note": "Окремий статус оподаткування прибутку",
			"bank_accounts": [
				{"name": "bank-one", "iban": IBAN, "bank_name": "Тестовий банк", "is_default": 1}
			],
		}
		self.customer = {
			"name": "CUSTOMER",
			"organization_name": "CRM назва",
			"ua_legal_name": "ТОВ Тест",
			"ua_registration_code": "00000001",
			"ua_legal_address": "Адреса замовника",
			"ua_signatory": "Тестовий Замовник",
			"ua_signatory_position": "Директор",
		}

	def test_freezes_legal_names_bank_and_tax_note_without_changing_sources(self):
		original = copy.deepcopy(self.issuer)
		result = make_party_snapshot(self.issuer, self.customer, "bank-one", require_complete=True)
		self.assertEqual(result["issuer"]["registration_code"], "0000000001")
		self.assertEqual(result["issuer"]["income_tax_note"], "Окремий статус оподаткування прибутку")
		self.assertEqual(result["bank"]["bank_mfo"], "300001")
		self.assertEqual(result["bank"]["iban"], IBAN)
		self.assertTrue(result["payer_is_customer"])
		self.assertEqual(self.issuer, original)
		self.customer["ua_legal_name"] = "Нова назва"
		self.issuer["bank_accounts"][0]["iban"] = "changed"
		self.assertEqual(result["customer"]["legal_name"], "ТОВ Тест")
		self.assertEqual(result["bank"]["iban"], IBAN)

	def test_requires_legal_requisites_only_at_issuance(self):
		customer = {"name": "C", "organization_name": "CRM назва"}
		self.assertEqual(make_party_snapshot(self.issuer, customer)["customer"]["legal_name"], "CRM назва")
		with self.assertRaises(ValueError):
			make_party_snapshot(self.issuer, customer, require_complete=True)

	def test_rejects_foreign_bank_and_invalid_tax_profiles(self):
		with self.assertRaises(ValueError):
			make_party_snapshot(self.issuer, self.customer, "someone-elses-bank", require_complete=True)
		self.issuer["vat_registered"] = 1
		with self.assertRaises(ValueError):
			make_party_snapshot(self.issuer, self.customer, require_complete=True)

	def test_supports_a_distinct_payer_without_requiring_their_signature(self):
		payer = {"name": "PAYER", "ua_legal_name": "ТОВ Інший платник", "ua_registration_code": "00000002"}
		result = make_party_snapshot(self.issuer, self.customer, payer=payer, require_complete=True)
		self.assertFalse(result["payer_is_customer"])
		self.assertEqual(result["payer"]["legal_name"], "ТОВ Інший платник")
