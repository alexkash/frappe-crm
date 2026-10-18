import json

import frappe
from frappe import _

from recuite_billing.documents import ITEM_FIELDS, active_periods, dates, record


@frappe.whitelist(methods=["POST"])
def create_invoice(contract: str, period_from: str, period_to: str) -> dict:
	if not frappe.has_permission("UA Invoice", "create"):
		frappe.throw(_("Немає права створювати рахунки"), frappe.PermissionError)
	source = record("UA Contract", contract, lock=True)
	if source.disabled:
		frappe.throw(_("Договір закритий"))
	first, last = dates(period_from, period_to)
	rows = active_periods("UA Invoice", "contract", source.name, first, last)
	if rows:
		if len(rows) == 1 and rows[0].period_from == first and rows[0].period_to == last:
			doc = record("UA Invoice", rows[0].name, lock=True)
			return {"name": doc.name, "existing": True}
		frappe.throw(_("За цим договором уже існує рахунок із перехресним періодом"))
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


@frappe.whitelist(methods=["POST"])
def create_act(invoice: str, period_from: str, period_to: str, items: list[dict] | str) -> dict:
	if not frappe.has_permission("UA Act", "create"):
		frappe.throw(_("Немає права створювати акти"), frappe.PermissionError)
	if isinstance(items, str):
		items = frappe.parse_json(items)
	if not isinstance(items, list) or not items or any(not isinstance(row, dict) for row in items):
		frappe.throw(_("Оберіть позиції рахунку та кількість"))
	source = record("UA Invoice", invoice, lock=True)
	if source.docstatus != 1:
		frappe.throw(_("Акт можна створити лише до випущеного рахунку"))
	first, last = dates(period_from, period_to)
	rows = active_periods("UA Act", "invoice", source.name, first, last)
	if rows:
		if len(rows) == 1 and rows[0].period_from == first and rows[0].period_to == last:
			doc = record("UA Act", rows[0].name, lock=True)
			return {"name": doc.name, "existing": True}
		frappe.throw(_("До рахунку вже існує акт із перехресним періодом"))
	doc = frappe.get_doc(
		{
			"doctype": "UA Act",
			"invoice": source.name,
			"period_from": first,
			"period_to": last,
			"items": [{"invoice_item": row.get("invoice_item"), "qty": row.get("qty")} for row in items],
		}
	).insert()
	return {"name": doc.name, "existing": False}


@frappe.whitelist()
def get_capabilities() -> dict:
	return {
		"enabled": True,
		"create": {
			kind: bool(frappe.has_permission(kind, "create"))
			for kind in ("UA Contract", "UA Invoice", "UA Act")
		},
		"can_read": any(
			frappe.has_permission(kind, "read") for kind in ("UA Contract", "UA Invoice", "UA Act")
		),
		"can_create": bool(frappe.has_permission("UA Invoice", "create")),
		"can_manage": bool(frappe.has_permission("UA Issuer", "write")),
	}


@frappe.whitelist()
def get_organization_documents(organization: str, kind: str, start: int = 0, page_length: int = 20) -> dict:
	kinds = {"contracts": "UA Contract", "invoices": "UA Invoice", "acts": "UA Act"}
	if kind not in kinds:
		frappe.throw(_("Невідомий тип документів"))
	try:
		start, page_length = int(start), int(page_length)
		if start < 0 or not 1 <= page_length <= 100:
			raise ValueError
	except (ValueError, TypeError):
		frappe.throw(_("Неприпустимі параметри сторінки"))
	record("CRM Organization", organization)
	fields = ["name", "issuer", "docstatus", "modified"] + (
		["contract_number", "contract_date", "disabled"]
		if kind == "contracts"
		else ["print_number", "posting_date", "period_from", "period_to", "grand_total", "pdf_file"]
	)
	rows = frappe.get_list(
		kinds[kind],
		filters={"organization": organization},
		fields=fields,
		order_by="modified desc",
		start=start,
		page_length=page_length + 1,
	)
	return {"rows": rows[:page_length], "has_more": len(rows) > page_length}


@frappe.whitelist()
def get_period_suggestion(doctype: str, name: str) -> dict:
	from frappe.utils import getdate

	from recuite_billing.periods import periods_in_range

	if doctype not in {"UA Contract", "UA Invoice"}:
		frappe.throw(_("Невідоме джерело періодів"))
	source = record(doctype, name)
	if doctype == "UA Contract":
		first, last, cadence, target, field = (
			source.start_date,
			source.end_date,
			source.invoice_cadence,
			"UA Invoice",
			"contract",
		)
	else:
		first, last, cadence, target, field = (
			source.period_from,
			source.period_to,
			source.act_cadence,
			"UA Act",
			"invoice",
		)
	periods = frappe.get_list(
		target,
		filters={field: name, "docstatus": ["<", 2]},
		fields=["period_from", "period_to"],
		page_length=0,
	)
	anchor = getdate(first) if doctype == "UA Contract" else _service_anchor(source)
	try:
		schedule = periods_in_range(anchor, getdate(first), getdate(last), cadence)
	except ValueError as exc:
		frappe.throw(str(exc))
	for period in schedule:
		if not any(
			getdate(row.period_from) <= period[1] and getdate(row.period_to) >= period[0] for row in periods
		):
			return {"period_from": period[0].isoformat(), "period_to": period[1].isoformat()}
	return {}


@frappe.whitelist()
def get_act_items(invoice: str) -> list:
	from decimal import ROUND_DOWN, Decimal

	from frappe.utils import getdate

	from recuite_billing.periods import periods_in_range

	source = record("UA Invoice", invoice, lock=True)
	if source.docstatus != 1:
		frappe.throw(_("Спочатку випустіть рахунок"))
	acts = frappe.db.get_values(
		"UA Act",
		{"invoice": invoice, "docstatus": 1},
		["name", "period_from", "period_to"],
		as_dict=True,
		for_update=True,
	)
	used = (
		frappe.db.get_values(
			"UA Billing Item",
			{"parenttype": "UA Act", "parent": ["in", [act.name for act in acts]]},
			["invoice_item", "qty"],
			as_dict=True,
			for_update=True,
		)
		if acts
		else []
	)
	try:
		schedule = periods_in_range(
			_service_anchor(source),
			getdate(source.period_from),
			getdate(source.period_to),
			source.act_cadence,
		)
	except ValueError as exc:
		frappe.throw(str(exc))
	open_periods = sum(
		not any(getdate(act.period_from) <= last and getdate(act.period_to) >= first for act in acts)
		for first, last in schedule
	)
	result = []
	for row in source.items:
		remaining = Decimal(str(row.qty)) - sum(
			(Decimal(str(item.qty)) for item in used if item.invoice_item == row.name), Decimal(0)
		)
		if remaining > 0:
			qty = (
				remaining
				if open_periods <= 1
				else min(
					remaining,
					(Decimal(str(row.qty)) / max(1, len(schedule))).quantize(
						Decimal("0.000001"), rounding=ROUND_DOWN
					),
				)
			)
			result.append(
				{
					**{field: row.get(field) for field in ITEM_FIELDS},
					"invoice_item": row.name,
					"product_name": row.product_name,
					"uom": row.uom,
					"remaining": str(remaining),
					"qty": str(qty or remaining),
				}
			)
	return result


def _service_anchor(invoice):
	from frappe.utils import getdate

	return getdate(
		json.loads(invoice.party_snapshot or "{}").get("invoice", {}).get("service_anchor")
		or invoice.period_from
	)


@frappe.whitelist()
def get_document_context(doctype: str, name: str) -> dict:
	if doctype not in {"UA Contract", "UA Invoice", "UA Act"}:
		frappe.throw(_("Невідомий тип документа"))
	source = record(doctype, name)
	related = []
	for field, parent_type in (("contract", "UA Contract"), ("invoice", "UA Invoice")):
		parent_name = source.get(field)
		if parent_name and frappe.has_permission(parent_type, "read", doc=parent_name):
			parent = record(parent_type, parent_name)
			related.append(
				{
					"doctype": parent_type,
					"name": parent.name,
					"contract_number": parent.get("contract_number"),
					"print_number": parent.get("print_number"),
					"docstatus": parent.docstatus,
				}
			)
	children = {
		"UA Contract": [("UA Invoice", "contract"), ("UA Act", "contract")],
		"UA Invoice": [("UA Act", "invoice")],
		"UA Act": [],
	}
	more = []
	for child_type, field in children[doctype]:
		if not frappe.has_permission(child_type, "read"):
			continue
		rows = frappe.get_list(
			child_type,
			filters={field: source.name},
			fields=["name", "print_number", "docstatus", "period_from", "period_to", "grand_total"],
			order_by="period_from desc, creation desc",
			page_length=21,
		)
		related.extend({"doctype": child_type, **row} for row in rows[:20])
		if len(rows) > 20:
			more.append({"doctype": child_type, "field": field, "value": source.name})
	return {"related": related, "more": more}
