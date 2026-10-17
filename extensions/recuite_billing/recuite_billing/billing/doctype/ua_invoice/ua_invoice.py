from frappe.model.document import Document

from recuite_billing.documents import (
	cancel_invoice,
	forbid_final_update,
	issue_invoice,
	protect_final_deletion,
	require_new_draft,
	validate_invoice,
)


class UAInvoice(Document):
	def before_insert(self):
		require_new_draft(self)

	def validate(self):
		validate_invoice(self)

	def before_submit(self):
		issue_invoice(self)

	def before_cancel(self):
		cancel_invoice(self)

	def before_update_after_submit(self):
		forbid_final_update(self)

	def on_trash(self):
		protect_final_deletion(self)
