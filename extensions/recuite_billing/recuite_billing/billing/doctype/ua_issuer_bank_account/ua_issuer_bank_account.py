import frappe
from frappe.model.document import Document


class UAIssuerBankAccount(Document):
	def validate(self):
		frappe.throw("Змінюйте банківські рахунки через картку нашого ФОП / ТОВ")

	before_update_after_submit = validate
	before_cancel = validate
	on_trash = validate
