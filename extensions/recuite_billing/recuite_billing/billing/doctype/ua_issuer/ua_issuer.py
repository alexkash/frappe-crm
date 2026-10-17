import re

import frappe
from frappe.model.document import Document

from recuite_billing.permissions import assert_owned_rows
from recuite_billing.validations import validate_iban, validate_registration_code


class UAIssuer(Document):
	def validate(self):
		assert_owned_rows(self, "bank_accounts")
		if not re.fullmatch(r"[\w-]{1,20}", str(self.issuer_code or ""), re.UNICODE):
			frappe.throw("Код виконавця: до 20 літер/цифр, дефіс або підкреслення")
		old = self.get_doc_before_save()
		if old and old.issuer_code != self.issuer_code:
			frappe.throw("Код виконавця незмінний")
		try:
			if self.registration_code:
				self.registration_code = validate_registration_code(self.registration_code, self.issuer_type)
			for row in self.bank_accounts:
				row.iban = validate_iban(row.iban)
		except ValueError as exc:
			frappe.throw(str(exc))
		if len({row.iban for row in self.bank_accounts}) != len(self.bank_accounts):
			frappe.throw("Банківські рахунки не повинні повторюватися")
		if sum(bool(row.is_default) for row in self.bank_accounts) > 1:
			frappe.throw("Оберіть один рахунок за замовчуванням")
