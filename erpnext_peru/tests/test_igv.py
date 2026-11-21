# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""IGV templates on a company that runs on the PCGE (Annexure A: TX-UC-01, TX-UC-02)."""

import frappe
from erpnext.accounts.party import set_taxes
from frappe.utils import flt, today

from erpnext_peru.accounts.igv import (
	IGV_RATE,
	PURCHASE_TEMPLATES,
	SALES_TEMPLATES,
	TAX_CATEGORIES,
	IgvSetupError,
	setup_igv,
)
from erpnext_peru.overrides.common import ComprobanteError
from erpnext_peru.tests.utils import (
	BUYING_PRICE_LIST,
	FOREIGN_COMPANY,
	ITEM,
	PCGE_ABBR,
	PCGE_COMPANY,
	PERU_COMPANY,
	SELLING_PRICE_LIST,
	UOM,
	PeruTestCase,
	ensure_pcge_company,
	make_customer,
	make_return,
	make_ruc,
	make_series,
	make_supplier,
	pcge_account,
)

GRAVADO = f"IGV 18% - Ventas gravadas - {PCGE_ABBR}"
EXONERADO = f"IGV 0% - Ventas exoneradas - {PCGE_ABBR}"
INAFECTO = f"IGV 0% - Ventas inafectas - {PCGE_ABBR}"
EXPORTACION = f"IGV 0% - Exportación - {PCGE_ABBR}"
COMPRAS_GRAVADAS = f"IGV 18% - Compras gravadas - {PCGE_ABBR}"
COMPRAS_EXONERADAS = f"IGV 0% - Compras exoneradas - {PCGE_ABBR}"
DEFAULT = object()


def sales_invoice(customer, lines, template=DEFAULT, **kwargs):
	"""``lines`` is a list of (qty, rate). The default template is applied as the form does."""
	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"company": PCGE_COMPANY,
			"customer": customer,
			"posting_date": today(),
			"due_date": today(),
			"set_posting_time": 1,
			"currency": "PEN",
			"conversion_rate": 1,
			"selling_price_list": SELLING_PRICE_LIST,
			"price_list_currency": "PEN",
			"plc_conversion_rate": 1,
			"ignore_pricing_rule": 1,
			"disable_rounded_total": 1,
		}
	)
	for qty, rate in lines:
		doc.append(
			"items",
			{
				"item_code": ITEM,
				"qty": qty,
				"rate": rate,
				"uom": UOM,
				"conversion_factor": 1,
				"cost_center": f"Main - {PCGE_ABBR}",
			},
		)
	doc.update(kwargs)
	if template is DEFAULT:
		doc.set_taxes()  # what the browser does for a new document
	elif template:
		doc.taxes_and_charges = template
		doc.set_taxes()
	doc.insert()
	return doc


def purchase_invoice(supplier, rate, template=COMPRAS_GRAVADAS, **kwargs):
	doc = frappe.new_doc("Purchase Invoice")
	doc.update(
		{
			"company": PCGE_COMPANY,
			"supplier": supplier,
			"posting_date": today(),
			"due_date": today(),
			"set_posting_time": 1,
			"currency": "PEN",
			"conversion_rate": 1,
			"buying_price_list": BUYING_PRICE_LIST,
			"price_list_currency": "PEN",
			"plc_conversion_rate": 1,
			"ignore_pricing_rule": 1,
			"disable_rounded_total": 1,
		}
	)
	doc.append(
		"items",
		{
			"item_code": ITEM,
			"qty": 1,
			"rate": rate,
			"uom": UOM,
			"conversion_factor": 1,
			"expense_account": pcge_account("6011"),
			"cost_center": f"Main - {PCGE_ABBR}",
		},
	)
	doc.update(kwargs)
	if template:
		doc.taxes_and_charges = template
		doc.set_taxes()
	doc.insert()
	return doc


def ledger(doc):
	rows = frappe.get_all(
		"GL Entry", {"voucher_no": doc.name, "is_cancelled": 0}, ["account", "debit", "credit"]
	)
	return sorted(
		(frappe.db.get_value("Account", r.account, "account_number"), flt(r.debit, 2), flt(r.credit, 2))
		for r in rows
	)


class IgvCase(PeruTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_pcge_company()

	def setUp(self):
		super().setUp()
		self.customer = make_customer("_Test PE IGV Customer", "6", make_ruc(90000001)).name
		self.anonymous = make_customer("_Test PE IGV Anonymous").name
		self.supplier = make_supplier("_Test PE IGV Supplier", "6", make_ruc(90000002)).name
		make_series("01", "F001", company=PCGE_COMPANY)
		make_series("03", "B001", company=PCGE_COMPANY)
		make_series("07", "FC01", company=PCGE_COMPANY)


class TestIgvSetup(IgvCase):
	def test_what_is_set_up(self):
		for name in TAX_CATEGORIES:
			self.assertTrue(frappe.db.exists("Tax Category", name))
		igv_account = pcge_account("40111")
		self.assertEqual(igv_account, f"40111 - IGV – Cuenta propia - {PCGE_ABBR}")
		for title, category, rate, affectation, _description in SALES_TEMPLATES:
			template = frappe.get_doc("Sales Taxes and Charges Template", f"{title} - {PCGE_ABBR}")
			with self.subTest(template=template.name):
				self.assertEqual(template.tax_category, category)
				self.assertEqual(template.pe_igv_affectation_type, affectation)
				self.assertEqual(template.disabled, 0)
				self.assertEqual(len(template.taxes), 1)
				row = template.taxes[0]
				self.assertEqual(
					(row.charge_type, row.account_head, flt(row.rate)), ("On Net Total", igv_account, rate)
				)
				self.assertEqual(
					frappe.db.get_value(
						"Tax Rule",
						{"tax_type": "Sales", "company": PCGE_COMPANY, "tax_category": category},
						"sales_tax_template",
					),
					template.name,
				)
		for title, category, rate, _description in PURCHASE_TEMPLATES:
			template = frappe.get_doc("Purchase Taxes and Charges Template", f"{title} - {PCGE_ABBR}")
			with self.subTest(template=template.name):
				row = template.taxes[0]
				self.assertEqual(
					(row.account_head, flt(row.rate), row.category, row.add_deduct_tax),
					(igv_account, rate, "Total", "Add"),
				)
				self.assertEqual(template.tax_category, category)

	def test_rate_and_affectation_codes(self):
		self.assertEqual(IGV_RATE, 18.0)
		self.assertEqual(
			[(t[2], t[3]) for t in SALES_TEMPLATES], [(18.0, "10"), (0.0, "20"), (0.0, "30"), (0.0, "40")]
		)
		for code, text in (("10", "Gravado"), ("20", "Exonerado"), ("30", "Inafecto"), ("40", "Exportación")):
			self.assertIn(text, frappe.db.get_value("SUNAT IGV Affectation Type", code, "description"))
		self.assertEqual(frappe.db.count("SUNAT IGV Affectation Type"), 18)

	def test_defaults(self):
		self.assertEqual(
			frappe.get_all(
				"Sales Taxes and Charges Template", {"company": PCGE_COMPANY, "is_default": 1}, pluck="name"
			),
			[GRAVADO],
		)
		self.assertEqual(
			frappe.get_all(
				"Purchase Taxes and Charges Template",
				{"company": PCGE_COMPANY, "is_default": 1},
				pluck="name",
			),
			[COMPRAS_GRAVADAS],
		)

	def test_setup_is_idempotent(self):
		counts = {
			doctype: frappe.db.count(doctype, {"company": PCGE_COMPANY})
			for doctype in (
				"Sales Taxes and Charges Template",
				"Purchase Taxes and Charges Template",
				"Tax Rule",
			)
		}
		report = setup_igv(PCGE_COMPANY)
		self.assertEqual(report.created, [])
		self.assertEqual(len(report.existing), 4 + 4 + 4 + 3 + 3)
		for doctype, count in counts.items():
			self.assertEqual(frappe.db.count(doctype, {"company": PCGE_COMPANY}), count)
		self.assertEqual(counts["Sales Taxes and Charges Template"], 4)
		self.assertEqual(counts["Purchase Taxes and Charges Template"], 3)
		self.assertEqual(counts["Tax Rule"], 7)

	def test_local_changes_to_a_template_survive(self):
		frappe.db.set_value("Sales Taxes and Charges Template", EXONERADO, "disabled", 1)
		setup_igv(PCGE_COMPANY)
		self.assertEqual(frappe.db.get_value("Sales Taxes and Charges Template", EXONERADO, "disabled"), 1)

	def test_requirements(self):
		with self.assertRaises(IgvSetupError):
			setup_igv(PERU_COMPANY)  # no account 40111: the PCGE has not been applied
		with self.assertRaises(IgvSetupError):
			setup_igv(FOREIGN_COMPANY)
		with self.assertRaises(IgvSetupError):
			setup_igv("No such company")
		frappe.db.set_value("Account", pcge_account("40111"), "account_type", "")
		with self.assertRaises(IgvSetupError):
			setup_igv(PCGE_COMPANY)

	def test_rounding_warning(self):
		frappe.db.set_single_value("System Settings", "rounding_method", "Banker's Rounding")
		[warning] = setup_igv(PCGE_COMPANY).warnings
		self.assertIn("Banker's Rounding", warning)
		self.assertNotIn("<", warning)  # plain text: the form escapes it
		frappe.db.set_single_value("System Settings", "rounding_method", "Commercial Rounding")
		self.assertEqual(setup_igv(PCGE_COMPANY).warnings, [])

	def test_chart_cannot_be_replaced_once_igv_is_set_up(self):
		"""ERPNext would refuse half way; the preview says so before anything is tried."""
		from erpnext_peru.accounts.pcge import PcgeApplyError, apply_pcge

		setup_igv(PCGE_COMPANY)
		frappe.db.delete("GL Entry", {"company": PCGE_COMPANY})  # replacing needs no ledger entries
		for dry_run in (True, False):
			with self.subTest(dry_run=dry_run), self.assertRaises(PcgeApplyError) as raised:
				apply_pcge(PCGE_COMPANY, replace_existing=True, dry_run=dry_run)
			self.assertIn("IGV is already set up", str(raised.exception))
		self.assertTrue(frappe.db.exists("Tax Rule", {"company": PCGE_COMPANY}))
		self.assertEqual(apply_pcge(PCGE_COMPANY, dry_run=True).created, [])  # adding stays possible

	def test_tax_category_selects_the_template(self):
		"""What the form asks the server when the user picks a tax category."""
		expected = {
			"IGV - Gravado": GRAVADO,
			"IGV - Exonerado": EXONERADO,
			"IGV - Inafecto": INAFECTO,
			"IGV - Exportación": EXPORTACION,
		}
		for category, template in expected.items():
			self.assertEqual(
				set_taxes(self.customer, "Customer", today(), PCGE_COMPANY, tax_category=category), template
			)
		self.assertEqual(
			set_taxes(self.supplier, "Supplier", today(), PCGE_COMPANY, tax_category="IGV - Gravado"),
			COMPRAS_GRAVADAS,
		)
		self.assertEqual(
			set_taxes(self.supplier, "Supplier", today(), PCGE_COMPANY, tax_category="IGV - Exonerado"),
			COMPRAS_EXONERADAS,
		)


class TestSalesWithIgv(IgvCase):
	def test_tx_uc_01_factura_with_igv(self):
		invoice = sales_invoice(self.customer, [(1, 1000)])
		self.assertEqual(invoice.taxes_and_charges, GRAVADO)  # the default, not chosen by hand
		self.assertEqual(flt(invoice.net_total, 2), 1000.00)
		self.assertEqual(flt(invoice.total_taxes_and_charges, 2), 180.00)
		self.assertEqual(flt(invoice.grand_total, 2), 1180.00)
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "F001-00000001")
		self.assertEqual(
			ledger(invoice),
			[("1212", 1180.00, 0.0), ("40111", 0.0, 180.00), ("70121", 0.0, 1000.00)],
		)
		self.assertEqual(flt(invoice.outstanding_amount, 2), 1180.00)

	def test_amounts_with_centimos(self):
		cases = [
			# lines, net, igv, total
			([(1, 1234.56)], 1234.56, 222.22, 1456.78),
			([(3, 33.33)], 99.99, 18.00, 117.99),
			([(1, 99.50)], 99.50, 17.91, 117.41),
			([(1, 0.03)], 0.03, 0.01, 0.04),
			([(2, 149.99), (5, 12.10), (1, 0.01)], 360.49, 64.89, 425.38),
			([(1, 84.75)], 84.75, 15.26, 100.01),  # 15.255: see test_half_centimo_rounding
		]
		for lines, net, igv, total in cases[:5]:
			with self.subTest(lines=lines):
				invoice = sales_invoice(self.customer, lines)
				self.assertEqual(flt(invoice.net_total, 2), net)
				self.assertEqual(flt(invoice.total_taxes_and_charges, 2), igv)
				self.assertEqual(flt(invoice.grand_total, 2), total)
				invoice.submit()
				entries = ledger(invoice)
				self.assertEqual(flt(sum(e[1] for e in entries), 2), flt(sum(e[2] for e in entries), 2))
				self.assertIn(("1212", total, 0.0), entries)
				self.assertIn(("40111", 0.0, igv), entries)

	def test_half_centimo_rounding_follows_the_site_setting(self):
		"""0.25 x 18% = 0.045 and 1.25 x 18% = 0.225: the two methods disagree."""
		expected = {
			"Banker's Rounding": {0.25: 0.04, 1.25: 0.22, 0.75: 0.14},
			"Commercial Rounding": {0.25: 0.05, 1.25: 0.23, 0.75: 0.14},
		}
		for method, cases in expected.items():
			frappe.db.set_single_value("System Settings", "rounding_method", method)
			frappe.clear_cache()
			frappe.local.rounding_method = None
			for net, igv in cases.items():
				with self.subTest(method=method, net=net):
					invoice = sales_invoice(self.customer, [(1, net)])
					self.assertEqual(flt(invoice.total_taxes_and_charges, 2), igv)

	def test_exempt_unaffected_and_export_sales_post_no_igv(self):
		for template in (EXONERADO, INAFECTO, EXPORTACION):
			with self.subTest(template=template):
				invoice = sales_invoice(self.customer, [(1, 1000)], template=template)
				self.assertEqual(len(invoice.taxes), 1)  # the line is there, at zero
				self.assertEqual(flt(invoice.taxes[0].tax_amount, 2), 0.0)
				self.assertEqual(flt(invoice.grand_total, 2), 1000.00)
				invoice.submit()
				self.assertEqual(ledger(invoice), [("1212", 1000.00, 0.0), ("70121", 0.0, 1000.00)])

	def test_invoice_without_any_igv_line_is_blocked(self):
		invoice = sales_invoice(self.customer, [(1, 1000)], template=None)
		self.assertEqual(invoice.taxes, [])
		with self.assertRaises(ComprobanteError) as ctx:
			invoice.submit()
		self.assertIn("IGV", str(ctx.exception))
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, "docstatus"), 0)

	def test_an_invoice_whose_only_tax_row_is_not_igv_is_blocked(self):
		"""A freight charge states nothing about IGV."""
		invoice = sales_invoice(self.customer, [(1, 1000)], template=None)
		invoice.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": pcge_account("7599"),
				"tax_amount": 10,
				"description": "Flete",
			},
		)
		invoice.save()
		with self.assertRaisesRegex(ComprobanteError, "IGV"):
			invoice.submit()

	def test_credit_note_reverses_the_igv(self):
		invoice = sales_invoice(self.customer, [(1, 1000)])
		invoice.submit()
		note = make_return(invoice, pe_credit_note_reason="06")
		self.assertEqual(flt(note.grand_total, 2), -1180.00)
		note.submit()
		self.assertEqual(note.pe_voucher_number, "FC01-00000001")
		self.assertEqual(
			ledger(note), [("1212", 0.0, 1180.00), ("40111", 180.00, 0.0), ("70121", 1000.00, 0.0)]
		)
		balance = frappe.db.sql(
			"select sum(debit) - sum(credit) from `tabGL Entry` where account=%s and voucher_no in (%s, %s)",
			(pcge_account("40111"), invoice.name, note.name),
		)[0][0]
		self.assertEqual(flt(balance, 2), 0.0)

	def test_boleta_threshold_counts_the_igv(self):
		"""The S/ 700 rule looks at the total of the comprobante, IGV included."""
		below = sales_invoice(self.anonymous, [(1, 593.22)])  # 593.22 + 106.78 = 700.00
		self.assertEqual(flt(below.grand_total, 2), 700.00)
		below.submit()
		above = sales_invoice(self.anonymous, [(1, 593.23)])  # 700.01
		self.assertEqual(flt(above.grand_total, 2), 700.01)
		with self.assertRaises(ComprobanteError):
			above.submit()


class TestPurchasesWithIgv(IgvCase):
	def test_tx_uc_02_igv_credit_is_recorded_apart_from_the_cost(self):
		invoice = purchase_invoice(
			self.supplier, 500, pe_comprobante_type="01", pe_series="F001", pe_number="321"
		)
		self.assertEqual(flt(invoice.total_taxes_and_charges, 2), 90.00)
		self.assertEqual(flt(invoice.grand_total, 2), 590.00)
		invoice.submit()
		self.assertEqual(
			ledger(invoice), [("40111", 90.00, 0.0), ("4212", 0.0, 590.00), ("6011", 500.00, 0.0)]
		)

	def test_purchase_without_igv(self):
		invoice = purchase_invoice(self.supplier, 500, template=COMPRAS_EXONERADAS)
		self.assertEqual(flt(invoice.grand_total, 2), 500.00)
		invoice.submit()
		self.assertEqual(ledger(invoice), [("4212", 0.0, 500.00), ("6011", 500.00, 0.0)])

	def test_igv_payable_is_sales_igv_less_purchase_igv(self):
		"""SUNAT's own example: sells 1,000 and buys 600 -> 180 - 108 = 72 to pay."""
		sale = sales_invoice(self.customer, [(1, 1000)])
		sale.submit()
		purchase = purchase_invoice(self.supplier, 600)
		purchase.submit()
		balance = frappe.db.sql(
			"select sum(credit) - sum(debit) from `tabGL Entry` where account=%s and voucher_no in (%s, %s)",
			(pcge_account("40111"), sale.name, purchase.name),
		)[0][0]
		self.assertEqual(flt(balance, 2), 72.00)


class TestErpnextDefaultTemplate(IgvCase):
	"""ERPNext recreates its 16% "Peru Tax" template in some cases; it must stay disabled."""

	def make_peru_tax(self):
		name = f"Peru Tax - {PCGE_ABBR}"
		frappe.delete_doc_if_exists("Sales Taxes and Charges Template", name, force=True)
		doc = frappe.get_doc(
			{
				"doctype": "Sales Taxes and Charges Template",
				"title": "Peru Tax",
				"company": PCGE_COMPANY,
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": pcge_account("40111"),
						"rate": 16,
						"description": "VAT @ 16.0",
					}
				],
			}
		)
		# as ERPNext inserts it (setup_wizard/operations/taxes_setup.py)
		doc.flags.ignore_validate = doc.flags.ignore_mandatory = doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)
		return name

	def test_saving_the_company_disables_it_again(self):
		setup_igv(PCGE_COMPANY)
		name = self.make_peru_tax()
		frappe.get_doc("Company", PCGE_COMPANY).save()
		self.assertEqual(frappe.db.get_value("Sales Taxes and Charges Template", name, "disabled"), 1)

	def test_left_alone_before_the_igv_setup(self):
		frappe.db.delete("Tax Rule", {"company": PCGE_COMPANY})
		name = self.make_peru_tax()
		frappe.get_doc("Company", PCGE_COMPANY).save()
		self.assertEqual(frappe.db.get_value("Sales Taxes and Charges Template", name, "disabled"), 0)
