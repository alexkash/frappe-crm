import hashlib
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from recuite_billing.tests.helpers import contract, pdf_bytes
from recuite_billing.tests.test_print_assets import asset, png_bytes


class TestPrinting(FrappeTestCase):
	def test_invoice_pdf_keeps_the_service_unit_together(self):
		from recuite_billing.printing import get_document_pdf

		invoice = self.draft()
		invoice.items[0].uom = "послуга"
		invoice.save().submit()
		content = get_document_pdf(invoice.doctype, invoice.name).get_content()
		text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)
		self.assertIn("послуга", text)

	def test_json_grouped_pdf_uses_archives_and_cannot_start_async_rerender(self):
		from recuite_billing.printing import download_multi_pdf, download_multi_pdf_async

		invoice = self.draft()
		with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
			invoice.submit()
		groups = json.dumps({"UA Invoice": [invoice.name]})
		with patch("recuite_billing.printing.render_html", side_effect=AssertionError("Must use archive")):
			download_multi_pdf(groups, None)
			self.assertEqual(len(PdfReader(BytesIO(frappe.local.response.filecontent)).pages), 1)
		with self.assertRaises(frappe.ValidationError):
			download_multi_pdf_async(groups, None)

	def draft(self):
		from recuite_billing.api import create_invoice

		source = contract()
		return frappe.get_doc("UA Invoice", create_invoice(source.name, "2026-01-01", "2026-12-31")["name"])

	def signature(self, invoice):
		image = asset(frappe.get_doc("UA Issuer", invoice.issuer))
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "test.png",
				"content": png_bytes(),
				"is_private": 1,
				"attached_to_doctype": image.doctype,
				"attached_to_name": image.name,
			}
		).insert()
		image.image, image.active = file.file_url, 1
		image.save()
		invoice.print_signature, invoice.signature_asset = 1, image.name
		return image, file

	def test_archive_is_private_and_stable_after_sources_and_template_change(self):
		from recuite_billing.printing import get_document_pdf

		invoice = self.draft()
		image, original = self.signature(invoice)
		invoice.submit()
		file = get_document_pdf(invoice.doctype, invoice.name)
		content = file.get_content()
		self.assertEqual(hashlib.sha256(content).hexdigest(), invoice.pdf_sha256)
		self.assertEqual(file.is_private, 1)
		self.assertTrue(content.startswith(b"%PDF-"))
		text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)
		for block in (
			"Рахунок-фактура",
			"Постачальник",
			"Одержувач",
			"Замовлення",
			"Виписав",
			"Дванадцять тисяч",
			"Без ПДВ",
		):
			self.assertIn(block, text)
		snapshot = json.loads(invoice.print_assets_snapshot)["signature"]
		copy = frappe.get_doc("File", snapshot["file"])
		self.assertNotEqual(copy.file_url, original.file_url)
		image.active = 0
		image.save()
		frappe.db.set_value("UA Issuer", invoice.issuer, "legal_name", "Змінені реквізити")
		with patch(
			"recuite_billing.printing.render_html", side_effect=AssertionError("Must not render archive")
		):
			self.assertEqual(get_document_pdf(invoice.doctype, invoice.name).get_content(), content)
			from recuite_billing.printing import download_pdf

			download_pdf(invoice.doctype, invoice.name, format="Standard")
			self.assertEqual(frappe.local.response.filecontent, content)

	def test_act_pdf_has_both_parties_invoice_and_service_period(self):
		from recuite_billing.api import create_act
		from recuite_billing.printing import get_document_pdf

		invoice = self.draft()
		owner = frappe.get_doc("UA Issuer", invoice.issuer)
		owner.income_tax_note = "Платник єдиного податку, третя група, без ПДВ"
		owner.save()
		invoice.items[
			0
		].description = "Технічна підтримка інформаційної системи. Супровід, консультації та усунення технічних несправностей."
		with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
			invoice.submit()
		act = frappe.get_doc(
			"UA Act",
			create_act(
				invoice.name, "2026-01-01", "2026-01-31", [{"invoice_item": invoice.items[0].name, "qty": 1}]
			)["name"],
		)
		from PIL import Image

		for kind in ("Logo", "Signature", "Stamp"):
			image = asset(owner, kind)
			buffer = BytesIO()
			Image.new("RGBA", (500, 500) if kind == "Stamp" else (700, 180), (10, 30, 100, 100)).save(
				buffer, format="PNG"
			)
			file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "layout.png",
					"content": buffer.getvalue(),
					"is_private": 1,
					"attached_to_doctype": image.doctype,
					"attached_to_name": image.name,
				}
			).insert()
			image.image, image.active = file.file_url, 1
			image.save()
			act.set(f"print_{kind.lower()}", 1)
			act.set(f"{kind.lower()}_asset", image.name)
		act.submit()
		content = get_document_pdf(act.doctype, act.name).get_content()
		reader = PdfReader(BytesIO(content))
		self.assertEqual(len(reader.pages), 1)
		text = "\n".join(page.extract_text() for page in reader.pages)
		for block in (
			"ЗАТВЕРДЖУЮ",
			"АКТ №",
			"Від Виконавця",
			"Від Замовника",
			"Сторони претензій",
			"Місце складання",
			invoice.print_number,
			"Період надання послуг",
		):
			self.assertIn(block, text)

	def test_renderer_failure_keeps_draft_and_removes_only_new_blobs(self):
		invoice = self.draft()
		_image, original = self.signature(invoice)
		before = set(Path(frappe.get_site_path("private", "files")).glob("ua-billing-*"))
		with patch(
			"recuite_billing.printing.render_pdf_bytes", side_effect=RuntimeError("renderer unavailable")
		):
			with self.assertRaises(RuntimeError):
				invoice.submit()
		self.assertEqual(frappe.db.get_value("UA Invoice", invoice.name, "docstatus"), 0)
		self.assertEqual(set(Path(frappe.get_site_path("private", "files")).glob("ua-billing-*")), before)
		self.assertTrue(Path(original.get_full_path()).exists())
		self.assertFalse(
			frappe.db.exists("File", {"attached_to_doctype": "UA Invoice", "attached_to_name": invoice.name})
		)

	def test_signature_selection_is_scoped_and_must_match_signer(self):
		invoice = self.draft()
		image, _file = self.signature(invoice)
		image.signatory = "Інша особа"
		image.save()
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()

	def test_all_image_combinations_and_independent_repeated_snapshots(self):
		from recuite_billing.printing import render_html

		for signature, stamp in ((0, 0), (1, 0), (0, 1), (1, 1)):
			with self.subTest(signature=signature, stamp=stamp):
				invoice = self.draft()
				image, _file = self.signature(invoice)
				seal = asset(frappe.get_doc("UA Issuer", invoice.issuer), kind="Stamp")
				file = frappe.get_doc(
					{
						"doctype": "File",
						"file_name": "seal.png",
						"content": png_bytes(),
						"is_private": 1,
						"attached_to_doctype": seal.doctype,
						"attached_to_name": seal.name,
					}
				).insert()
				seal.image, seal.active = file.file_url, 1
				seal.save()
				invoice.print_signature, invoice.print_stamp, invoice.stamp_asset = (
					signature,
					stamp,
					seal.name,
				)
				with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
					invoice.submit()
				html = render_html(invoice)
				self.assertEqual('alt="Зображення підпису"' in html, bool(signature))
				self.assertEqual('alt="Зображення печатки"' in html, bool(stamp))
				self.assertEqual(
					set(json.loads(invoice.print_assets_snapshot)),
					({"signature"} if signature else set()) | ({"stamp"} if stamp else set()),
				)
				if signature:
					from recuite_billing.api import create_act

					acts = []
					for first, last in (("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28")):
						act = frappe.get_doc(
							"UA Act",
							create_act(
								invoice.name, first, last, [{"invoice_item": invoice.items[0].name, "qty": 1}]
							)["name"],
						)
						act.print_signature, act.signature_asset = 1, image.name
						with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
							act.submit()
						acts.append(act)
					files = [
						frappe.get_doc("File", json.loads(doc.print_assets_snapshot)["signature"]["file"])
						for doc in [invoice, *acts]
					]
					self.assertEqual(len({file.file_url for file in files}), 3)
					self.assertEqual(len({file.get_content() for file in files}), 1)

	def test_multipage_pdf_retains_last_item_and_escapes_catalog_html(self):
		from recuite_billing.printing import get_document_pdf, render_html

		invoice = self.draft()
		values = {
			key: invoice.items[0].get(key)
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
		for index in range(25):
			invoice.append(
				"items",
				{
					**values,
					"product_name": f"Послуга {index + 1}",
					"description": "Довгий опис технічної підтримки. " * 8,
				},
			)
		invoice.items[-1].product_name = "Остання послуга <script>alert(1)</script>"
		invoice.save()
		self.assertNotIn("<script>", render_html(invoice, preview=True))
		invoice.submit()
		reader = PdfReader(BytesIO(get_document_pdf(invoice.doctype, invoice.name).get_content()))
		self.assertGreater(len(reader.pages), 1)
		self.assertIn("Остання послуга", "\n".join(page.extract_text() for page in reader.pages))

	def test_storage_failure_after_writing_a_blob_cleans_the_failed_file(self):
		from recuite_billing.overrides.file import BillingFile

		invoice = self.draft()
		self.signature(invoice)
		before = set(Path(frappe.get_site_path("private", "files")).glob("ua-billing-*"))
		native = BillingFile.after_insert

		def fail_after_insert(file):
			native(file)
			if file.attached_to_doctype == "UA Invoice":
				raise RuntimeError("storage failure after write")

		with patch.object(BillingFile, "after_insert", fail_after_insert):
			with self.assertRaises(RuntimeError):
				invoice.submit()
		self.assertEqual(set(Path(frappe.get_site_path("private", "files")).glob("ua-billing-*")), before)

	def test_amendment_gets_new_archive_without_copying_cancelled_files(self):
		invoice = self.draft()
		with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
			invoice.submit()
		invoice.cancel()
		amended = frappe.copy_doc(invoice, ignore_no_copy=False)
		amended.docstatus = 0
		amended.amended_from = invoice.name
		amended.insert()
		self.assertFalse(
			frappe.db.exists(
				"File", {"attached_to_doctype": amended.doctype, "attached_to_name": amended.name}
			)
		)
		with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
			amended.submit()
		self.assertNotEqual(invoice.pdf_file, amended.pdf_file)
		self.assertNotEqual(invoice.print_number, amended.print_number)

	def test_cancel_rejects_mutating_financial_history(self):
		from recuite_billing.api import create_act

		invoice = self.draft()
		with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
			invoice.submit()
		act = frappe.get_doc(
			"UA Act",
			create_act(
				invoice.name, "2026-01-01", "2026-01-31", [{"invoice_item": invoice.items[0].name, "qty": 1}]
			)["name"],
		)
		with patch("recuite_billing.printing.render_pdf_bytes", return_value=pdf_bytes()):
			act.submit()
		from frappe.client import save

		payload = act.as_dict()
		payload["docstatus"] = 2
		payload["items"][0]["qty"] = 0.5
		with self.assertRaises(frappe.ValidationError):
			save(payload)
		act.reload().cancel()
		payload = invoice.as_dict()
		payload["docstatus"], payload["party_snapshot"] = 2, "{}"
		with self.assertRaises(frappe.ValidationError):
			save(payload)

	def test_non_billing_pdf_retains_native_guest_route_metadata(self):
		from recuite_billing.printing import download_pdf

		self.assertIn(download_pdf, frappe.guest_methods)
