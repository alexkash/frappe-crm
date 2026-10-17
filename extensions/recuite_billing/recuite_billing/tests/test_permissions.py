import frappe
from frappe.tests.utils import FrappeTestCase

from recuite_billing.tests.helpers import as_user, contract, issuer, user


class TestBillingPermissions(FrappeTestCase):
	def test_cannot_take_over_an_existing_contract_by_spoofing_its_issuer(self):
		first, second = issuer(), issuer()
		doc = contract(owner=first)
		account = user("UA Billing Manager", second.name)
		payload = doc.as_dict()
		payload["issuer"] = second.name
		payload["bank_account"] = second.bank_accounts[0].name
		with as_user(account), self.assertRaises(frappe.PermissionError):
			frappe.get_doc(payload).save()
		self.assertEqual(frappe.db.get_value("UA Contract", doc.name, "issuer"), first.name)

	def test_billing_role_does_not_expose_companies_without_crm_access(self):
		doc = contract()
		account = user("UA Billing Reader", doc.issuer)
		frappe.get_doc("User", account).remove_roles("Sales User")
		frappe.clear_cache(user=account)
		with as_user(account):
			self.assertFalse(frappe.has_permission("CRM Organization", "read", doc=doc.organization))
			self.assertNotIn(doc.name, frappe.get_list("UA Contract", pluck="name"))
			self.assertFalse(frappe.has_permission("UA Contract", "read", doc=doc))

	def test_issuer_restrictions_apply_to_lists_and_document_reads(self):
		first, second = issuer(), issuer()
		allowed, forbidden = contract(owner=first), contract(owner=second)
		account = user(allowed_issuer=first.name)
		with as_user(account):
			visible = frappe.get_list("UA Contract", pluck="name")
			self.assertIn(allowed.name, visible)
			self.assertNotIn(forbidden.name, visible)
			self.assertFalse(frappe.has_permission("UA Contract", "read", doc=forbidden))
			self.assertTrue(frappe.has_permission("UA Contract", "read", doc=allowed))

	def test_reader_cannot_create_and_user_cannot_cancel(self):
		owner = issuer()
		reader = user("UA Billing Reader", owner.name)
		with as_user(reader):
			self.assertFalse(frappe.has_permission("UA Invoice", "create"))
			self.assertFalse(
				frappe.has_permission(
					"UA Print Asset",
					"write",
					doc=frappe.get_doc({"doctype": "UA Print Asset", "issuer": owner.name}),
				)
			)
		account = user(allowed_issuer=owner.name)
		with as_user(account):
			self.assertFalse(frappe.has_permission("UA Invoice", "cancel"))
