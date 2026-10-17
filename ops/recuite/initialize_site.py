import json
import sys

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import (
	enable_setup_wizard_complete,
	get_setup_stages,
	process_setup_stages,
)

credentials = json.load(sys.stdin)
assert credentials.get("smtp_password")
frappe.init(site="crm.recuite.com", sites_path="/home/frappe/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
assert frappe.conf.mute_emails is True
assert frappe.conf.pause_scheduler is True
assert all(
	frappe.db.count(doctype) == 0
	for doctype in [
		"CRM Lead",
		"CRM Deal",
		"CRM Organization",
		"Contact",
		"CRM Task",
		"FCRM Note",
		"Email Queue",
	]
)
# CRM adds demo records via a setup task; run the normal Framework stages without it.
if not frappe.is_setup_complete():
	args = frappe._dict(
		language="English",
		lang="English",
		country="Ukraine",
		timezone="Europe/Kyiv",
		currency="UAH",
		enable_telemetry=0,
	)
	stages = get_setup_stages(args)
	demo_tasks = [task for stage in stages for task in stage["tasks"] if task.get("app_name") == "crm"]
	assert len(demo_tasks) == 1
	assert demo_tasks[0]["fn"].__module__ == "crm.demo.api"
	assert demo_tasks[0]["fn"].__name__ == "create_demo_data"
	stages = [
		{**stage, "tasks": [task for task in stage["tasks"] if task not in demo_tasks]} for stage in stages
	]
	result = process_setup_stages(stages, args)
	assert result["status"] == "ok"
	enable_setup_wizard_complete("crm")
assert frappe.is_setup_complete()
assert frappe.get_system_settings("setup_complete")
assert not frappe.db.get_default("crm_demo_data_created")

account = (
	frappe.get_doc("Email Account", "Cloudflare SMTP")
	if frappe.db.exists("Email Account", "Cloudflare SMTP")
	else frappe.new_doc("Email Account")
)
account.update(
	dict(
		email_account_name="Cloudflare SMTP",
		email_id="hello@recuite.com",
		auth_method="Basic",
		login_id_is_different=1,
		login_id="api_token",
		password=credentials["smtp_password"],
		enable_incoming=0,
		default_incoming=0,
		enable_outgoing=1,
		default_outgoing=1,
		smtp_server="smtp.mx.cloudflare.net",
		smtp_port="465",
		use_ssl_for_outgoing=1,
		use_tls=0,
		no_smtp_authentication=0,
		always_use_account_email_id_as_sender=1,
	)
)
account.save(ignore_permissions=True)
account.validate_smtp_conn()
frappe.db.commit()
assert account.get_password("password") == credentials["smtp_password"]
counts = {
	doctype: frappe.db.count(doctype)
	for doctype in [
		"CRM Lead",
		"CRM Deal",
		"CRM Organization",
		"Contact",
		"CRM Contacts",
		"CRM Task",
		"FCRM Note",
		"Email Queue",
	]
}
assert all(value == 0 for value in counts.values()), counts
assert frappe.db.count("User", {"name": ["not in", ["Administrator", "Guest"]]}) == 0
print(
	json.dumps(
		{
			"setup_complete": True,
			"demo_data": False,
			"smtp_auth_valid": True,
			"messages_sent": 0,
			"empty_records": counts,
		}
	)
)
frappe.destroy()
