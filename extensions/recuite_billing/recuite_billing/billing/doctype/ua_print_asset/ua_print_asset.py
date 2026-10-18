import frappe
from frappe import _
from frappe.model.document import Document


class UAPrintAsset(Document):
	def validate(self):
		if self.active and not self.image:
			frappe.throw(_("Додайте приватне зображення перед активацією"))
		if self.active and self.asset_type == "Signature" and not self.signatory:
			frappe.throw(_("Вкажіть ПІБ підписанта"))
		if self.image and not frappe.db.exists(
			"File",
			{
				"file_url": self.image,
				"is_private": 1,
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
			},
		):
			frappe.throw(_("Зображення має бути приватним вкладенням цієї картки"))
