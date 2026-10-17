"""Back up and restore only synthetic billing_test into a new, private test site."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import frappe

os.chdir("/home/frappe/frappe-bench/sites")
assert not Path("billing_restore_test").exists(), "Restore target already exists; never overwrite it"
frappe.init(site="test_site")
frappe.connect()
frappe.set_user("Administrator")
assert frappe.conf.db_name == "billing_test"
manifest = json.loads(Path(frappe.get_site_path("private", "billing-qa", "manifest.json")).read_text())
encryption_key = frappe.conf.get("encryption_key")
from frappe.utils.backups import new_backup

backup = new_backup(ignore_files=False, compress=True)
paths = [
	str(Path(path).resolve())
	for path in (backup.backup_path_db, backup.backup_path_files, backup.backup_path_private_files)
]
frappe.destroy()


def bench(*args):
	result = subprocess.run(["bench", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	if result.returncode:
		message = result.stdout
		for key in ("BILLING_TEST_DB_PASSWORD", "BILLING_TEST_ADMIN_PASSWORD"):
			message = message.replace(os.environ[key], "[redacted]")
		print(message[-4000:])
		raise SystemExit(1)


password = os.environ["BILLING_TEST_DB_PASSWORD"]
bench(
	"new-site",
	"billing_restore_test",
	"--db-name",
	"billing_restore_test",
	"--db-root-password",
	password,
	"--admin-password",
	os.environ["BILLING_TEST_ADMIN_PASSWORD"],
	"--no-mariadb-socket",
)
bench(
	"--site",
	"billing_restore_test",
	"restore",
	paths[0],
	"--with-public-files",
	paths[1],
	"--with-private-files",
	paths[2],
	"--db-root-password",
	password,
)
config_path = Path("billing_restore_test/site_config.json")
config = json.loads(config_path.read_text())
if encryption_key:
	config["encryption_key"] = encryption_key
config.update({"pause_scheduler": 1, "mute_emails": 1, "allow_tests": True})
config_path.write_text(json.dumps(config))
bench("--site", "billing_restore_test", "migrate")
frappe.init(site="billing_restore_test")
frappe.connect()
frappe.set_user("Administrator")
assert frappe.conf.db_name == "billing_restore_test"
from recuite_billing.printing import get_document_pdf

for entry in manifest["documents"]:
	doc = frappe.get_doc(entry["doctype"], entry["name"])
	assert doc.pdf_sha256 == entry["sha256"]
	assert (
		hashlib.sha256(get_document_pdf(doc.doctype, doc.name).get_content()).hexdigest() == entry["sha256"]
	)
	for image in json.loads(doc.print_assets_snapshot or "{}").values():
		file = frappe.get_doc("File", image["file"])
		assert hashlib.sha256(file.get_content()).hexdigest() == image["sha256"]
assert frappe.get_doc("UA Contract", manifest["contract"]).organization == manifest["organization"]
assert frappe.get_doc("File", manifest["contract_file"]).get_content().startswith(b"%PDF-")
for role in ("UA Billing User", "UA Billing Reader", "UA Billing Manager"):
	assert frappe.db.exists("Role", role)
frappe.destroy()
print(
	json.dumps(
		{"result": "PASS", "restored_documents": len(manifest["documents"]), "target": "billing_restore_test"}
	)
)
