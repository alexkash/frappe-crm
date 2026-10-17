import json

import frappe
from frappe.model.naming import getseries
from frappe.utils import get_datetime, getdate, strip_html, today

from recuite_billing.calculations import allocate_act_items, calculate_items
from recuite_billing.parties import make_party_snapshot
from recuite_billing.periods import is_partial_period
from recuite_billing.permissions import assert_owned_rows

ITEM_FIELDS = (
	"product_code",
	"product_name",
	"description",
	"uom",
	"qty",
	"net_rate",
	"vat_mode",
	"vat_rate",
	"vat_basis",
)


def _locking_reads():
	# MariaDB 11.8's strict snapshots reject Frappe's current locking reads after ordinary reads.
	db = frappe.local.db
	setting = db.sql("SHOW SESSION VARIABLES LIKE 'innodb_snapshot_isolation'")
	if setting and str(setting[0][1]).upper() in {"ON", "1"}:
		db.sql("SET SESSION innodb_snapshot_isolation=OFF")

		def restore():
			db.sql("SET SESSION innodb_snapshot_isolation=ON")

		db.after_commit.add(restore)
		db.after_rollback.add(restore)


def record(doctype, name, *, lock=False):
	if not isinstance(name, str) or not name.strip():
		frappe.throw("Оберіть пов'язаний документ")
	if lock:
		_locking_reads()
	doc = frappe.get_doc(doctype, name, for_update=lock)
	doc.check_permission("read")
	return doc


def dates(first, last):
	if not first or not last:
		frappe.throw("Вкажіть початок і кінець періоду")
	first, last = getdate(first), getdate(last)
	if first > last:
		frappe.throw("Кінець періоду не може передувати його початку")
	return first, last


def lock_existing(doc, expected_status=0):
	if doc.is_new():
		return None
	_locking_reads()
	current = frappe.get_doc(doc.doctype, doc.name, for_update=True)
	if current.docstatus != expected_status:
		frappe.throw("Стан документа змінився. Оновіть сторінку")
	old = doc.get_doc_before_save()
	if old and get_datetime(current.modified) != get_datetime(old.modified):
		frappe.throw("Документ уже змінено. Оновіть сторінку", frappe.TimestampMismatchError)
	return current


def active_periods(doctype, source_field, source_name, first, last, *, exclude=None):
	if doctype not in {"UA Invoice", "UA Act"} or source_field not in {"contract", "invoice"}:
		raise ValueError("Invalid internal period query")
	filters = {
		source_field: source_name,
		"docstatus": ["<", 2],
		"period_from": ["<=", last],
		"period_to": [">=", first],
	}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.db.get_values(
		doctype, filters, ["name", "period_from", "period_to"], as_dict=True, for_update=True
	)


def _matching_parties(doc, source):
	for field in ("issuer", "organization"):
		if doc.get(field) and doc.get(field) != source.get(field):
			frappe.throw("Виконавець і замовник повинні відповідати пов'язаному документу")
		doc.set(field, source.get(field))


def _parties(doc, *, complete=False):
	issuer = record("UA Issuer", doc.issuer, lock=complete)
	if issuer.disabled:
		frappe.throw("Виконавець неактивний")
	customer = record("CRM Organization", doc.organization)
	payer = record("CRM Organization", doc.payer_organization) if doc.get("payer_organization") else None
	try:
		snapshot = make_party_snapshot(
			issuer.as_dict(),
			customer.as_dict(),
			doc.bank_account,
			payer=payer.as_dict() if payer else None,
			require_complete=complete,
		)
	except ValueError as exc:
		frappe.throw(str(exc))
	doc.bank_account = snapshot["bank"]["name"] or None
	return issuer, snapshot


def calculate_document(doc, issuer, current=None):
	assert_owned_rows(doc, "items")
	old_products = {row.name: row.product_code for row in current.items} if current else {}
	for row in doc.items:
		product = record("CRM Product", row.product_code)
		if product.disabled and old_products.get(row.name) != row.product_code:
			frappe.throw("Неактивний продукт не можна додати до нового документа")
		if not row.product_name:
			row.product_name = product.product_name
		if not row.description:
			row.description = strip_html(product.description or "")
		row.uom = row.uom or product.get("ua_uom") or "послуга"
		if row.net_rate is None:
			row.net_rate = product.standard_rate or 0
		row.vat_mode = row.vat_mode or "Без ПДВ"
		row.vat_rate = row.vat_rate or "0"
		row.invoice_item = None
	try:
		result = calculate_items([row.as_dict() for row in doc.items], bool(issuer.vat_registered))
	except ValueError as exc:
		frappe.throw(str(exc))
	for row, values in zip(doc.items, result["items"], strict=True):
		for field in ("qty", "net_rate", "vat_rate", "net_amount", "vat_amount", "gross_amount"):
			row.set(field, str(int(values[field])) if field == "vat_rate" else values[field])
	for field in ("net_total", "vat_total", "grand_total"):
		if doc.meta.has_field(field):
			doc.set(field, result[field])
	return result


def validate_contract(doc):
	current = lock_existing(doc)
	if current and (current.issuer, current.organization) != (doc.issuer, doc.organization):
		if frappe.db.get_values("UA Invoice", {"contract": doc.name}, "name", for_update=True, limit=1):
			frappe.throw("Не можна змінювати сторони договору, для якого вже створено рахунок")
	doc.start_date, doc.end_date = dates(doc.start_date, doc.end_date)
	issuer, _snapshot = _parties(doc)
	calculate_document(doc, issuer, current)


def _set_invoice_snapshot(doc, snapshot, source):
	snapshot["invoice"] = {
		"name": doc.name,
		"number": doc.print_number or "",
		"date": str(doc.posting_date),
		"period_from": str(doc.period_from),
		"period_to": str(doc.period_to),
		"service_anchor": str(source.start_date if source else doc.period_from),
	}
	snapshot["contract"] = (
		{"number": source.contract_number, "date": str(source.contract_date), "name": source.name}
		if source
		else None
	)
	doc.party_snapshot = json.dumps(snapshot, ensure_ascii=False, default=str)


def validate_invoice(doc, *, issue=False):
	source = record("UA Contract", doc.contract, lock=True) if doc.contract else None
	if source:
		if source.disabled:
			frappe.throw("Договір закритий")
		_matching_parties(doc, source)
	current = lock_existing(doc)
	if not doc.organization or not doc.issuer:
		frappe.throw("Оберіть компанію-замовника та нашого виконавця")
	doc.posting_date = getdate(doc.posting_date or today())
	doc.period_from, doc.period_to = dates(doc.period_from, doc.period_to)
	if doc.print_number:
		frappe.throw("Номер рахунку присвоюється лише під час випуску")
	if source:
		try:
			doc.requires_partial_confirmation = int(
				is_partial_period(
					getdate(source.start_date),
					getdate(source.end_date),
					source.invoice_cadence,
					doc.period_from,
					doc.period_to,
				)
			)
		except ValueError as exc:
			frappe.throw(str(exc))
		if active_periods(
			"UA Invoice", "contract", source.name, doc.period_from, doc.period_to, exclude=doc.name
		):
			frappe.throw("Для договору вже існує рахунок із цим або перехресним періодом")
		doc.period_key = f"invoice:{source.name}:{doc.period_from}:{doc.period_to}"
	else:
		doc.period_key = None
		doc.requires_partial_confirmation = 0
	if issue and doc.requires_partial_confirmation and not doc.partial_period_confirmed:
		frappe.throw("Підтвердьте кількість і ціну за неповний період")
	if doc.deal:
		deal = record("CRM Deal", doc.deal)
		if deal.organization != doc.organization:
			frappe.throw("Угода CRM належить іншій компанії")
	if doc.amended_from:
		previous = record("UA Invoice", doc.amended_from)
		if previous.docstatus != 2 or (previous.issuer, previous.organization) != (
			doc.issuer,
			doc.organization,
		):
			frappe.throw("Редакція має посилатися на скасований рахунок тих самих сторін")
	issuer, snapshot = _parties(doc, complete=issue)
	calculate_document(doc, issuer, current)
	doc.pdf_file = doc.pdf_sha256 = doc.print_assets_snapshot = None
	_set_invoice_snapshot(doc, snapshot, source)
	return source


def require_new_draft(doc):
	if doc.docstatus != 0:
		frappe.throw("Спочатку збережіть чернетку, потім випустіть документ")


def issue_invoice(doc):
	source = validate_invoice(doc, issue=True)
	prefix = f"{doc.issuer}-INV-{getdate(doc.posting_date).year}-"
	doc.print_number = prefix + getseries(prefix, 5)
	snapshot = json.loads(doc.party_snapshot)
	_set_invoice_snapshot(doc, snapshot, source)


def cancel_invoice(doc):
	assert_cancel_unchanged(doc, lock_existing(doc, expected_status=1))
	if frappe.db.get_values(
		"UA Act", {"invoice": doc.name, "docstatus": 1}, "name", for_update=True, limit=1
	):
		frappe.throw("Спочатку скасуйте всі випущені акти цього рахунку")
	doc.period_key = None


def validate_act(doc, *, issue=False):
	source = record("UA Invoice", doc.invoice, lock=True)
	if source.docstatus != 1:
		frappe.throw("Акт можна створити лише до випущеного рахунку")
	_matching_parties(doc, source)
	current = lock_existing(doc)
	assert_owned_rows(doc, "items")
	doc.posting_date = getdate(doc.posting_date or today())
	doc.period_from, doc.period_to = dates(doc.period_from, doc.period_to)
	if doc.period_from < getdate(source.period_from) or doc.period_to > getdate(source.period_to):
		frappe.throw("Період акта має бути в межах періоду рахунку")
	if doc.print_number:
		frappe.throw("Номер акта присвоюється лише під час випуску")
	if active_periods("UA Act", "invoice", source.name, doc.period_from, doc.period_to, exclude=doc.name):
		frappe.throw("До рахунку вже існує акт із цим або перехресним періодом")
	doc.contract, doc.deal, doc.bank_account = source.contract, source.deal, source.bank_account
	doc.period_key = f"act:{source.name}:{doc.period_from}:{doc.period_to}"
	parents = frappe.db.get_values(
		"UA Act", {"invoice": source.name, "docstatus": 1}, "name", pluck=True, for_update=True
	)
	used = (
		frappe.db.get_values(
			"UA Billing Item",
			{"parenttype": "UA Act", "parentfield": "items", "parent": ["in", parents]},
			["invoice_item", "qty", "net_amount", "vat_amount"],
			as_dict=True,
			for_update=True,
		)
		if parents
		else []
	)
	try:
		result = allocate_act_items(
			[row.as_dict() for row in source.items],
			used,
			[{"invoice_item": row.invoice_item, "qty": row.qty} for row in doc.items],
		)
	except ValueError as exc:
		frappe.throw(str(exc))
	for row, values in zip(doc.items, result["items"], strict=True):
		for field in (
			*ITEM_FIELDS,
			"invoice_item",
			"net_amount",
			"vat_amount",
			"gross_amount",
			"rounding_adjustment",
		):
			row.set(field, str(int(values[field])) if field == "vat_rate" else values.get(field))
	for field in ("net_total", "vat_total", "grand_total"):
		doc.set(field, result[field])
	doc.party_snapshot = source.party_snapshot
	doc.pdf_file = doc.pdf_sha256 = doc.print_assets_snapshot = None
	if not doc.place_of_issue:
		doc.place_of_issue = record("UA Issuer", source.issuer).place_of_issue
	if issue and not doc.place_of_issue:
		frappe.throw("Вкажіть місце складання акта")
	if doc.amended_from:
		previous = record("UA Act", doc.amended_from)
		if previous.docstatus != 2 or previous.invoice != source.name:
			frappe.throw("Редакція має посилатися на скасований акт цього рахунку")
	return current


def issue_act(doc):
	validate_act(doc, issue=True)
	prefix = f"{doc.issuer}-ACT-{getdate(doc.posting_date).year}-"
	doc.print_number = prefix + getseries(prefix, 5)


def cancel_act(doc):
	record("UA Invoice", doc.invoice, lock=True)
	assert_cancel_unchanged(doc, lock_existing(doc, expected_status=1))
	doc.period_key = None


def assert_cancel_unchanged(doc, current):
	def business_values(value):
		fields = value.get_valid_dict()
		for field in ("modified", "modified_by", "docstatus"):
			fields.pop(field, None)
		for field in value.meta.get_table_fields():
			fields[field.fieldname] = [business_values(row) for row in value.get(field.fieldname) or []]
		return fields

	if frappe.as_json(business_values(doc)) != frappe.as_json(business_values(current)):
		frappe.throw("Під час скасування не можна змінювати реквізити, позиції або архів документа")


def forbid_final_update(doc):
	frappe.throw("Випущений документ незмінний; використайте скасування і нову редакцію")


def protect_final_deletion(doc):
	if doc.docstatus != 0:
		frappe.throw("Історію випущеного або скасованого документа видаляти не можна")
