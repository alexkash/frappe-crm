"""Create only the isolated Compose test site; never adopt or reinstall a site."""

import contextlib
import io
import json
import os
from pathlib import Path

SITE = "test_site"
SITES = Path("/home/frappe/frappe-bench/sites")


def validate_target(site, database_host):
	if site != SITE or database_host != "db":
		raise ValueError("Billing bootstrap only supports test_site on its private db service")


def bootstrap():
	validate_target(os.environ.get("BILLING_TEST_SITE", SITE), "db")
	if Path.cwd() != SITES or (SITES / SITE).exists():
		raise ValueError("Test site must be new; existing state is never reinstalled")
	if any(p.is_dir() and (p / "site_config.json").exists() for p in SITES.iterdir()):
		raise ValueError("Unexpected existing site in the test volume")
	common = dict(
		db_host="db",
		db_port=3306,
		redis_cache="redis://redis-cache:6379",
		redis_queue="redis://redis-queue:6379",
		redis_socketio="redis://redis-queue:6379",
		socketio_port=9000,
		default_site=SITE,
		serve_default_site=True,
		mute_emails=True,
		pause_scheduler=True,
	)
	(SITES / "common_site_config.json").write_text(json.dumps(common))
	(SITES / "common_site_config.json").chmod(0o600)
	(SITES / "apps.txt").write_text("frappe\ncrm\nrecuite_billing\n")
	import frappe
	from frappe.installer import _new_site, install_app, update_site_config

	frappe.init(site=SITE, sites_path=".", new_site=True)
	_new_site(
		db_name="billing_test",
		site=SITE,
		db_type="mariadb",
		db_host="db",
		db_port=3306,
		db_root_username="root",
		db_root_password=os.environ["BILLING_TEST_DB_PASSWORD"],
		admin_password=os.environ["BILLING_TEST_ADMIN_PASSWORD"],
		install_apps=[],
		mariadb_user_host_login_scope="%",
	)
	frappe.destroy()
	frappe.init(site=SITE, sites_path=".")
	for key, value in dict(
		mute_emails=True,
		pause_scheduler=True,
		allow_tests=True,
		socketio_port=18082,
		host_name="http://billing-test.localhost:18082",
	).items():
		update_site_config(key, value)
	frappe.connect()
	# Isolated synthetic-site actor; this is not a request handler.
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	frappe.set_user("Administrator")
	install_app("crm")
	install_app("recuite_billing")
	from frappe.desk.page.setup_wizard.setup_wizard import (
		enable_setup_wizard_complete,
		get_setup_stages,
		process_setup_stages,
	)

	args = frappe._dict(
		language="English",
		lang="English",
		country="Ukraine",
		timezone="Europe/Kyiv",
		currency="UAH",
		enable_telemetry=0,
	)
	stages = get_setup_stages(args)
	for stage in stages:
		stage["tasks"] = [
			task
			for task in stage["tasks"]
			if not (
				task.get("app_name") == "crm"
				and task["fn"].__module__ == "crm.demo.api"
				and task["fn"].__name__ == "create_demo_data"
			)
		]
	if process_setup_stages(stages, args)["status"] != "ok":
		raise ValueError("Framework setup failed")
	enable_setup_wizard_complete("crm")
	frappe.db.set_single_value("System Settings", "enable_scheduler", 0)
	frappe.db.set_single_value("FCRM Settings", "currency", "UAH")
	# Separate HTTP/restore processes must see the synthetic fixtures.
	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()
	frappe.destroy()
	(SITES / SITE / "site_config.json").chmod(0o600)


if __name__ == "__main__":
	output = io.StringIO()
	try:
		with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
			bootstrap()
	except Exception:
		import traceback

		details = output.getvalue() + traceback.format_exc()
		for key in ("BILLING_TEST_DB_PASSWORD", "BILLING_TEST_ADMIN_PASSWORD"):
			if os.environ.get(key):
				details = details.replace(os.environ[key], "[redacted]")
		log = Path("/tmp/billing-bootstrap.log")
		log.write_text(details)
		log.chmod(0o600)
		print("Bootstrap failed; inspect /tmp/billing-bootstrap.log in this test container")
		raise SystemExit(1)
	print(json.dumps({"site": SITE, "created": True, "emails_muted": True}))
