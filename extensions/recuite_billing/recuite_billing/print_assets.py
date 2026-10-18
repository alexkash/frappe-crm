import base64
import hashlib
import json

import frappe
from frappe import _

from recuite_billing.attachments import archival_write
from recuite_billing.documents import record


def selected_images(doc):
	result = {}
	party = json.loads(doc.party_snapshot)
	for kind in ("logo", "signature", "stamp"):
		if not doc.get(f"print_{kind}"):
			continue
		asset = record("UA Print Asset", doc.get(f"{kind}_asset"), lock=True)
		if asset.issuer != doc.issuer or asset.asset_type != kind.title() or not asset.active:
			frappe.throw(_("Оберіть активне зображення потрібного типу цього виконавця"))
		if kind == "signature" and (asset.signatory, asset.signatory_position or "") != (
			party["issuer"]["signatory"],
			party["issuer"]["signatory_position"] or "",
		):
			frappe.throw(_("Підписант зображення має відповідати підписанту документа"))
		name = frappe.db.get_value(
			"File",
			{
				"file_url": asset.image,
				"is_private": 1,
				"attached_to_doctype": asset.doctype,
				"attached_to_name": asset.name,
			},
			"name",
		)
		if not name:
			frappe.throw(_("Збережене приватне зображення недоступне"))
		file = record("File", name)
		result[kind] = (asset, file.get_content())
	return result


def snapshot_print_assets(doc, created):
	result = {}
	for kind, (asset, content) in selected_images(doc).items():
		with archival_write():
			file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"{kind}.png",
					"content": content,
					"is_private": 1,
					"attached_to_doctype": doc.doctype,
					"attached_to_name": doc.name,
				}
			)
			created.append(file)
			file.insert(ignore_permissions=True)
		result[kind] = {
			"asset": asset.name,
			"file": file.name,
			"sha256": hashlib.sha256(file.get_content()).hexdigest(),
		}
	return result


def get_print_images(doc, *, preview=False):
	if preview:
		contents = {kind: content for kind, (_asset, content) in selected_images(doc).items()}
	else:
		contents = {}
		for kind, image in json.loads(doc.print_assets_snapshot or "{}").items():
			file = record("File", image["file"])
			if (file.attached_to_doctype, file.attached_to_name, file.is_private) != (
				doc.doctype,
				doc.name,
				1,
			):
				frappe.throw(_("Пошкоджена прив'язка архівного зображення"))
			content = file.get_content()
			if hashlib.sha256(content).hexdigest() != image["sha256"]:
				frappe.throw(_("Контрольна сума архівного зображення не збігається"))
			contents[kind] = content
	return {
		kind: "data:image/png;base64," + base64.b64encode(content).decode("ascii")
		for kind, content in contents.items()
	}
