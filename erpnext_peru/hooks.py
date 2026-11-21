app_name = "erpnext_peru"
app_title = "ERPNext Peru"
app_publisher = "erpnext_peru contributors"
app_description = "Peruvian localization for ERPNext"
app_email = ""
app_license = "GPL-3.0"
required_apps = ["erpnext"]

# The icon on the apps screen (the home page). Frappe redirects "/app/peru" to
# the workspace's /desk address.
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/erpnext_peru/images/erpnext_peru_logo.svg",
		"title": "Peru",
		"route": "/app/peru",
		"has_permission": "erpnext_peru.setup.apps_screen.has_app_permission",
	}
]

before_install = "erpnext_peru.setup.install.before_install"
after_install = "erpnext_peru.setup.install.after_install"
after_migrate = "erpnext_peru.setup.install.after_migrate"

# Kept by ERPNext's "Delete Company Transactions": a series carries the last
# number issued, which may continue the numbering of a previous system.
company_data_to_be_ignored = ["SUNAT Voucher Series"]

# The tests need a site on which the ERPNext setup wizard has run.
before_tests = "erpnext_peru.tests.utils.prepare_site"

doctype_js = {"Company": "public/js/company.js", "Address": "public/js/address.js"}

doc_events = {
	"Company": {
		"validate": "erpnext_peru.overrides.company.validate",
		"on_update": "erpnext_peru.overrides.company.on_update",
	},
	"Customer": {
		"validate": "erpnext_peru.overrides.party.validate",
	},
	"Supplier": {
		"validate": "erpnext_peru.overrides.party.validate",
	},
	"Address": {
		"validate": "erpnext_peru.overrides.address.validate",
	},
	"Sales Invoice": {
		"validate": "erpnext_peru.overrides.sales_invoice.validate",
		"before_submit": "erpnext_peru.overrides.sales_invoice.before_submit",
		"on_trash": "erpnext_peru.overrides.sales_invoice.on_trash",
	},
	# ERPNext's "Delete Company Transactions". Its "Retry" of a failed deletion
	# saves the submitted record instead of submitting it again.
	"Transaction Deletion Record": {
		"before_submit": "erpnext_peru.overrides.transaction_deletion.before_submit",
		"before_update_after_submit": "erpnext_peru.overrides.transaction_deletion.before_submit",
	},
	"Purchase Invoice": {
		"validate": "erpnext_peru.overrides.purchase_invoice.validate",
		"before_submit": "erpnext_peru.overrides.purchase_invoice.before_submit",
	},
}
