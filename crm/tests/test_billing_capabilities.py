import unittest
from unittest.mock import patch

from crm.api.billing import get_capabilities


class TestBillingCapabilities(unittest.TestCase):
	def test_absent_app_needs_no_extension_import(self):
		with patch("crm.api.billing.frappe.get_installed_apps", return_value=["frappe", "crm"]):
			self.assertEqual(
				get_capabilities(),
				{"enabled": False, "can_read": False, "can_create": False, "can_manage": False},
			)
