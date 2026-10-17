from contextvars import ContextVar

import frappe
from frappe.model.db_query import DatabaseQuery

PROTECTED_DOCTYPES = {"UA Contract", "UA Invoice", "UA Act", "UA Print Asset"}
_checking_saved_scope = ContextVar("ua_billing_saved_scope", default=False)


def can_read(doctype, name, user=None):
	if not name:
		return False
	try:
		return frappe.has_permission(doctype, "read", doc=name, user=user)
	except frappe.DoesNotExistError:
		return False


def has_document_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return None
	# Incoming party fields are caller-controlled; mutations must also authorize the saved record.
	if (
		ptype in {"write", "delete", "submit", "cancel", "amend", "share"}
		and doc.name
		and not doc.is_new()
		and not _checking_saved_scope.get()
	):
		if frappe.db.exists(doc.doctype, doc.name):
			saved = frappe.get_doc(doc.doctype, doc.name)
			token = _checking_saved_scope.set(True)
			try:
				if not frappe.has_permission(doc.doctype, ptype, doc=saved, user=user):
					return False
			finally:
				_checking_saved_scope.reset(token)
	if ptype == "create" and not doc.get("issuer"):
		return None
	if not can_read("UA Issuer", doc.get("issuer"), user):
		return False
	if doc.get("organization") and not can_read("CRM Organization", doc.organization, user):
		return False
	for field, doctype in (("contract", "UA Contract"), ("invoice", "UA Invoice")):
		if doc.get(field) and not can_read(doctype, doc.get(field), user):
			return False
	return None


def _query_conditions(doctype, user):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return ""
	conditions = []
	for field, parent in (("organization", "CRM Organization"), ("issuer", "UA Issuer")):
		if not frappe.has_permission(parent, "read", user=user):
			return "1=0"
		names = DatabaseQuery(parent, user=user).execute(fields=["name"], limit_page_length=0, pluck="name")
		if not names:
			return "1=0"
		values = ",".join(frappe.db.escape(name) for name in names)
		conditions.append(f"`tab{doctype}`.`{field}` IN ({values})")
	return " AND ".join(conditions)


def contract_query_conditions(user=None):
	return _query_conditions("UA Contract", user)


def invoice_query_conditions(user=None):
	return _query_conditions("UA Invoice", user)


def act_query_conditions(user=None):
	return _query_conditions("UA Act", user)


def file_parent(doc):
	if doc.attached_to_doctype in PROTECTED_DOCTYPES and doc.attached_to_name:
		return doc.attached_to_doctype, doc.attached_to_name
	return None


def has_file_permission(doc, ptype=None, user=None):
	parent = file_parent(doc)
	if not parent:
		return None
	if not can_read(*parent, user=user):
		return False
	if (
		ptype in {"write", "delete"}
		and parent[0] in {"UA Invoice", "UA Act"}
		and frappe.db.get_value(*parent, "docstatus")
	):
		return False
	return None


def assert_owned_rows(doc, fieldname):
	child_type = doc.meta.get_field(fieldname).options
	for row in doc.get(fieldname) or []:
		if not row.name:
			continue
		saved = frappe.db.get_value(
			child_type, row.name, ["parent", "parenttype", "parentfield"], as_dict=True
		)
		if saved and (saved.parent, saved.parenttype, saved.parentfield) != (
			doc.name,
			doc.doctype,
			fieldname,
		):
			frappe.throw(
				"Рядок належить іншому документу; додайте новий рядок замість перенесення його ідентифікатора"
			)
