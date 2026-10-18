import frappe
from frappe import _
from frappe.model.document import Document

from recuite_billing.documents import (
	cancel_invoice,
	forbid_final_update,
	issue_invoice,
	protect_final_deletion,
	record,
	require_new_draft,
	validate_invoice,
)


class UAInvoice(Document):
	def copy_attachments_from_amended_from(self):
		# A new edition gets its own archive; old PDFs/scans belong to the cancelled record.
		return

	def check_if_latest(self):
		if self.contract:
			record("UA Contract", self.contract, lock=True)
		if not self.is_new() and frappe.db.get_value(self.doctype, self.name, "contract") != self.contract:
			frappe.throw(_("Для іншого договору створіть нову чернетку рахунку"))
		return super().check_if_latest()

	def before_insert(self):
		require_new_draft(self)

	def validate(self):
		validate_invoice(self)

	def before_submit(self):
		issue_invoice(self)
		from recuite_billing.printing import archive_document

		archive_document(self)

	def before_cancel(self):
		cancel_invoice(self)

	def before_update_after_submit(self):
		forbid_final_update(self)

	def on_trash(self):
		protect_final_deletion(self)
