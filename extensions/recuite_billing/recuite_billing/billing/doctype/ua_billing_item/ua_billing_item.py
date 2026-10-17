import frappe
from frappe.model.document import Document


class UABillingItem(Document):
	def validate(self):
		frappe.throw("Змінюйте позиції через договір, рахунок або акт")

	before_update_after_submit = validate
	before_cancel = validate
	on_trash = validate
