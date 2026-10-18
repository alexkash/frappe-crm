import frappe
from frappe import _
from frappe.model.document import Document


class UABillingItem(Document):
	def validate(self):
		frappe.throw(_("Змінюйте позиції через договір, рахунок або акт"))

	before_update_after_submit = validate
	before_cancel = validate
	on_trash = validate
