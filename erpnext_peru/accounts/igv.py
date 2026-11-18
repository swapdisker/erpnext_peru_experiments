# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""IGV tax categories, templates and rules for a Peruvian company.

Rate
----
The rate applied to taxed operations is 18% (SUNAT, "Concepto, tasa y
operaciones gravadas - IGV"). That 18% is the sum of the IGV itself and the
Impuesto de Promoción Municipal (IPM); Ley N.° 32387 moves part of it from one
to the other each year (2026: 15.5% + 2.5%) without changing the total. Both
are declared and booked together, so one 18% row on account 40111 is used.

The reduced rate for small restaurants, hotels and tourist lodging is not set
up here.

What is created (nothing existing is modified, except as reported)
------------------------------------------------------------------
* Tax categories: IGV - Gravado / Exonerado / Inafecto / Exportación.
* Sales templates, one per category, tagged with the SUNAT catalogue 07 code.
  The taxed one becomes the company's default.
* Purchase templates for taxed, exempt and unaffected purchases. On a taxed
  purchase the IGV is debited to 40111 as tax credit, apart from the cost.
* Tax rules, so that choosing a tax category on a document picks its template.

ERPNext creates a "Peru Tax" template at 16% with every Peruvian company. It
is disabled here, because that rate is not the applicable one.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext_peru.overrides.common import PeruValidationError, is_peru_company

IGV_RATE = 18.0
IGV_ACCOUNT_NUMBER = "40111"  # PCGE: IGV – Cuenta propia

CATEGORY_GRAVADO = "IGV - Gravado"
CATEGORY_EXONERADO = "IGV - Exonerado"
CATEGORY_INAFECTO = "IGV - Inafecto"
CATEGORY_EXPORTACION = "IGV - Exportación"
TAX_CATEGORIES = (CATEGORY_GRAVADO, CATEGORY_EXONERADO, CATEGORY_INAFECTO, CATEGORY_EXPORTACION)

# title, tax category, rate, SUNAT catalogue 07 code, row description
SALES_TEMPLATES = (
	("IGV 18% - Ventas gravadas", CATEGORY_GRAVADO, IGV_RATE, "10", "IGV 18%"),
	("IGV 0% - Ventas exoneradas", CATEGORY_EXONERADO, 0.0, "20", "Exonerado"),
	("IGV 0% - Ventas inafectas", CATEGORY_INAFECTO, 0.0, "30", "Inafecto"),
	("IGV 0% - Exportación", CATEGORY_EXPORTACION, 0.0, "40", "Exportación"),
)
# title, tax category, rate, row description
PURCHASE_TEMPLATES = (
	("IGV 18% - Compras gravadas", CATEGORY_GRAVADO, IGV_RATE, "IGV 18%"),
	("IGV 0% - Compras exoneradas", CATEGORY_EXONERADO, 0.0, "Exonerado"),
	("IGV 0% - Compras inafectas", CATEGORY_INAFECTO, 0.0, "Inafecto"),
)
DEFAULT_SALES_TEMPLATE = SALES_TEMPLATES[0][0]
DEFAULT_PURCHASE_TEMPLATE = PURCHASE_TEMPLATES[0][0]

SALES_DOCTYPE = "Sales Taxes and Charges Template"
PURCHASE_DOCTYPE = "Purchase Taxes and Charges Template"
ERPNEXT_DEFAULT_TEMPLATE_TITLE = "Peru Tax"


class IgvSetupError(PeruValidationError):
	pass


def setup_igv(company: str) -> dict:
	"""Create the IGV categories, templates and rules of ``company``. Idempotent.

	Returns a report with ``created``, ``existing``, ``disabled``,
	``default_changed`` and ``warnings`` lists.
	"""
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(frappe.bold(company or "")), exc=IgvSetupError)
	if not is_peru_company(company):
		frappe.throw(
			_("Company {0} is not a Peruvian company.").format(frappe.bold(company)), exc=IgvSetupError
		)

	account = get_igv_account(company)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	report = frappe._dict(
		company=company,
		igv_account=account,
		created=[],
		existing=[],
		disabled=[],
		default_changed=[],
		warnings=[],
	)
	_check_rounding_method(report)

	report.disabled += disable_erpnext_default_templates(company, abbr)

	for name in TAX_CATEGORIES:
		if frappe.db.exists("Tax Category", name):
			report.existing.append(f"Tax Category: {name}")
		else:
			frappe.get_doc({"doctype": "Tax Category", "title": name}).insert(ignore_permissions=True)
			report.created.append(f"Tax Category: {name}")

	for title, category, rate, affectation, description in SALES_TEMPLATES:
		name = _ensure_template(
			SALES_DOCTYPE,
			company,
			abbr,
			title,
			category,
			account,
			rate,
			description,
			report,
			is_default=title == DEFAULT_SALES_TEMPLATE,
			extra={"pe_igv_affectation_type": affectation},
		)
		_ensure_tax_rule("Sales", company, category, name, report)

	for title, category, rate, description in PURCHASE_TEMPLATES:
		name = _ensure_template(
			PURCHASE_DOCTYPE,
			company,
			abbr,
			title,
			category,
			account,
			rate,
			description,
			report,
			is_default=title == DEFAULT_PURCHASE_TEMPLATE,
			row_extra={"category": "Total", "add_deduct_tax": "Add"},
		)
		_ensure_tax_rule("Purchase", company, category, name, report)

	return report


def _check_rounding_method(report):
	"""Warn when the site rounds half-way amounts to the even digit.

	With banker's rounding the IGV of S/ 0.25 (0.045) becomes 0.04 instead of
	0.05. The setting is site-wide, so it is reported and not changed here.
	"""
	method = frappe.db.get_single_value("System Settings", "rounding_method") or ""
	if method.startswith("Banker"):
		report.warnings.append(
			_(
				"This site rounds with {0}: an IGV amount that falls exactly on half a céntimo is rounded to the even digit (0.045 becomes 0.04). Ask the accountant whether System Settings > Rounding Method should be Commercial Rounding."
			).format(method)
		)


def get_igv_account(company: str) -> str:
	"""Name of the company's account 40111, which must be a ledger of type Tax."""
	row = frappe.db.get_value(
		"Account",
		{"company": company, "account_number": IGV_ACCOUNT_NUMBER},
		["name", "is_group", "account_type"],
		as_dict=True,
	)
	if not row:
		frappe.throw(
			_(
				"Company {0} has no account {1} (IGV – Cuenta propia). Apply the PCGE to the company first."
			).format(frappe.bold(company), IGV_ACCOUNT_NUMBER),
			exc=IgvSetupError,
		)
	if row.is_group:
		frappe.throw(
			_(
				"Account {0} is a group account in {1}. The IGV templates need an account that accepts entries."
			).format(row.name, frappe.bold(company)),
			exc=IgvSetupError,
		)
	if row.account_type != "Tax":
		frappe.throw(
			_("Account {0} must have the account type Tax to be used in tax templates.").format(row.name),
			exc=IgvSetupError,
		)
	return row.name


def disable_erpnext_default_templates(company, abbr) -> list[str]:
	"""Disable the 16% "Peru Tax" templates ERPNext creates on its own. Returns what was disabled."""
	disabled = []
	name = f"{ERPNEXT_DEFAULT_TEMPLATE_TITLE} - {abbr}"
	for doctype in (SALES_DOCTYPE, PURCHASE_DOCTYPE, "Item Tax Template"):
		row = frappe.db.get_value(
			doctype, {"name": name, "company": company}, ["name", "disabled"], as_dict=True
		)
		if not row or row.disabled:
			continue
		values = {"disabled": 1}
		if doctype != "Item Tax Template":
			values["is_default"] = 0
		frappe.db.set_value(doctype, name, values)
		disabled.append(f"{doctype}: {name}")
	return disabled


def _ensure_template(
	doctype,
	company,
	abbr,
	title,
	category,
	account,
	rate,
	description,
	report,
	is_default=False,
	extra=None,
	row_extra=None,
):
	name = f"{title} - {abbr}"
	if frappe.db.exists(doctype, name):
		report.existing.append(f"{doctype}: {name}")
		return name

	make_default = False
	if is_default:
		current_default = frappe.db.get_value(doctype, {"company": company, "is_default": 1, "disabled": 0})
		make_default = True
		if current_default:
			report.default_changed.append(f"{doctype}: {current_default} -> {name}")

	row = {
		"charge_type": "On Net Total",
		"account_head": account,
		"rate": flt(rate),
		"description": description,
	}
	row.update(row_extra or {})
	doc = frappe.get_doc(
		{
			"doctype": doctype,
			"title": title,
			"company": company,
			"tax_category": category,
			"is_default": 1 if make_default else 0,
			"taxes": [row],
		}
	)
	doc.update(extra or {})
	doc.insert(ignore_permissions=True)
	if doc.name != name:
		frappe.throw(_("Unexpected template name {0}.").format(doc.name), exc=IgvSetupError)
	report.created.append(f"{doctype}: {name}")
	return name


def _ensure_tax_rule(tax_type, company, category, template, report):
	template_field = "sales_tax_template" if tax_type == "Sales" else "purchase_tax_template"
	existing = frappe.db.get_value(
		"Tax Rule", {"tax_type": tax_type, "company": company, "tax_category": category}, "name"
	)
	label = f"Tax Rule: {tax_type} / {category}"
	if existing:
		report.existing.append(label)
		return
	frappe.get_doc(
		{
			"doctype": "Tax Rule",
			"tax_type": tax_type,
			"company": company,
			"tax_category": category,
			template_field: template,
			"priority": 1,
		}
	).insert(ignore_permissions=True)
	report.created.append(label)
