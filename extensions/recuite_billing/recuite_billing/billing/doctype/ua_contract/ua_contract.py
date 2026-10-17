from frappe.model.document import Document

from recuite_billing.documents import validate_contract


class UAContract(Document):
	def validate(self):
		validate_contract(self)
