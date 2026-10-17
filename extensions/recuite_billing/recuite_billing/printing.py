import hashlib
import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import frappe
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import escape
from pypdf import PdfReader, PdfWriter

from recuite_billing.amount_in_words import amount_in_words_uk
from recuite_billing.attachments import archival_write
from recuite_billing.documents import record
from recuite_billing.formatting import date_uk, money_uk, quantity_uk, rate_uk, rounding_note
from recuite_billing.print_assets import get_print_images, snapshot_print_assets

DOCUMENTS = {"UA Invoice", "UA Act"}


def tax_summary(items):
	labels = []
	for row in items:
		label = f"ПДВ {int(float(row.vat_rate))}%" if row.vat_mode == "ПДВ" else row.vat_mode
		if row.vat_basis:
			label += f" ({row.vat_basis})"
		if label not in labels:
			labels.append(label)
	return "; ".join(labels)


def render_html(doc, *, preview=False):
	if doc.doctype not in DOCUMENTS:
		frappe.throw("Невідомий тип документа")
	env = Environment(
		loader=FileSystemLoader(Path(__file__).parent / "templates"),
		autoescape=True,
		undefined=StrictUndefined,
	)
	return env.get_template("invoice.html" if doc.doctype == "UA Invoice" else "act.html").render(
		doc=doc,
		party=json.loads(doc.party_snapshot),
		items=doc.items,
		images=get_print_images(doc, preview=preview),
		tax_label=tax_summary(doc.items),
		date_uk=date_uk,
		money_uk=money_uk,
		rate_uk=rate_uk,
		quantity_uk=quantity_uk,
		amount_in_words_uk=amount_in_words_uk,
		rounding_note=rounding_note,
	)


def render_pdf_bytes(html):
	from frappe.utils.pdf import get_pdf

	return get_pdf(
		html,
		{
			"page-size": "A4",
			"margin-top": "14mm",
			"margin-bottom": "14mm",
			"margin-left": "14mm",
			"margin-right": "14mm",
			"encoding": "UTF-8",
		},
	)


def archive_document(doc):
	created, savepoint = [], "ua_print_" + uuid4().hex
	frappe.db.savepoint(savepoint)
	try:
		doc.print_assets_snapshot = json.dumps(snapshot_print_assets(doc, created))
		content = render_pdf_bytes(render_html(doc))
		with archival_write():
			file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"{doc.print_number}.pdf",
					"content": content,
					"is_private": 1,
					"attached_to_doctype": doc.doctype,
					"attached_to_name": doc.name,
				}
			)
			created.append(file)
			file.insert(ignore_permissions=True)
		doc.pdf_file, doc.pdf_sha256 = file.name, hashlib.sha256(file.get_content()).hexdigest()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		# Core rollback callbacks run for the whole transaction, not for a savepoint.
		for file in created:
			if file.file_url and (file.file_name or "").startswith("ua-billing-"):
				Path(file.get_full_path()).unlink(missing_ok=True)
		raise


def get_document_pdf(doctype, name):
	if doctype not in DOCUMENTS:
		frappe.throw("Невідомий тип документа")
	doc = record(doctype, name)
	doc.check_permission("print")
	if doc.docstatus not in (1, 2) or not doc.pdf_file:
		frappe.throw("Фінальний PDF доступний після випуску документа")
	file = record("File", doc.pdf_file)
	if (file.attached_to_doctype, file.attached_to_name, file.is_private) != (doctype, name, 1):
		frappe.throw("Пошкоджена прив'язка архівного PDF")
	if hashlib.sha256(file.get_content()).hexdigest() != doc.pdf_sha256:
		frappe.throw("Контрольна сума архівного PDF не збігається")
	return file


@frappe.whitelist(allow_guest=True)
def download_pdf(doctype, name, **kwargs):
	if doctype not in DOCUMENTS:
		from frappe.utils.print_format import download_pdf as native

		return frappe.call(native, doctype=doctype, name=name, **kwargs)
	doc = record(doctype, name)
	doc.check_permission("print")
	content = (
		get_document_pdf(doctype, name).get_content()
		if doc.docstatus
		else render_pdf_bytes(render_html(doc, preview=True))
	)
	frappe.local.response.filename = (doc.print_number or doc.name).replace("/", "-") + ".pdf"
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def download_multi_pdf(doctype, name, **kwargs):
	groups = (
		doctype
		if isinstance(doctype, dict)
		else {doctype: frappe.parse_json(name) if isinstance(name, str) else name}
	)
	if not DOCUMENTS.intersection(groups):
		from frappe.utils.print_format import download_multi_pdf as native

		return native(doctype, name, **kwargs)
	if sum(len(names) for names in groups.values()) > 100:
		frappe.throw("Оберіть не більше 100 документів")
	writer = PdfWriter()
	for kind, names in groups.items():
		for identifier in names:
			if kind in DOCUMENTS:
				doc = record(kind, identifier)
				doc.check_permission("print")
				content = (
					get_document_pdf(kind, identifier).get_content()
					if doc.docstatus
					else render_pdf_bytes(render_html(doc, preview=True))
				)
			else:
				content = frappe.get_print(kind, identifier, as_pdf=True)
			writer.append(PdfReader(BytesIO(content)))
	buffer = BytesIO()
	writer.write(buffer)
	frappe.local.response.filename = "Документи.pdf"
	frappe.local.response.filecontent = buffer.getvalue()
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def download_multi_pdf_async(doctype, name, **kwargs):
	groups = doctype if isinstance(doctype, dict) else {doctype: []}
	if DOCUMENTS.intersection(groups):
		frappe.throw("Для фінансових документів використайте звичайне завантаження PDF (до 100 документів)")
	from frappe.utils.print_format import download_multi_pdf_async as native

	return native(doctype, name, **kwargs)


def pdf_body_html(jenv, template, print_format, args):
	doc = args["doc"]
	if doc.doctype in DOCUMENTS:
		# Always reload: printview can otherwise receive an arbitrary client-supplied document.
		doc = record(doc.doctype, doc.name)
		doc.check_permission("print")
		if doc.docstatus:
			file = get_document_pdf(doc.doctype, doc.name)
			return f'<p>Архівний PDF · {"Скасовано" if doc.docstatus == 2 else "Випущено"}</p><iframe title="Архівний PDF" src="{escape(file.file_url)}" style="width:100%;height:90vh;border:0"></iframe>'
		return render_html(doc, preview=True)
	from frappe.utils.pdf import pdf_body_html as native

	return native(jenv=jenv, template=template, print_format=print_format, args=args)


def prevent_archive_rerender(doctype, name, **kwargs):
	if doctype in DOCUMENTS and frappe.db.get_value(doctype, name, "docstatus"):
		frappe.throw("Використайте збережений архівний PDF документа")
