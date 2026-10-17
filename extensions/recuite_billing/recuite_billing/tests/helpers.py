from contextlib import contextmanager
from io import BytesIO

import frappe

IBAN = "UA273000010000000000000000001"


def pdf_bytes():
	from pypdf import PdfWriter

	buffer = BytesIO()
	writer = PdfWriter()
	writer.add_blank_page(width=595, height=842)
	writer.write(buffer)
	return buffer.getvalue()


def issuer(vat=False):
	return frappe.get_doc(
		{
			"doctype": "UA Issuer",
			"issuer_code": "TEST-" + frappe.generate_hash(length=8),
			"issuer_type": "ТОВ" if vat else "ФОП",
			"legal_name": "Тестовий виконавець",
			"registration_code": "00000000" if vat else "0000000000",
			"legal_address": "Тестова адреса",
			"phone": "+380000000000",
			"vat_registered": int(vat),
			"vat_number": "000000000000" if vat else "",
			"signatory": "Тестовий Підписант",
			"signatory_position": "Директор",
			"place_of_issue": "м. Київ",
			"bank_accounts": [{"iban": IBAN, "bank_name": "Тестовий банк", "is_default": 1}],
		}
	).insert()


def organization():
	return frappe.get_doc(
		{
			"doctype": "CRM Organization",
			"organization_name": "_Test UA " + frappe.generate_hash(length=8),
			"currency": "UAH",
			"exchange_rate": 1,
			"ua_legal_name": "Тестовий замовник",
			"ua_registration_code": "00000001",
			"ua_legal_address": "Тестова адреса замовника",
			"ua_signatory": "Тестовий Замовник",
			"ua_signatory_position": "Директор",
		}
	).insert()


def product():
	return frappe.get_doc(
		{
			"doctype": "CRM Product",
			"product_code": "_Test UA " + frappe.generate_hash(length=8),
			"product_name": "Технічна підтримка",
			"standard_rate": 1000,
			"ua_uom": "міс.",
			"ua_item_type": "Service",
			"ua_vat_mode": "Без ПДВ",
		}
	).insert()


def contract(owner=None, company=None, item=None, qty=12, cadence="Yearly"):
	owner, company, item = owner or issuer(), company or organization(), item or product()
	return frappe.get_doc(
		{
			"doctype": "UA Contract",
			"contract_number": "TEST-" + frappe.generate_hash(length=8),
			"contract_date": "2026-01-01",
			"issuer": owner.name,
			"organization": company.name,
			"bank_account": owner.bank_accounts[0].name,
			"start_date": "2026-01-01",
			"end_date": "2026-12-31",
			"invoice_cadence": cadence,
			"act_cadence": "Monthly",
			"items": [
				{
					"product_code": item.name,
					"product_name": item.product_name,
					"description": "Тестова підтримка",
					"uom": "міс.",
					"qty": qty,
					"net_rate": 1000,
					"vat_mode": "Без ПДВ",
					"vat_rate": "0",
				}
			],
		}
	).insert()


def user(role="UA Billing User", allowed_issuer=None):
	name = "billing-" + frappe.generate_hash(length=8) + "@example.invalid"
	frappe.get_doc(
		{
			"doctype": "User",
			"email": name,
			"first_name": "Billing Test",
			"enabled": 1,
			"user_type": "System User",
			"send_welcome_email": 0,
			"roles": [{"role": "Sales User"}, {"role": role}],
		}
	).insert(ignore_permissions=True)
	if allowed_issuer:
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": name,
				"allow": "UA Issuer",
				"for_value": allowed_issuer,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
	frappe.clear_cache(user=name)
	return name


@contextmanager
def as_user(name):
	previous = frappe.session.user
	frappe.set_user(name)
	try:
		yield
	finally:
		frappe.set_user(previous)
