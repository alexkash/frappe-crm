"""Optional billing app entry point; CRM remains usable without the extension."""

import frappe


@frappe.whitelist()
def get_capabilities() -> dict:
	if "recuite_billing" not in frappe.get_installed_apps():
		return {"enabled": False, "can_read": False, "can_create": False, "can_manage": False}
	from recuite_billing.api import get_capabilities as installed_capabilities

	return installed_capabilities()
