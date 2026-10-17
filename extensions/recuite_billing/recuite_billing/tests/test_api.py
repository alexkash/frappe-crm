import frappe
from frappe.tests.utils import FrappeTestCase

from recuite_billing.tests.helpers import as_user, contract, user


class TestBillingAPI(FrappeTestCase):
	def test_capabilities_and_company_pagination_respect_permissions(self):
		from recuite_billing.api import get_capabilities, get_organization_documents

		source = contract()
		self.assertTrue(get_capabilities()["can_manage"])
		self.assertEqual(
			get_organization_documents(source.organization, "contracts")["rows"][0]["name"], source.name
		)
		for kind in ("File", "UA Contract", "invoices; drop table"):
			with self.assertRaises(frappe.ValidationError):
				get_organization_documents(source.organization, kind)
		with self.assertRaises(frappe.ValidationError):
			get_organization_documents(source.organization, "contracts", page_length=1000)
		account = user("UA Billing Reader")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": account,
				"allow": "CRM Organization",
				"for_value": source.organization,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=account)
		with as_user(account):
			self.assertTrue(get_capabilities()["can_read"])
			self.assertFalse(get_capabilities()["can_create"])

	def test_period_suggestion_advances_without_creating_a_document(self):
		from recuite_billing.api import create_invoice, get_period_suggestion

		source = contract(qty=3, cadence="Quarterly")
		period = get_period_suggestion("UA Contract", source.name)
		self.assertEqual((period["period_from"], period["period_to"]), ("2026-01-01", "2026-03-31"))
		create_invoice(source.name, **period)
		period = get_period_suggestion("UA Contract", source.name)
		self.assertEqual(period["period_from"], "2026-04-01")

	def test_monthly_act_suggestions_keep_contract_anchor_across_quarters(self):
		from unittest.mock import patch

		from recuite_billing.api import create_invoice, get_act_items, get_period_suggestion
		from recuite_billing.tests.helpers import pdf_bytes

		source = contract(qty=3, cadence="Quarterly")
		source.start_date, source.end_date = "2026-01-31", "2027-01-30"
		source.save()
		invoice = frappe.get_doc(
			"UA Invoice", create_invoice(source.name, "2026-04-30", "2026-07-30")["name"]
		)
		with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
			invoice.submit()
		period = get_period_suggestion("UA Invoice", invoice.name)
		self.assertEqual(period, {"period_from": "2026-04-30", "period_to": "2026-05-30"})
		self.assertEqual(get_act_items(invoice.name)[0]["qty"], "1.000000")
