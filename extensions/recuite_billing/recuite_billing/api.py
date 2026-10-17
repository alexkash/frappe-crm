import frappe

from recuite_billing.documents import ITEM_FIELDS, active_periods, dates, record


@frappe.whitelist(methods=["POST"])
def create_invoice(contract: str, period_from: str, period_to: str) -> dict:
	if not frappe.has_permission("UA Invoice", "create"):
		frappe.throw("Немає права створювати рахунки", frappe.PermissionError)
	source = record("UA Contract", contract, lock=True)
	if source.disabled:
		frappe.throw("Договір закритий")
	first, last = dates(period_from, period_to)
	rows = active_periods("UA Invoice", "contract", source.name, first, last)
	if rows:
		if len(rows) == 1 and rows[0].period_from == first and rows[0].period_to == last:
			doc = record("UA Invoice", rows[0].name, lock=True)
			return {"name": doc.name, "existing": True}
		frappe.throw("За цим договором уже існує рахунок із перехресним періодом")
	doc = frappe.get_doc(
		{
			"doctype": "UA Invoice",
			"contract": source.name,
			"issuer": source.issuer,
			"organization": source.organization,
			"bank_account": source.bank_account,
			"period_from": first,
			"period_to": last,
			"act_cadence": source.act_cadence,
			"items": [{field: row.get(field) for field in ITEM_FIELDS} for row in source.items],
		}
	).insert()
	return {"name": doc.name, "existing": False}
