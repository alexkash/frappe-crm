import importlib.util
import unittest
from pathlib import Path


class TestTestEnvironment(unittest.TestCase):
	def test_runner_does_not_accept_frappe_zero_exit_failure(self):
		spec = importlib.util.spec_from_file_location(
			"billing_test_runner", Path(__file__).resolve().parents[1] / "run_tests.py"
		)
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		self.assertFalse(module.succeeded("Ran 1 test in 0.5s\n\nFAILED (failures=1)\n", 0))
		self.assertFalse(module.succeeded("Ran 0 tests in 0.0s\n\nOK\n", 0))
		self.assertFalse(module.succeeded("Ran 2 tests in 0.5s\n\nOK\n", 1))
		self.assertTrue(module.succeeded("Ran 2 tests in 0.5s\n\nOK\n", 0))

	def test_bootstrap_rejects_production_targets(self):
		root = Path(__file__).resolve().parents[1]
		spec = importlib.util.spec_from_file_location("billing_bootstrap", root / "bootstrap.py")
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		module.validate_target("test_site", "db")
		for site, host in [
			("crm.recuite.com", "db"),
			("test_site", "localhost"),
			("test_site", "production-db"),
		]:
			with self.subTest(site=site, host=host), self.assertRaises(ValueError):
				module.validate_target(site, host)
