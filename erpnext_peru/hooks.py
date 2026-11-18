app_name = "erpnext_peru"
app_title = "ERPNext Peru"
app_publisher = "erpnext_peru contributors"
app_description = "Peruvian localization for ERPNext"
app_email = ""
app_license = "GPL-3.0"
required_apps = ["erpnext"]

# The icon on the apps screen. "/app/peru" also works on Frappe v16, which
# redirects it to the new /desk address.
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/erpnext_peru/images/erpnext_peru_logo.svg",
		"title": "Peru",
		"route": "/app/peru",
		"has_permission": "erpnext_peru.setup.apps_screen.has_app_permission",
	}
]

after_install = "erpnext_peru.setup.install.after_install"
after_migrate = "erpnext_peru.setup.install.after_migrate"

# The tests need a site on which the ERPNext setup wizard has run.
before_tests = "erpnext_peru.tests.utils.prepare_site"

doctype_js = {"Company": "public/js/company.js", "Address": "public/js/address.js"}

doc_events = {
	"Company": {
		"validate": "erpnext_peru.overrides.company.validate",
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
	"Purchase Invoice": {
		"validate": "erpnext_peru.overrides.purchase_invoice.validate",
		"before_submit": "erpnext_peru.overrides.purchase_invoice.before_submit",
	},
}
