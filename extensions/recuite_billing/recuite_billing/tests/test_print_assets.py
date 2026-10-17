from io import BytesIO
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from PIL import Image

from recuite_billing.tests.helpers import issuer, organization


def png_bytes():
	buffer = BytesIO()
	Image.new("RGBA", (8, 8), (10, 20, 30, 0)).save(buffer, format="PNG")
	return buffer.getvalue()


def asset(owner=None, kind="Signature"):
	owner = owner or issuer()
	return frappe.get_doc(
		{
			"doctype": "UA Print Asset",
			"issuer": owner.name,
			"asset_type": kind,
			"title": "Тестове зображення",
			"signatory": owner.signatory,
			"signatory_position": owner.signatory_position,
			"active": 0,
		}
	).insert()


class TestPrintAssets(FrappeTestCase):
	def test_deleting_an_independent_copy_does_not_leave_a_blob_or_delete_the_original(self):
		first, second = asset(), asset()
		original = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "signature.png",
				"content": png_bytes(),
				"is_private": 1,
				"attached_to_doctype": first.doctype,
				"attached_to_name": first.name,
			}
		).insert()
		copy = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "signature.png",
				"content": png_bytes(),
				"is_private": 1,
				"attached_to_doctype": second.doctype,
				"attached_to_name": second.name,
			}
		).insert()
		path, original_path = Path(copy.get_full_path()), Path(original.get_full_path())
		copy.delete()
		self.assertFalse(path.exists())
		self.assertTrue(original_path.exists())

	def test_private_upload_elsewhere_gets_an_independent_copy(self):
		doc = asset()
		original = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "signature.png",
				"content": png_bytes(),
				"is_private": 1,
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
			}
		).insert()
		company = organization()
		copy = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "copy.png",
				"content": original.get_content(),
				"is_private": 1,
				"attached_to_doctype": company.doctype,
				"attached_to_name": company.name,
			}
		).insert()
		self.assertNotEqual(original.file_url, copy.file_url)
		self.assertEqual(original.get_content(), copy.get_content())

	def test_jpeg_is_stored_as_normalized_png(self):
		doc = asset()
		buffer = BytesIO()
		Image.new("RGB", (8, 8), (10, 20, 30)).save(buffer, format="JPEG")
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "signature.jpg",
				"content": buffer.getvalue(),
				"is_private": 1,
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
			}
		).insert()
		self.assertEqual(Image.open(BytesIO(file.get_content())).format, "PNG")
		self.assertTrue(file.file_url.endswith(".png"))

	def test_active_asset_requires_an_owned_private_image(self):
		doc = asset()
		doc.active = 1
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_normalizes_image_and_preserves_transparency(self):
		doc = asset()
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "signature.png",
				"content": png_bytes(),
				"is_private": 1,
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
			}
		).insert()
		doc.image, doc.active = file.file_url, 1
		doc.save()
		image = Image.open(BytesIO(file.get_content()))
		self.assertEqual(image.format, "PNG")
		self.assertEqual(image.getpixel((0, 0)), (10, 20, 30, 0))

	def test_rejects_alias_to_another_contract_or_asset(self):
		first, second = asset(), asset()
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "signature.png",
				"content": png_bytes(),
				"is_private": 1,
				"attached_to_doctype": first.doctype,
				"attached_to_name": first.name,
			}
		).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": file.file_name,
					"file_url": file.file_url,
					"is_private": 1,
					"attached_to_doctype": second.doctype,
					"attached_to_name": second.name,
				}
			).insert()

	def test_rejects_oversized_or_non_raster_uploads(self):
		doc = asset()
		for name, content in [
			("signature.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
			("signature.png", png_bytes() + b"0" * (5 * 1024**2)),
		]:
			with self.subTest(name=name), self.assertRaises(frappe.ValidationError):
				frappe.get_doc(
					{
						"doctype": "File",
						"file_name": name,
						"content": content,
						"is_private": 1,
						"attached_to_doctype": doc.doctype,
						"attached_to_name": doc.name,
					}
				).insert()
