from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path

import frappe
from PIL import Image, ImageOps

from recuite_billing.permissions import PROTECTED_DOCTYPES, can_read, file_parent

_archive_write = ContextVar("ua_billing_archive_write", default=False)


@contextmanager
def archival_write():
	"""Internal capability for new final PDF/image files; never a request flag."""
	token = _archive_write.set(True)
	try:
		yield
	finally:
		_archive_write.reset(token)


def validate_billing_file(doc, event=None):
	old = (
		frappe.db.get_value(
			"File", doc.name, ["attached_to_doctype", "attached_to_name", "file_url"], as_dict=True
		)
		if doc.name
		else None
	)
	parent = file_parent(doc)
	if (
		old
		and old.attached_to_doctype in PROTECTED_DOCTYPES
		and (old.attached_to_doctype, old.attached_to_name) != parent
	):
		frappe.throw("Не можна змінювати прив'язку захищеного файла")
	if doc.file_url:
		aliases = frappe.get_all(
			"File",
			filters={"file_url": doc.file_url, "attached_to_doctype": ["in", list(PROTECTED_DOCTYPES)]},
			pluck="name",
		)
		if any(name != doc.name for name in aliases):
			frappe.throw("Захищений файл не можна повторно прив'язати за URL; завантажте окрему копію")
	if not parent:
		return
	if not doc.is_private or (doc.file_url and not doc.file_url.startswith("/private/files/")):
		frappe.throw("Договори, підписи, печатки та PDF мають бути приватними")
	if event == "before_insert" and doc.file_url:
		frappe.throw("Завантажте вміст файла, а не URL")
	if not can_read(*parent):
		frappe.throw("Немає доступу до документа", frappe.PermissionError)
	frozen = parent[0] in {"UA Invoice", "UA Act"} and frappe.db.get_value(*parent, "docstatus") in (1, 2)
	if frozen and (old or not _archive_write.get()):
		frappe.throw("Файли випущеного документа незмінні")
	if not _archive_write.get() and not frappe.has_permission(parent[0], "write", doc=parent[1]):
		frappe.throw("Немає права змінювати вкладення", frappe.PermissionError)
	if event == "on_trash":
		if (
			not {"System Manager", "UA Billing Manager"}.intersection(frappe.get_roles())
			and frappe.session.user != "Administrator"
		):
			frappe.throw("Видаляти вкладення може лише менеджер", frappe.PermissionError)
		return
	if old and old.file_url != doc.file_url:
		frappe.throw("Завантажте новий файл замість підміни збереженого URL")
	extension = Path(doc.file_name or doc.file_url or "").suffix.lower()
	allowed = (
		{".png", ".jpg", ".jpeg"} if parent[0] == "UA Print Asset" else {".pdf", ".png", ".jpg", ".jpeg"}
	)
	if extension not in allowed:
		frappe.throw("Дозволені лише PDF, PNG або JPEG; для зображень друку — PNG/JPEG")


def prepare_content(doc, content):
	limit = (5 if doc.attached_to_doctype == "UA Print Asset" else 20) * 1024**2
	if not isinstance(content, bytes) or not content or len(content) > limit:
		frappe.throw("Неприпустимий вміст або розмір файла")
	extension = Path(doc.file_name).suffix.lower()
	try:
		if extension == ".pdf":
			from pypdf import PdfReader

			if not content.startswith(b"%PDF-"):
				raise ValueError("Not a PDF")
			PdfReader(BytesIO(content))
			return content, extension
		with Image.open(BytesIO(content)) as original:
			if original.format not in ({"PNG"} if extension == ".png" else {"JPEG"}):
				raise ValueError("Image type does not match its filename")
			if original.width * original.height > 20_000_000:
				raise ValueError("Image exceeds 20 megapixels")
			original.load()
			if doc.attached_to_doctype != "UA Print Asset":
				return content, extension
			image = ImageOps.exif_transpose(original)
			normalized = image.convert(
				"RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
			)
			image.close()
			normalized.info.clear()
		buffer = BytesIO()
		normalized.save(buffer, format="PNG")
		normalized.close()
		if buffer.tell() > limit:
			raise ValueError("Normalized image exceeds size limit")
		return buffer.getvalue(), ".png"
	except Exception as exc:
		frappe.throw(f"Некоректний PDF або растрове зображення: {type(exc).__name__}")
