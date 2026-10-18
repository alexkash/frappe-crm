app_name = "recuite_billing"
app_title = "Документи"
app_publisher = "Recuite"
app_description = "Ukrainian billing documents for Frappe CRM"
app_email = "support@example.invalid"
app_license = "MIT"
required_apps = ["crm"]
after_install = "recuite_billing.install.after_install"
after_migrate = "recuite_billing.install.after_migrate"
app_include_js = ["/assets/recuite_billing/js/navigation.js"]

has_permission = {
	"UA Contract": "recuite_billing.permissions.has_document_permission",
	"UA Invoice": "recuite_billing.permissions.has_document_permission",
	"UA Act": "recuite_billing.permissions.has_document_permission",
	"UA Print Asset": "recuite_billing.permissions.has_document_permission",
	"File": "recuite_billing.permissions.has_file_permission",
}
permission_query_conditions = {
	"UA Contract": "recuite_billing.permissions.contract_query_conditions",
	"UA Invoice": "recuite_billing.permissions.invoice_query_conditions",
	"UA Act": "recuite_billing.permissions.act_query_conditions",
}
override_doctype_class = {"File": "recuite_billing.overrides.file.BillingFile"}
override_whitelisted_methods = {
	"frappe.utils.print_format.download_pdf": "recuite_billing.printing.download_pdf",
	"frappe.utils.print_format.download_multi_pdf": "recuite_billing.printing.download_multi_pdf",
	"frappe.utils.print_format.download_multi_pdf_async": "recuite_billing.printing.download_multi_pdf_async",
}
pdf_body_html = "recuite_billing.printing.pdf_body_html"
on_print_pdf = "recuite_billing.printing.prevent_archive_rerender"
doctype_js = {
	"UA Contract": "public/js/billing.js",
	"UA Invoice": "public/js/billing.js",
	"UA Act": "public/js/billing.js",
}
