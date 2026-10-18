"""Synthetic fixtures and PDF exports, confined to the isolated billing test site."""

import hashlib
import json
import os
from io import BytesIO
from pathlib import Path

import frappe
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader


def main():
	os.chdir("/home/frappe/frappe-bench/sites")
	frappe.init(site="test_site")
	frappe.connect()
	assert frappe.local.site == "test_site" and frappe.conf.db_name == "billing_test"
	# Isolated synthetic-site actor; this is not a request handler.
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	frappe.set_user("Administrator")

	from recuite_billing.api import create_act, create_invoice
	from recuite_billing.printing import get_document_pdf
	from recuite_billing.tests.helpers import contract, issuer, pdf_bytes
	from recuite_billing.tests.test_print_assets import asset

	out = Path(frappe.get_site_path("private", "billing-qa"))
	out.mkdir(exist_ok=True)
	manifest = {"documents": [], "organization": None}

	def export(doc, label):
		file = get_document_pdf(doc.doctype, doc.name)
		content = file.get_content()
		(out / f"{label}.pdf").write_bytes(content)
		manifest["documents"].append(
			{
				"doctype": doc.doctype,
				"name": doc.name,
				"label": label,
				"sha256": hashlib.sha256(content).hexdigest(),
				"pdf_file": file.name,
			}
		)

	try:
		owner = issuer()
		owner.legal_name = "ФОП Тестовий Виконавець"
		owner.income_tax_note = "Платник єдиного податку, третя група, без ПДВ"
		owner.save()
		images = {}
		for kind in ("Logo", "Signature", "Stamp"):
			image = Image.new("RGBA", (500, 500) if kind == "Stamp" else (700, 180), (255, 255, 255, 0))
			draw = ImageDraw.Draw(image)
			font = ImageFont.truetype(
				"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 70 if kind == "Logo" else 40
			)
			if kind == "Stamp":
				draw.ellipse((15, 15, 485, 485), outline="#244a9b", width=12)
				draw.ellipse((55, 55, 445, 445), outline="#244a9b", width=4)
				draw.text((135, 225), "TEST ONLY", fill="#244a9b", font=font)
			elif kind == "Signature":
				draw.line(
					[
						(20, 140),
						(70, 25),
						(100, 140),
						(155, 50),
						(130, 120),
						(230, 75),
						(300, 120),
						(420, 65),
						(480, 110),
						(660, 80),
					],
					fill="#244a9b",
					width=8,
				)
			else:
				draw.rounded_rectangle((0, 0, 690, 170), radius=25, fill="#163b56")
				draw.text((245, 45), "TEST", fill="white", font=font)
			buffer = BytesIO()
			image.save(buffer, format="PNG")
			card = asset(owner, kind)
			file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"{kind}.png",
					"content": buffer.getvalue(),
					"is_private": 1,
					"attached_to_doctype": card.doctype,
					"attached_to_name": card.name,
				}
			).insert()
			card.image, card.active = file.file_url, 1
			card.save()
			images[kind.lower()] = card.name
		source = contract(owner=owner)
		source.items[
			0
		].description = "Технічна підтримка інформаційної системи. Супровід, консультації та усунення технічних несправностей."
		source.save()
		manifest["organization"] = source.organization
		invoice = frappe.get_doc(
			"UA Invoice", create_invoice(source.name, "2026-01-01", "2026-12-31")["name"]
		)
		for kind, name in images.items():
			invoice.set(f"print_{kind}", 1)
			invoice.set(f"{kind}_asset", name)
		invoice.submit()
		export(invoice, "invoice-with-scans")
		act = frappe.get_doc(
			"UA Act",
			create_act(
				invoice.name, "2026-01-01", "2026-01-31", [{"invoice_item": invoice.items[0].name, "qty": 1}]
			)["name"],
		)
		for kind, name in images.items():
			act.set(f"print_{kind}", 1)
			act.set(f"{kind}_asset", name)
		act.submit()
		export(act, "act-with-scans")
		second = frappe.get_doc(
			"UA Act",
			create_act(
				invoice.name, "2026-02-01", "2026-02-28", [{"invoice_item": invoice.items[0].name, "qty": 1}]
			)["name"],
		).submit()
		export(second, "act-no-scans")
		for vat, label in ((False, "invoice-tov-no-vat"), (True, "invoice-tov-vat")):
			other = issuer(vat=vat)
			other.issuer_type, other.registration_code = "ТОВ", "00000002"
			other.save()
			agreement = contract(owner=other)
			if vat:
				agreement.items[0].vat_mode, agreement.items[0].vat_rate = "ПДВ", "20"
			agreement.save()
			bill = frappe.get_doc(
				"UA Invoice", create_invoice(agreement.name, "2026-01-01", "2026-12-31")["name"]
			).submit()
			export(bill, label)
			if vat:
				text = "\n".join(
					page.extract_text()
					for page in PdfReader(
						BytesIO(get_document_pdf(bill.doctype, bill.name).get_content())
					).pages
				)
				assert "ІПН платника ПДВ: 000000000000" in text
		long_source = contract()
		row = {
			key: long_source.items[0].get(key)
			for key in (
				"product_code",
				"product_name",
				"description",
				"uom",
				"qty",
				"net_rate",
				"vat_mode",
				"vat_rate",
			)
		}
		for index in range(18):
			long_source.append(
				"items",
				{
					**row,
					"product_name": f"Послуга {index+1}",
					"description": "Довгий опис технічної підтримки та консультацій. " * 7,
				},
			)
		long_source.save()
		long = frappe.get_doc(
			"UA Invoice", create_invoice(long_source.name, "2026-01-01", "2026-12-31")["name"]
		).submit()
		export(long, "invoice-multipage")
		attachment = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "synthetic-contract.pdf",
				"content": pdf_bytes(),
				"is_private": 1,
				"attached_to_doctype": source.doctype,
				"attached_to_name": source.name,
			}
		).insert()
		manifest["contract"] = source.name
		manifest["contract_file"] = attachment.name
		# Separate HTTP/restore processes must see the synthetic fixtures.
		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		(out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
		print(
			json.dumps(
				{"result": "PASS", "pdfs": len(manifest["documents"]), "organization": source.organization}
			)
		)
	except Exception:
		frappe.db.rollback()
		raise
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
