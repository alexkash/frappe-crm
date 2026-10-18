import frappe
from frappe.tests.utils import FrappeTestCase

from recuite_billing.tests.helpers import as_user, contract, issuer, pdf_bytes, user


class TestContractFiles(FrappeTestCase):
	def test_contract_attachment_cannot_be_public(self):
		doc = contract()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "contract.pdf",
					"content": pdf_bytes(),
					"is_private": 0,
					"attached_to_doctype": "UA Contract",
					"attached_to_name": doc.name,
				}
			).insert()

	def test_file_owner_loses_download_after_issuer_access_is_revoked(self):
		first, second = issuer(), issuer()
		doc = contract(owner=first)
		account = user("UA Billing Manager", second.name)
		attachment = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "contract.pdf",
				"content": pdf_bytes(),
				"is_private": 1,
				"attached_to_doctype": "UA Contract",
				"attached_to_name": doc.name,
			}
		).insert()
		attachment.db_set("owner", account)
		with as_user(account):
			self.assertFalse(attachment.is_downloadable())
			self.assertFalse(frappe.has_permission("File", "read", doc=attachment))
			self.assertNotIn(attachment.name, frappe.get_list("File", pluck="name"))
