app_name = "erpnext_peru"
app_title = "ERPNext Peru"
app_publisher = "erpnext_peru contributors"
app_description = "Peruvian localization for ERPNext"
app_email = ""
app_license = "GPL-3.0"
required_apps = ["erpnext"]

after_install = "erpnext_peru.setup.install.after_install"
after_migrate = "erpnext_peru.setup.install.after_migrate"

# The tests need a site on which the ERPNext setup wizard has run.
before_tests = "erpnext.setup.utils.before_tests"

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
