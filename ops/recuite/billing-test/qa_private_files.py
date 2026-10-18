"""HTTP authorization regression on the isolated test backend; synthetic records only."""

import json
import os
import secrets
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import frappe
from recuite_billing.tests.helpers import contract, issuer, pdf_bytes, user


def main():
	os.chdir("/home/frappe/frappe-bench/sites")
	frappe.init(site="test_site", sites_path=".")
	frappe.connect()
	# Isolated synthetic-site actor; this is not a request handler.
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	frappe.set_user("Administrator")
	assert frappe.local.site == "test_site" and frappe.conf.db_name == "billing_test"

	first, second = issuer(), issuer()
	document = contract(owner=first)
	account = user("UA Billing Manager", first.name)
	api_key, api_secret = secrets.token_hex(16), secrets.token_hex(24)
	person = frappe.get_doc("User", account)
	person.api_key, person.api_secret = api_key, api_secret
	person.save(ignore_permissions=True)
	attachment = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": "synthetic-contract.pdf",
			"content": pdf_bytes(),
			"is_private": 1,
			"attached_to_doctype": document.doctype,
			"attached_to_name": document.name,
		}
	).insert()
	attachment.db_set("owner", account)
	# Separate HTTP/restore processes must see the synthetic fixtures.
	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()

	def request(path, *, authenticated=True, method="GET", data=None):
		headers = {"Host": "test_site", "Accept": "application/json"}
		if authenticated:
			headers["Authorization"] = f"token {api_key}:{api_secret}"
		if data is not None:
			headers["Content-Type"] = "application/json"
		request = Request(
			"http://127.0.0.1:8000" + path,
			headers=headers,
			method=method,
			data=json.dumps(data).encode() if data is not None else None,
		)
		try:
			with urlopen(request, timeout=15) as response:
				return response.status, response.read()
		except HTTPError as error:
			return error.code, error.read()

	try:
		resource = "/api/resource/File/" + quote(attachment.name)
		private = quote(attachment.file_url)
		assert request(resource)[0] == 200
		assert request(private)[0] == 200
		assert request(resource, authenticated=False)[0] in (401, 403)
		assert request(private, authenticated=False)[0] in (401, 403)
		assert request(resource, method="PUT", data={"is_private": 0})[0] >= 400
		permission = frappe.get_doc("User Permission", {"user": account, "allow": "UA Issuer"})
		permission.for_value = second.name
		permission.save(ignore_permissions=True)
		frappe.clear_cache(user=account)
		# Separate HTTP/restore processes must see the synthetic fixtures.
		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		assert request(resource)[0] == 403
		assert request(private)[0] == 403
		forged = json.loads(document.as_json())
		forged["issuer"], forged["bank_account"] = second.name, second.bank_accounts[0].name
		assert request("/api/method/frappe.client.save", method="POST", data={"doc": forged})[0] == 403
		assert frappe.db.get_value("UA Contract", document.name, "issuer") == first.name
		listing = "/api/resource/File?filters=" + quote(json.dumps({"name": attachment.name}))
		status, body = request(listing)
		assert status == 200 and json.loads(body)["data"] == []
		print(
			json.dumps(
				{
					"http_private_files": "PASS",
					"guest_denied": True,
					"public_conversion_denied": True,
					"revoked_owner_denied": True,
				}
			)
		)
	finally:
		frappe.db.rollback()
		# Isolated synthetic-site actor; this is not a request handler.
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user("Administrator")
		frappe.delete_doc("File", attachment.name, ignore_permissions=True)
		frappe.delete_doc("UA Contract", document.name, ignore_permissions=True)
		for name in frappe.get_all("User Permission", filters={"user": account}, pluck="name"):
			frappe.delete_doc("User Permission", name, ignore_permissions=True)
		frappe.delete_doc("User", account, ignore_permissions=True)
		for doc in (first, second):
			frappe.delete_doc("UA Issuer", doc.name, ignore_permissions=True)
		# Separate HTTP/restore processes must see the synthetic fixtures.
		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		frappe.destroy()


if __name__ == "__main__":
	main()
