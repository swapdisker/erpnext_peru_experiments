# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Fixtures shared by the integration tests.

All data is synthetic. The base fixtures (companies, item, price lists) are
created once and committed; every test rolls its own changes back.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from erpnext_peru.utils.identity import ruc_check_digit

PERU_COMPANY = "_Test Peru SAC"
PERU_ABBR = "_TPE"
FOREIGN_COMPANY = "_Test Foreign Inc"
FOREIGN_ABBR = "_TFI"
ITEM = "_Test Peru Service"
SELLING_PRICE_LIST = "_Test Peru Selling"
BUYING_PRICE_LIST = "_Test Peru Buying"
CUSTOMER_GROUP = "_Test Peru Customers"
SUPPLIER_GROUP = "_Test Peru Suppliers"
TERRITORY = "_Test Peru Territory"
ITEM_GROUP = "_Test Peru Items"
UOM = "_Test Peru Unit"


PCGE_COMPANY = "_Test PCGE SAC"
PCGE_ABBR = "_TPG"


def make_ruc(body: int | str, prefix: str = "20") -> str:
	"""A syntactically valid RUC built from ``prefix`` and an 8-digit body."""
	first_ten = f"{prefix}{int(body):08d}"
	return first_ten + str(ruc_check_digit(first_ten))


COMPANY_RUC = make_ruc(60000001)


class PeruTestCase(IntegrationTestCase):
	"""Creates the shared fixtures and isolates every test with a rollback."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_fixtures()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_messages()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()


def prepare_site():
	"""Bring a fresh site to the state the fixtures below need: setup wizard done.

	This is the app's ``before_tests`` hook. ``ensure_fixtures`` calls it as well,
	because Frappe does not run that hook for every kind of test class. ERPNext
	no longer ships a function for this, so the wizard is run here.
	"""
	if frappe.db.exists("Warehouse Type", "Transit"):  # created by the wizard
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = frappe.utils.now_datetime().year
	setup_complete(
		{
			"currency": "USD",
			"full_name": "Test User",
			"company_name": "Wind Power LLC",
			"timezone": "America/New_York",
			"company_abbr": "WP",
			"industry": "Manufacturing",
			"country": "United States",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"language": "english",
			"company_tagline": "Testing",
			"email": "test@erpnext.com",
			"password": "test",
			"chart_of_accounts": "Standard",
		}
	)
	frappe.db.commit()
	if not frappe.db.exists("Warehouse Type", "Transit"):
		raise RuntimeError("The ERPNext setup wizard did not complete; the test site is not usable.")


def ensure_fixtures():
	frappe.set_user("Administrator")
	frappe.flags.mute_emails = True
	prepare_site()

	for currency in ("PEN", "USD"):
		if not frappe.db.get_value("Currency", currency, "enabled"):
			frappe.db.set_value("Currency", currency, "enabled", 1)

	_ensure_tree("Customer Group", CUSTOMER_GROUP, "customer_group_name", "parent_customer_group")
	_ensure_tree("Supplier Group", SUPPLIER_GROUP, "supplier_group_name", "parent_supplier_group")
	_ensure_tree("Territory", TERRITORY, "territory_name", "parent_territory")
	_ensure_tree("Item Group", ITEM_GROUP, "item_group_name", "parent_item_group")

	if not frappe.db.exists("UOM", UOM):
		frappe.get_doc({"doctype": "UOM", "uom_name": UOM}).insert()

	for name, selling in ((SELLING_PRICE_LIST, 1), (BUYING_PRICE_LIST, 0)):
		if not frappe.db.exists("Price List", name):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": name,
					"currency": "PEN",
					"selling": selling,
					"buying": 0 if selling else 1,
					"enabled": 1,
				}
			).insert()

	_ensure_company(PERU_COMPANY, PERU_ABBR, "Peru", "PEN", COMPANY_RUC)
	_ensure_company(FOREIGN_COMPANY, FOREIGN_ABBR, "United States", "USD", None)

	_ensure_usd_receivable()

	if not frappe.db.exists("Item", ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM,
				"item_name": ITEM,
				"item_group": ITEM_GROUP,
				"stock_uom": UOM,
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 1,
			}
		).insert()

	frappe.db.commit()  # nosemgrep: fixtures are created once for the whole run


def ensure_pcge_company():
	"""A Peruvian company whose chart is the PCGE, with the IGV templates. Created once."""
	from erpnext_peru.accounts.igv import setup_igv
	from erpnext_peru.accounts.pcge import apply_pcge

	ensure_fixtures()
	_ensure_company(PCGE_COMPANY, PCGE_ABBR, "Peru", "PEN", make_ruc(60000003))
	if not frappe.db.exists("Account", {"company": PCGE_COMPANY, "account_number": "40111"}):
		apply_pcge(PCGE_COMPANY, replace_existing=True)
	setup_igv(PCGE_COMPANY)
	# With perpetual inventory on, ERPNext demands stock accounts (Stock Received
	# But Not Billed...) on every purchase invoice. How inventory is booked under
	# the PCGE (purchases through 60/61 or perpetual) is left to the accountant,
	# so the test company runs with it off.
	if frappe.db.get_value("Company", PCGE_COMPANY, "enable_perpetual_inventory"):
		frappe.db.set_value("Company", PCGE_COMPANY, "enable_perpetual_inventory", 0)
		frappe.clear_cache(doctype="Company")
	frappe.db.commit()  # nosemgrep: fixtures are created once for the whole run


def pcge_account(code: str, company: str = PCGE_COMPANY) -> str:
	return frappe.db.get_value("Account", {"company": company, "account_number": code}, "name")


def _ensure_tree(doctype, name, name_field, parent_field):
	if frappe.db.exists(doctype, name):
		return
	root = frappe.db.get_value(doctype, {"is_group": 1, parent_field: ("is", "not set")}, "name")
	if not root:
		root_doc = frappe.get_doc(
			{"doctype": doctype, name_field: f"_Test Peru Root {doctype}", "is_group": 1}
		)
		root_doc.insert()
		root = root_doc.name
	frappe.get_doc({"doctype": doctype, name_field: name, parent_field: root, "is_group": 0}).insert()


def _ensure_company(name, abbr, country, currency, tax_id):
	if frappe.db.exists("Company", name):
		return
	frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": name,
			"abbr": abbr,
			"country": country,
			"default_currency": currency,
			"tax_id": tax_id,
			"create_chart_of_accounts_based_on": "Standard Template",
			"chart_of_accounts": "Standard",
		}
	).insert()


USD_RECEIVABLE = f"Debtors USD - {PERU_ABBR}"


def _ensure_usd_receivable():
	"""ERPNext books a foreign-currency invoice against a party account in that currency."""
	if frappe.db.exists("Account", USD_RECEIVABLE):
		return
	debtors = frappe.get_doc("Account", f"Debtors - {PERU_ABBR}")
	frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": "Debtors USD",
			"company": PERU_COMPANY,
			"parent_account": debtors.parent_account,
			"account_type": "Receivable",
			"account_currency": "USD",
			"root_type": debtors.root_type,
			"report_type": debtors.report_type,
		}
	).insert()


def account(company: str, account_type: str) -> str:
	return frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_type": account_type,
			"is_group": 0,
			"account_currency": frappe.get_cached_value("Company", company, "default_currency"),
		},
		"name",
	)


def make_customer(name, identity_type=None, identity_number=None, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_group": CUSTOMER_GROUP,
			"territory": TERRITORY,
			"pe_identity_type": identity_type,
			"pe_identity_number": identity_number,
			**kwargs,
		}
	)
	doc.insert()
	return doc


def make_supplier(name, identity_type=None, identity_number=None, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": name,
			"supplier_group": SUPPLIER_GROUP,
			"pe_identity_type": identity_type,
			"pe_identity_number": identity_number,
			**kwargs,
		}
	)
	doc.insert()
	return doc


def make_series(comprobante_type, series, company=PERU_COMPANY, current_number=0, enabled=1):
	doc = frappe.get_doc(
		{
			"doctype": "SUNAT Voucher Series",
			"company": company,
			"comprobante_type": comprobante_type,
			"series": series,
			"current_number": current_number,
			"enabled": enabled,
		}
	)
	doc.insert()
	return doc


def make_sales_invoice(
	customer, rate=100, qty=1, company=PERU_COMPANY, currency=None, conversion_rate=1, **kwargs
):
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	abbr = frappe.get_cached_value("Company", company, "abbr")
	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"company": company,
			"customer": customer,
			"posting_date": today(),
			"due_date": today(),
			"set_posting_time": 1,
			"currency": currency or company_currency,
			"conversion_rate": conversion_rate,
			"selling_price_list": SELLING_PRICE_LIST,
			"price_list_currency": company_currency,
			"plc_conversion_rate": 1,
			"ignore_pricing_rule": 1,
			"debit_to": USD_RECEIVABLE
			if (currency == "USD" and company == PERU_COMPANY)
			else account(company, "Receivable"),
			# Peruvian comprobantes are issued to the céntimo.
			"disable_rounded_total": 1,
			"cost_center": f"Main - {abbr}",
		}
	)
	doc.append(
		"items",
		{
			"item_code": ITEM,
			"qty": qty,
			"rate": rate,
			"uom": UOM,
			"conversion_factor": 1,
			"income_account": f"Sales - {abbr}",
			"cost_center": f"Main - {abbr}",
		},
	)
	doc.update(kwargs)
	doc.insert()
	return doc


def make_purchase_invoice(supplier, rate=100, qty=1, company=PERU_COMPANY, **kwargs):
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	abbr = frappe.get_cached_value("Company", company, "abbr")
	doc = frappe.new_doc("Purchase Invoice")
	doc.update(
		{
			"company": company,
			"supplier": supplier,
			"posting_date": today(),
			"due_date": today(),
			"set_posting_time": 1,
			"currency": company_currency,
			"conversion_rate": 1,
			"buying_price_list": BUYING_PRICE_LIST,
			"price_list_currency": company_currency,
			"plc_conversion_rate": 1,
			"ignore_pricing_rule": 1,
			"credit_to": account(company, "Payable"),
			"cost_center": f"Main - {abbr}",
		}
	)
	doc.append(
		"items",
		{
			"item_code": ITEM,
			"qty": qty,
			"rate": rate,
			"uom": UOM,
			"conversion_factor": 1,
			"expense_account": f"Cost of Goods Sold - {abbr}",
			"cost_center": f"Main - {abbr}",
		},
	)
	doc.update(kwargs)
	doc.insert()
	return doc


def make_return(invoice, **kwargs):
	"""Draft credit note (return) against a submitted Sales or Purchase Invoice."""
	if invoice.doctype == "Sales Invoice":
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return as mapper
	else:
		from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import make_debit_note as mapper
	doc = mapper(invoice.name)
	doc.update(kwargs)
	doc.insert()
	return doc
