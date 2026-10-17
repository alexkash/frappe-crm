import calendar
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from recuite_billing.tests.helpers import contract, issuer, parallel_requests, product, user


class TestActs(FrappeTestCase):
	def setUp(self):
		from recuite_billing.tests.helpers import pdf_bytes

		super().setUp()
		mock = patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes())
		mock.start()
		self.addCleanup(mock.stop)

	def invoice(self, source=None, first="2026-01-01", last="2026-12-31"):
		from recuite_billing.api import create_invoice

		return frappe.get_doc(
			"UA Invoice", create_invoice((source or contract()).name, first, last)["name"]
		).submit()

	def draft(self, invoice, month, qty=1, *, row=None):
		from recuite_billing.api import create_act

		first = date(2026, month, 1).isoformat()
		last = date(2026, month, calendar.monthrange(2026, month)[1]).isoformat()
		result = create_act(
			invoice.name, first, last, [{"invoice_item": row or invoice.items[0].name, "qty": qty}]
		)
		return frappe.get_doc("UA Act", result["name"])

	def test_annual_prepayment_closes_with_twelve_monthly_acts(self):
		invoice = self.invoice()
		acts = [self.draft(invoice, month).submit() for month in range(1, 13)]
		self.assertEqual([act.grand_total for act in acts], [1000] * 12)
		self.assertEqual(sum(act.grand_total for act in acts), invoice.grand_total)
		self.assertEqual({act.invoice for act in acts}, {invoice.name})

	def test_quarterly_invoices_have_three_monthly_acts_each(self):
		source = contract(qty=3, cadence="Quarterly")
		for quarter in range(4):
			first_month, last_month = quarter * 3 + 1, quarter * 3 + 3
			first = date(2026, first_month, 1).isoformat()
			last = date(2026, last_month, calendar.monthrange(2026, last_month)[1]).isoformat()
			invoice = self.invoice(source, first, last)
			acts = [self.draft(invoice, month).submit() for month in range(first_month, last_month + 1)]
			self.assertEqual(sum(act.grand_total for act in acts), 3000)
			self.assertEqual(invoice.grand_total, 3000)

	def test_rejects_draft_invoice_foreign_rows_and_dates(self):
		from recuite_billing.api import create_invoice

		source = contract()
		invoice = frappe.get_doc(
			"UA Invoice", create_invoice(source.name, "2026-01-01", "2026-12-31")["name"]
		)
		with self.assertRaises(frappe.ValidationError):
			self.draft(invoice, 1)
		invoice.submit()
		other = self.invoice()
		with self.assertRaises(frappe.ValidationError):
			self.draft(invoice, 1, row=other.items[0].name)
		quarter = self.invoice(contract(qty=3, cadence="Quarterly"), "2026-01-01", "2026-03-31")
		with self.assertRaises(frappe.ValidationError):
			self.draft(quarter, 4)

	def test_act_prices_and_parties_come_from_the_invoice(self):
		invoice = self.invoice()
		act = self.draft(invoice, 1)
		act.items[0].net_rate = 1
		act.save()
		self.assertEqual(act.items[0].net_rate, 1000)
		self.assertEqual(act.grand_total, 1000)
		act.issuer = issuer().name
		with self.assertRaises(frappe.ValidationError):
			act.save()

	def test_checks_each_row_and_allows_a_subset(self):
		source = contract(qty=1)
		second = product()
		source.append(
			"items",
			{
				"product_code": second.name,
				"product_name": second.product_name,
				"qty": 5,
				"net_rate": 200,
				"vat_mode": "Без ПДВ",
				"vat_rate": "0",
				"uom": "міс.",
			},
		)
		source.save()
		invoice = self.invoice(source)
		with self.assertRaises(frappe.ValidationError):
			self.draft(invoice, 1, qty=2)
		act = self.draft(invoice, 1, qty=1).submit()
		self.assertEqual(act.grand_total, 1000)
		self.assertEqual(len(act.items), 1)

	def test_cancel_frees_remainder_and_blocks_invoice_cancel_until_then(self):
		invoice = self.invoice()
		act = self.draft(invoice, 1).submit()
		with self.assertRaises(frappe.ValidationError):
			invoice.cancel()
		act.cancel()
		replacement = self.draft(invoice, 1).submit()
		self.assertNotEqual(act.print_number, replacement.print_number)
		replacement.cancel()
		invoice.reload()
		invoice.cancel()
		with self.assertRaises(frappe.ValidationError):
			self.draft(invoice, 2)

	def test_rounding_allocation_is_preserved_in_real_documents(self):
		owner = issuer(vat=True)
		source = contract(owner=owner, qty=3)
		source.items[0].net_rate, source.items[0].vat_mode, source.items[0].vat_rate = 0.03, "ПДВ", "20"
		source.save()
		invoice = self.invoice(source)
		acts = [self.draft(invoice, month).submit() for month in (1, 2, 3)]
		self.assertEqual(
			[Decimal(str(act.vat_total)) for act in acts], [Decimal("0.01"), Decimal("0.00"), Decimal("0.01")]
		)
		self.assertEqual(sum(Decimal(str(act.grand_total)) for act in acts), Decimal("0.11"))
		from recuite_billing.printing import render_html

		self.assertIn("ПДВ -0,01 грн", render_html(acts[1]))

	def test_duplicate_period_is_idempotent_and_does_not_inherit_signature_flags(self):
		from recuite_billing.api import create_act, create_invoice
		from recuite_billing.tests.test_print_assets import asset, png_bytes

		source = contract()
		invoice = frappe.get_doc(
			"UA Invoice", create_invoice(source.name, "2026-01-01", "2026-12-31")["name"]
		)
		signature = asset(frappe.get_doc("UA Issuer", source.issuer))
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "signature.png",
				"content": png_bytes(),
				"is_private": 1,
				"attached_to_doctype": signature.doctype,
				"attached_to_name": signature.name,
			}
		).insert()
		signature.image, signature.active = file.file_url, 1
		signature.save()
		invoice.print_signature, invoice.signature_asset = 1, signature.name
		invoice.submit()
		act = self.draft(invoice, 1)
		self.assertFalse(act.print_signature)
		self.assertFalse(act.print_stamp)
		self.assertFalse(act.signature_asset)
		result = create_act(
			invoice.name, "2026-01-01", "2026-01-31", [{"invoice_item": invoice.items[0].name, "qty": 1}]
		)
		self.assertEqual(result, {"name": act.name, "existing": True})

	def test_parallel_submits_cannot_exceed_one_remaining_quantity(self):
		invoice = self.invoice(contract(qty=1))
		first, second = self.draft(invoice, 1), self.draft(invoice, 2)
		account = user(allowed_issuer=invoice.issuer)

		def submit(name):
			try:
				frappe.get_doc("UA Act", name).submit()
				return True
			except frappe.ValidationError:
				frappe.db.rollback()
				return False

		result = parallel_requests(
			[lambda: submit(first.name), lambda: submit(second.name)],
			account=account,
			snapshot_contract=invoice.contract,
		)
		self.assertEqual(sorted(result), [False, True])
		self.assertEqual(frappe.db.count("UA Act", {"invoice": invoice.name, "docstatus": 1}), 1)

	def test_invoice_cancel_racing_act_submit_has_one_valid_outcome(self):
		invoice = self.invoice()
		act = self.draft(invoice, 1)
		account = user("UA Billing Manager", invoice.issuer)

		def change(doctype, name, operation):
			try:
				getattr(frappe.get_doc(doctype, name), operation)()
				return True
			except frappe.ValidationError:
				frappe.db.rollback()
				return False

		parallel_requests(
			[
				lambda: change("UA Act", act.name, "submit"),
				lambda: change("UA Invoice", invoice.name, "cancel"),
			],
			account=account,
			snapshot_contract=invoice.contract,
		)
		state = (
			frappe.db.get_value("UA Invoice", invoice.name, "docstatus"),
			frappe.db.get_value("UA Act", act.name, "docstatus"),
		)
		self.assertIn(state, {(1, 1), (2, 0)})

	def test_act_cancel_racing_another_submit_preserves_remainder(self):
		invoice = self.invoice(contract(qty=1))
		first, second = self.draft(invoice, 1), self.draft(invoice, 2)
		first.submit()
		account = user("UA Billing Manager", invoice.issuer)

		def change(name, operation):
			try:
				getattr(frappe.get_doc("UA Act", name), operation)()
				return True
			except frappe.ValidationError:
				frappe.db.rollback()
				return False

		parallel_requests(
			[lambda: change(first.name, "cancel"), lambda: change(second.name, "submit")],
			account=account,
			snapshot_contract=invoice.contract,
		)
		self.assertEqual(frappe.db.get_value("UA Act", first.name, "docstatus"), 2)
		self.assertLessEqual(frappe.db.count("UA Act", {"invoice": invoice.name, "docstatus": 1}), 1)
