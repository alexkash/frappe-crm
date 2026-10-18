"""Real form-encoded RPC, archive download and cancellation-payload regressions."""

import hashlib
import json
import os
import secrets
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import frappe


def main():
	os.chdir("/home/frappe/frappe-bench/sites")
	frappe.init(site="test_site")
	frappe.connect()
	# Isolated synthetic-site actor; this is not a request handler.
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	frappe.set_user("Administrator")
	assert frappe.conf.db_name == "billing_test"
	manifest = json.loads(Path(frappe.get_site_path("private", "billing-qa", "manifest.json")).read_text())
	invoice_info = next(row for row in manifest["documents"] if row["label"] == "invoice-with-scans")
	act_info = next(row for row in manifest["documents"] if row["label"] == "act-with-scans")
	invoice = frappe.get_doc("UA Invoice", invoice_info["name"])
	from recuite_billing.tests.helpers import user

	account = user("UA Billing Manager", invoice.issuer)
	key, secret = secrets.token_hex(16), secrets.token_hex(24)
	person = frappe.get_doc("User", account)
	person.api_key, person.api_secret = key, secret
	person.save(ignore_permissions=True)
	# Separate HTTP/restore processes must see the synthetic fixtures.
	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()

	def request(path, data=None, *, guest=False):
		headers = {"Host": "test_site"}
		if not guest:
			headers["Authorization"] = f"token {key}:{secret}"
		if data is not None:
			headers["Content-Type"] = "application/x-www-form-urlencoded"
		req = Request(
			"http://127.0.0.1:8000" + path,
			headers=headers,
			data=urlencode(data).encode() if data is not None else None,
		)
		try:
			with urlopen(req, timeout=30) as response:
				return response.status, response.read()
		except HTTPError as error:
			return error.code, error.read()

	created = None
	try:
		args = {
			"invoice": invoice.name,
			"period_from": "2026-03-01",
			"period_to": "2026-03-31",
			"items": json.dumps([{"invoice_item": invoice.items[0].name, "qty": "1.000000"}]),
		}
		status, body = request("/api/method/recuite_billing.api.create_act", args)
		assert status == 200, (status, body[:300])
		result = json.loads(body)["message"]
		created = result["name"] if not result["existing"] else None
		status, body = request("/api/method/recuite_billing.api.create_act", args)
		assert status == 200 and json.loads(body)["message"] == {"name": result["name"], "existing": True}
		doc = frappe.get_doc("UA Act", act_info["name"])
		payload = json.loads(doc.as_json())
		payload["docstatus"] = 2
		payload["items"][0]["qty"] = 0.5
		status, _body = request("/api/method/frappe.client.save", {"doc": json.dumps(payload)})
		assert status == 417
		frappe.db.rollback()
		assert frappe.db.get_value("UA Act", doc.name, "docstatus") == 1
		assert frappe.get_doc("UA Act", doc.name).items[0].qty == 1
		path = "/api/method/frappe.utils.print_format.download_pdf?doctype=UA%20Invoice&name=" + quote(
			invoice.name
		)
		status, content = request(path)
		assert status == 200 and hashlib.sha256(content).hexdigest() == invoice_info["sha256"]
		assert request(path, guest=True)[0] in (401, 403)
		status, content = request(
			"/api/method/frappe.utils.print_format.download_multi_pdf",
			{"doctype": "UA Invoice", "name": json.dumps([invoice.name])},
		)
		assert status == 200 and content.startswith(b"%PDF-")
		groups = {"UA Invoice": [invoice.name], "UA Act": [act_info["name"]]}
		grouped_args = {"doctype": json.dumps(groups), "name": "[]"}
		status, content = request(
			"/api/method/frappe.utils.print_format.download_multi_pdf", grouped_args
		)
		assert status == 200 and content.startswith(b"%PDF-"), (status, content[:300])
		status, body = request(
			"/api/method/frappe.utils.print_format.download_multi_pdf_async", grouped_args
		)
		assert status == 417, (status, body[:300])
		print(
			json.dumps(
				{
					"http_billing": "PASS",
					"form_encoded_act": True,
					"cancel_mutation_denied": True,
					"archive_download": True,
					"grouped_archive_download": True,
					"grouped_async_denied": True,
					"bulk_pdf": True,
					"guest_denied": True,
				}
			)
		)
	finally:
		frappe.db.rollback()
		# Isolated synthetic-site actor; this is not a request handler.
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user("Administrator")
		if created:
			frappe.delete_doc("UA Act", created, ignore_permissions=True)
		for name in frappe.get_all("User Permission", filters={"user": account}, pluck="name"):
			frappe.delete_doc("User Permission", name, ignore_permissions=True)
		frappe.delete_doc("User", account, ignore_permissions=True)
		# Separate HTTP/restore processes must see the synthetic fixtures.
		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		frappe.destroy()


if __name__ == "__main__":
	main()
