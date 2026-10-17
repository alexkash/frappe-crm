import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	after_migrate()


def after_migrate():
	overrides = frappe.get_hooks("override_doctype_class").get("File", [])
	if any(path != "recuite_billing.overrides.file.BillingFile" for path in overrides):
		frappe.throw(
			"Інший застосунок перевизначає File: узгодьте обробку захищених вкладень перед встановленням billing"
		)
	for name in ("UA Billing User", "UA Billing Manager", "UA Billing Reader"):
		if not frappe.db.exists("Role", name):
			frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	organization = [
		("ua_legal_name", "Юридичне найменування", "Data"),
		("ua_registration_code", "ЄДРПОУ / РНОКПП", "Data"),
		("ua_legal_address", "Юридична адреса", "Small Text"),
		("ua_phone", "Телефон у документах", "Data"),
		("ua_vat_registered", "Платник ПДВ", "Check"),
		("ua_vat_number", "ІПН платника ПДВ", "Data"),
		("ua_income_tax_note", "Статус оподаткування прибутку", "Small Text"),
		("ua_signatory", "ПІБ підписанта", "Data"),
		("ua_signatory_position", "Посада підписанта", "Data"),
		("ua_iban", "IBAN", "Data"),
		("ua_bank_name", "Банк", "Data"),
		("ua_bank_mfo", "МФО", "Data"),
	]
	fields = [{"fieldname": name, "label": label, "fieldtype": kind} for name, label, kind in organization]
	products = [
		{
			"fieldname": "ua_item_type",
			"label": "Тип позиції",
			"fieldtype": "Select",
			"options": "Product\nService",
			"default": "Service",
		},
		{"fieldname": "ua_uom", "label": "Одиниця виміру", "fieldtype": "Data", "default": "послуга"},
		{
			"fieldname": "ua_vat_mode",
			"label": "Режим ПДВ",
			"fieldtype": "Select",
			"options": "Без ПДВ\nПДВ\nЗвільнено",
			"default": "Без ПДВ",
		},
		{
			"fieldname": "ua_vat_rate",
			"label": "Ставка ПДВ",
			"fieldtype": "Select",
			"options": "0\n7\n14\n20",
			"default": "0",
		},
		{
			"fieldname": "ua_vat_basis",
			"label": "Підстава нульової ставки / звільнення",
			"fieldtype": "Small Text",
		},
	]
	create_custom_fields({"CRM Organization": fields, "CRM Product": products}, update=True)
