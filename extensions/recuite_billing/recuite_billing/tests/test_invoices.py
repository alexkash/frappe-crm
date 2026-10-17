import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from recuite_billing.tests.helpers import contract, issuer, organization, parallel_requests, user


class TestInvoices(FrappeTestCase):
	def setUp(self):
		from recuite_billing.tests.helpers import pdf_bytes

		super().setUp()
		mock = patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes())
		mock.start()
		self.addCleanup(mock.stop)

	def test_locking_read_compatibility_does_not_commit_callers_changes_and_restores_mode(self):
		frappe.db.rollback()
		initial = frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0]
		global_mode = frappe.db.sql("SELECT @@GLOBAL.innodb_snapshot_isolation")[0][0]
		source = contract()
		result = self.create(source)
		self.assertEqual(frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0], 0)
		frappe.db.rollback()
		self.assertFalse(frappe.db.exists("UA Invoice", result["name"]))
		self.assertFalse(frappe.db.exists("UA Contract", source.name))
		self.assertEqual(frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0], initial)
		self.assertEqual(frappe.db.sql("SELECT @@GLOBAL.innodb_snapshot_isolation")[0][0], global_mode)

	def test_locking_read_mode_is_restored_after_commit(self):
		frappe.db.rollback()
		initial = frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0]
		self.create(contract())
		frappe.db.commit()
		self.assertEqual(frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0], initial)

	def test_preconfigured_session_mode_is_not_overridden(self):
		frappe.db.rollback()
		initial = frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0]
		frappe.db.sql("SET SESSION innodb_snapshot_isolation=OFF")
		try:
			self.create(contract())
			frappe.db.rollback()
			self.assertEqual(frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0], 0)
		finally:
			frappe.db.sql("SET SESSION innodb_snapshot_isolation=" + ("ON" if initial else "OFF"))

	def test_invoice_child_identity_and_aggregate_cannot_be_bypassed(self):
		first = frappe.get_doc("UA Invoice", self.create(contract())["name"])
		second = frappe.get_doc("UA Invoice", self.create(contract())["name"])
		payload = second.as_dict()
		payload["items"][0]["name"] = first.items[0].name
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(payload).save()
		row = frappe.get_doc("UA Billing Item", first.items[0].name)
		row.qty = 100
		with self.assertRaises(frappe.ValidationError):
			row.save()
		self.assertEqual(frappe.db.get_value("UA Billing Item", row.name, "qty"), 12)

	def test_year_change_starts_a_new_series(self):
		source = contract()
		first = frappe.get_doc("UA Invoice", self.create(source)["name"])
		first.posting_date = "2026-12-31"
		first.submit()
		first.cancel()
		second = frappe.get_doc("UA Invoice", self.create(source)["name"])
		second.posting_date = "2027-01-01"
		second.submit()
		self.assertTrue(first.print_number.endswith("-2026-00001"))
		self.assertTrue(second.print_number.endswith("-2027-00001"))

	def test_direct_insert_cannot_bypass_period_reservation_or_draft_state(self):
		source = contract()
		doc = frappe.get_doc("UA Invoice", self.create(source)["name"])
		with self.assertRaises(frappe.ValidationError):
			frappe.copy_doc(doc).insert()
		for state in (1, 2):
			copy = frappe.copy_doc(doc)
			copy.contract, copy.docstatus = None, state
			with self.assertRaises(frappe.ValidationError):
				copy.insert()

	def test_concurrent_generation_returns_one_draft_despite_preexisting_snapshots(self):
		source = contract()
		account = user(allowed_issuer=source.issuer)
		results = parallel_requests(
			[lambda: self.create(source), lambda: self.create(source)],
			account=account,
			snapshot_contract=source.name,
		)
		self.assertEqual(results[0]["name"], results[1]["name"])
		self.assertEqual(sorted(result["existing"] for result in results), [False, True])
		self.assertEqual(frappe.db.count("UA Invoice", {"contract": source.name}), 1)

	def test_concurrent_issuance_uses_unique_numbers_for_one_issuer(self):
		owner = issuer()
		first, second = contract(owner=owner), contract(owner=owner)
		ids = [self.create(first)["name"], self.create(second)["name"]]
		account = user(allowed_issuer=owner.name)
		results = parallel_requests(
			[
				lambda: frappe.get_doc("UA Invoice", ids[0]).submit().print_number,
				lambda: frappe.get_doc("UA Invoice", ids[1]).submit().print_number,
			],
			account=account,
			snapshot_contract=first.name,
		)
		self.assertEqual({value[-5:] for value in results}, {"00001", "00002"})

	def create(self, source, first="2026-01-01", last="2026-12-31"):
		from recuite_billing.api import create_invoice

		return create_invoice(source.name, first, last)

	def test_creates_company_invoice_without_a_deal_and_reuses_the_period(self):
		source = contract()
		result = self.create(source)
		doc = frappe.get_doc("UA Invoice", result["name"])
		self.assertFalse(result["existing"])
		self.assertEqual(doc.organization, source.organization)
		self.assertEqual(doc.issuer, source.issuer)
		self.assertFalse(doc.deal)
		self.assertEqual(doc.grand_total, 12000)
		self.assertEqual(self.create(source), {"name": doc.name, "existing": True})
		self.assertEqual(frappe.db.count("UA Invoice", {"contract": source.name}), 1)

	def test_rejects_foreign_parties_and_freezes_used_contract_identity(self):
		source = contract()
		doc = frappe.get_doc("UA Invoice", self.create(source)["name"])
		other = issuer()
		doc.issuer, doc.bank_account = other.name, other.bank_accounts[0].name
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		source.issuer, source.bank_account = other.name, other.bank_accounts[0].name
		with self.assertRaises(frappe.ValidationError):
			source.save()

	def test_prevents_overlap_and_releases_a_changed_draft_period(self):
		source = contract(qty=3, cadence="Quarterly")
		doc = frappe.get_doc("UA Invoice", self.create(source, "2026-01-01", "2026-03-31")["name"])
		doc.period_from, doc.period_to = "2026-04-01", "2026-06-30"
		doc.save()
		new = self.create(source, "2026-01-01", "2026-03-31")
		self.assertNotEqual(new["name"], doc.name)
		with self.assertRaises(frappe.ValidationError):
			self.create(source, "2026-02-01", "2026-04-30")
		with self.assertRaises(frappe.ValidationError):
			self.create(source, "2025-12-01", "2025-12-31")

	def test_partial_period_requires_confirmation_before_issue(self):
		source = contract()
		source.end_date = "2026-12-15"
		source.save()
		doc = frappe.get_doc("UA Invoice", self.create(source, "2026-01-01", "2026-12-15")["name"])
		self.assertTrue(doc.requires_partial_confirmation)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		doc.reload()
		doc.partial_period_confirmed = 1
		doc.submit()
		self.assertEqual(doc.grand_total, 12000)
		self.assertTrue(doc.print_number)

	def test_final_snapshot_and_number_survive_profile_and_catalog_updates(self):
		source = contract()
		doc = frappe.get_doc("UA Invoice", self.create(source)["name"])
		doc.submit()
		snapshot, number = doc.party_snapshot, doc.print_number
		company = frappe.get_doc("CRM Organization", source.organization)
		company.ua_legal_name = "Нова юридична назва"
		company.save()
		product = frappe.get_doc("CRM Product", source.items[0].product_code)
		product.standard_rate = 9999
		product.save()
		doc.reload()
		self.assertEqual(doc.party_snapshot, snapshot)
		self.assertEqual(json.loads(snapshot)["customer"]["legal_name"], "Тестовий замовник")
		self.assertEqual(doc.items[0].net_rate, 1000)
		self.assertEqual(doc.print_number, number)
		doc.items[0].net_rate = 2000
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_incomplete_profiles_can_have_drafts_but_cannot_issue(self):
		source = contract()
		company = frappe.get_doc("CRM Organization", source.organization)
		company.ua_registration_code = ""
		company.save()
		doc = frappe.get_doc("UA Invoice", self.create(source)["name"])
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_new_invoices_reject_disabled_products_and_closed_contracts(self):
		source = contract(qty=3, cadence="Quarterly")
		draft = frappe.get_doc("UA Invoice", self.create(source, "2026-01-01", "2026-03-31")["name"])
		product = frappe.get_doc("CRM Product", source.items[0].product_code)
		product.standard_rate, product.disabled = 9999, 1
		product.save()
		draft.reload()
		self.assertEqual(draft.items[0].net_rate, 1000)
		with self.assertRaises(frappe.ValidationError):
			self.create(source, "2026-04-01", "2026-06-30")
		source.disabled = 1
		source.save()
		with self.assertRaises(frappe.ValidationError):
			self.create(source, "2026-07-01", "2026-09-30")

	def test_standalone_invoice_still_requires_a_company_and_rejects_supplied_number(self):
		source = contract()
		values = {
			"doctype": "UA Invoice",
			"issuer": source.issuer,
			"bank_account": source.bank_account,
			"posting_date": "2026-01-01",
			"period_from": "2026-01-01",
			"period_to": "2026-01-31",
			"items": [
				{
					field: source.items[0].get(field)
					for field in (
						"product_code",
						"product_name",
						"uom",
						"qty",
						"net_rate",
						"vat_mode",
						"vat_rate",
					)
				}
			],
		}
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(values).insert()
		values["organization"] = source.organization
		doc = frappe.get_doc(values).insert()
		self.assertFalse(doc.contract)
		doc.print_number = "FORGED"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_cancelled_numbers_are_not_reused_and_different_issuers_have_separate_series(self):
		source = contract()
		first = frappe.get_doc("UA Invoice", self.create(source)["name"]).submit()
		number = first.print_number
		first.cancel()
		second = frappe.get_doc("UA Invoice", self.create(source)["name"]).submit()
		self.assertNotEqual(number, second.print_number)
		self.assertTrue(second.print_number.endswith("00002"))
		other = contract(owner=issuer())
		third = frappe.get_doc("UA Invoice", self.create(other)["name"]).submit()
		self.assertTrue(third.print_number.endswith("00001"))

	def test_different_payer_is_saved_separately(self):
		source = contract()
		doc = frappe.get_doc("UA Invoice", self.create(source)["name"])
		payer = organization()
		payer.ua_legal_name = "Інший платник"
		payer.save()
		doc.payer_organization = payer.name
		doc.submit()
		snapshot = json.loads(doc.party_snapshot)
		self.assertFalse(snapshot["payer_is_customer"])
		self.assertEqual(snapshot["payer"]["legal_name"], "Інший платник")
