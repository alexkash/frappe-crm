from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from recuite_billing import install


class TestInstall(FrappeTestCase):
	def test_rejects_another_apps_file_override_before_changing_schema(self):
		original = frappe.get_hooks

		def hooks(name=None, *args, **kwargs):
			if name == "override_doctype_class":
				return {"File": ["other_app.CustomFile"]}
			return original(name, *args, **kwargs)

		with patch("frappe.get_hooks", side_effect=hooks), self.assertRaises(frappe.ValidationError):
			install.after_migrate()

	def test_custom_fields_are_idempotent_and_catalog_data_survives(self):
		product = frappe.get_doc(
			{
				"doctype": "CRM Product",
				"product_code": "_Test UA Install",
				"product_name": "Послуга",
				"standard_rate": 123.45,
			}
		).insert()
		install.after_migrate()
		install.after_migrate()
		self.assertEqual(
			frappe.db.count("Custom Field", {"dt": "CRM Organization", "fieldname": "ua_legal_name"}), 1
		)
		self.assertEqual(frappe.db.count("Custom Field", {"dt": "CRM Product", "fieldname": "ua_uom"}), 1)
		self.assertEqual(frappe.db.get_value("CRM Product", product.name, "standard_rate"), 123.45)
		self.assertTrue(frappe.db.exists("Role", "UA Billing User"))
		self.assertTrue(frappe.db.exists("Role", "UA Billing Manager"))
		self.assertTrue(frappe.db.exists("Role", "UA Billing Reader"))
