from pathlib import Path
from uuid import uuid4

import frappe
from frappe import _
from frappe.core.doctype.file.file import File, get_content_hash

from recuite_billing.attachments import prepare_content, validate_billing_file
from recuite_billing.permissions import PROTECTED_DOCTYPES, can_read, file_parent


class BillingFile(File):
	def before_insert(self):
		validate_billing_file(self, "before_insert")
		return super().before_insert()

	def validate(self):
		validate_billing_file(self, "validate")
		return super().validate()

	def on_trash(self):
		validate_billing_file(self, "on_trash")
		return super().on_trash()

	def is_downloadable(self):
		parent = file_parent(self)
		if parent and not can_read(*parent):
			return False
		return super().is_downloadable()

	def _delete_file_on_disk(self):
		if not self.is_folder and (file_parent(self) or (self.file_name or "").startswith("ua-billing-")):
			# Isolated blobs can share a hash, but only a shared URL owns the same physical file.
			shared = frappe.db.exists("File", {"file_url": self.file_url, "name": ["!=", self.name]})
			return self.delete_file_data_content(only_thumbnail=bool(shared))
		return super()._delete_file_on_disk()

	def save_file(self, content=None, decode=False, ignore_existing_file_check=False, overwrite=False):
		independent_copy = bool(file_parent(self))
		if independent_copy:
			validate_billing_file(self, "save_file")
			if self.name and frappe.db.exists("File", self.name):
				frappe.throw(_("Завантажте новий файл замість зміни збереженого вмісту"))
			content, extension = prepare_content(self, content if content is not None else self.get_content())
			self.file_type = extension.lstrip(".").upper()
		elif content is not None and self.is_private:
			# Core deduplication must not turn an ordinary upload into a protected URL alias.
			independent_copy = bool(
				frappe.db.exists(
					"File",
					{
						"content_hash": get_content_hash(content),
						"is_private": 1,
						"attached_to_doctype": ["in", list(PROTECTED_DOCTYPES)],
					},
				)
			)
			extension = Path(self.file_name).suffix
		if independent_copy:
			self.file_name = f"ua-billing-{Path(self.file_name).stem[:48]}-{uuid4().hex}{extension}"
			self.flags.ignore_duplicate_entry_error = True
			ignore_existing_file_check, overwrite = True, False
		return super().save_file(
			content=content,
			decode=decode,
			ignore_existing_file_check=ignore_existing_file_check,
			overwrite=overwrite,
		)
