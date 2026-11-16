# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Annexure A, module 1: chart of accounts (PCGE)."""

import frappe
from frappe.utils import today

from erpnext_peru.accounts.igv import setup_igv
from erpnext_peru.accounts.pcge import (
	COMPANY_DEFAULTS,
	PcgeApplyError,
	apply_pcge,
	import_client_accounts,
)
from erpnext_peru.tests.utils import (
	FOREIGN_COMPANY,
	PCGE_ABBR,
	PCGE_COMPANY,
	PERU_ABBR,
	PERU_COMPANY,
	PeruTestCase,
	ensure_pcge_company,
	make_customer,
	make_ruc,
	make_sales_invoice,
	make_series,
	pcge_account,
)
from erpnext_peru.utils.pcge import load_catalogue


def journal_entry(company, debit_account, credit_account, amount=100, abbr=PCGE_ABBR):
	doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": company,
			"posting_date": today(),
			"accounts": [
				{
					"account": debit_account,
					"debit_in_account_currency": amount,
					"cost_center": f"Main - {abbr}",
				},
				{
					"account": credit_account,
					"credit_in_account_currency": amount,
					"cost_center": f"Main - {abbr}",
				},
			],
		}
	)
	doc.insert()
	doc.submit()
	return doc


def account_rows(company):
	rows = frappe.get_all(
		"Account",
		filters={"company": company},
		fields=[
			"name",
			"account_name",
			"account_number",
			"parent_account",
			"is_group",
			"root_type",
			"report_type",
			"account_type",
			"account_currency",
			"lft",
			"rgt",
		],
	)
	return {row.account_number: row for row in rows}, rows


class TestPcgeChart(PeruTestCase):
	"""The fixture company was created with ERPNext's standard chart, then replaced by the PCGE."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_pcge_company()

	def test_coa_uc_01_the_chart_is_exactly_the_pcge(self):
		by_number, rows = account_rows(PCGE_COMPANY)
		catalogue = load_catalogue()
		self.assertEqual(len(rows), len(catalogue))  # nothing of the standard chart is left
		self.assertEqual(len(rows), 1774)
		for account in catalogue:
			row = by_number.get(account.code)
			with self.subTest(code=account.code):
				self.assertIsNotNone(row)
				self.assertEqual(row.account_name, account.name)
				self.assertEqual(row.name, f"{account.code} - {account.name} - {PCGE_ABBR}")
				self.assertEqual(row.is_group, 1 if account.is_group else 0)
				self.assertEqual(row.root_type, account.root_type)
				self.assertEqual(row.report_type, account.report_type)
				self.assertEqual(row.account_type or "", account.account_type)
				self.assertEqual(row.account_currency, "PEN")
				if account.is_element_root:
					self.assertFalse(row.parent_account)
				else:
					self.assertEqual(row.parent_account, by_number[account.parent_code].name)

	def test_tree_positions_are_consistent(self):
		"""Roll-up Elemento > Cuenta > Subcuenta > Divisionaria relies on the nested set."""
		by_number, rows = account_rows(PCGE_COMPANY)
		by_name = {row.name: row for row in rows}
		for row in rows:
			self.assertLess(row.lft, row.rgt, row.name)
			if row.parent_account:
				parent = by_name[row.parent_account]
				self.assertTrue(parent.lft < row.lft and row.rgt < parent.rgt, row.name)
			if not row.is_group:
				self.assertEqual(row.rgt, row.lft + 1, row.name)
		# every account below element 4 is found by a single range query, as reports do
		root = by_number["4"]
		below = frappe.db.count(
			"Account", {"company": PCGE_COMPANY, "lft": (">", root.lft), "rgt": ("<", root.rgt)}
		)
		self.assertEqual(
			below, sum(1 for a in load_catalogue() if a.code.startswith("4") and len(a.code) > 1)
		)

	def test_company_defaults(self):
		company = frappe.get_doc("Company", PCGE_COMPANY)
		for fieldname, code in COMPANY_DEFAULTS.items():
			self.assertEqual(company.get(fieldname), pcge_account(code), fieldname)
		self.assertEqual(company.default_receivable_account, f"1212 - Emitidas en cartera - {PCGE_ABBR}")
		self.assertEqual(company.default_payable_account, f"4212 - Emitidas - {PCGE_ABBR}")
		self.assertEqual(
			company.round_off_account, f"7599 - Otros ingresos de gestión - {PCGE_ABBR}"
		)  # provisional
		# decisions that belong to the accountant are not taken
		for fieldname in (
			"default_cash_account",
			"default_bank_account",
			"default_expense_account",
			"exchange_gain_loss_account",
			"default_inventory_account",
		):
			self.assertFalse(company.get(fieldname), fieldname)

	def test_coa_uc_03_applying_again_creates_nothing(self):
		before = frappe.db.count("Account", {"company": PCGE_COMPANY})
		report = apply_pcge(PCGE_COMPANY)
		self.assertEqual(report.created, [])
		self.assertEqual(report.existing, 1774)
		self.assertEqual(report.name_differences, [])
		self.assertEqual(report.conflicts, [])
		self.assertEqual(report.skipped, [])
		self.assertEqual(report.converted_to_group, [])
		self.assertEqual(report.defaults_set, {})
		self.assertEqual(frappe.db.count("Account", {"company": PCGE_COMPANY}), before)

	def test_coa_cc_03_posting_to_a_group_account_is_blocked(self):
		with self.assertRaises(frappe.ValidationError):
			journal_entry(PCGE_COMPANY, pcge_account("10"), pcge_account("5011"))
		with self.assertRaises(frappe.ValidationError):
			journal_entry(PCGE_COMPANY, pcge_account("101"), pcge_account("50"))

	def test_posting_to_ledger_accounts_works(self):
		entry = journal_entry(PCGE_COMPANY, pcge_account("101"), pcge_account("5011"), amount=2500.75)
		entries = frappe.get_all("GL Entry", {"voucher_no": entry.name}, ["account", "debit", "credit"])
		self.assertEqual(
			sorted((e.account, e.debit, e.credit) for e in entries),
			[(pcge_account("101"), 2500.75, 0.0), (pcge_account("5011"), 0.0, 2500.75)],
		)

	def test_coa_cc_02_different_name_is_kept_and_reported(self):
		account = pcge_account("101")
		frappe.db.set_value("Account", account, "account_name", "Caja chica y efectivo")
		report = apply_pcge(PCGE_COMPANY)
		self.assertEqual(
			report.name_differences,
			[{"code": "101", "company_name": "Caja chica y efectivo", "pcge_name": "Caja"}],
		)
		self.assertEqual(report.created, [])
		self.assertEqual(frappe.db.get_value("Account", account, "account_name"), "Caja chica y efectivo")

	def test_name_comparison_ignores_case_accents_and_dash_style(self):
		frappe.db.set_value("Account", pcge_account("40111"), "account_name", "IGV - CUENTA PROPIA")
		frappe.db.set_value("Account", pcge_account("2523"), "account_name", "energia")
		self.assertEqual(apply_pcge(PCGE_COMPANY).name_differences, [])

	def test_coa_cc_01_account_used_differently_is_a_conflict_and_is_not_changed(self):
		account = pcge_account("18")
		frappe.db.sql("update tabAccount set root_type='Liability' where name=%s", account)
		report = apply_pcge(PCGE_COMPANY)
		self.assertEqual([(c["code"], c["reason"]) for c in report.conflicts], [("18", "root_type")])
		self.assertEqual(frappe.db.get_value("Account", account, "root_type"), "Liability")

	def test_removed_account_is_restored(self):
		frappe.delete_doc("Account", pcge_account("1675"))
		report = apply_pcge(PCGE_COMPANY)
		self.assertEqual(report.created, ["1675"])
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("1675"), "parent_account"), pcge_account("167")
		)

	def test_dry_run_writes_nothing(self):
		frappe.delete_doc("Account", pcge_account("1675"))
		before = frappe.db.count("Account", {"company": PCGE_COMPANY})
		report = apply_pcge(PCGE_COMPANY, dry_run=True)
		self.assertTrue(report.dry_run)
		self.assertEqual(report.created, ["1675"])
		self.assertEqual(frappe.db.count("Account", {"company": PCGE_COMPANY}), before)

	def test_only_peruvian_companies(self):
		with self.assertRaises(PcgeApplyError):
			apply_pcge(FOREIGN_COMPANY)
		with self.assertRaises(PcgeApplyError):
			apply_pcge("No such company")
		with self.assertRaises(PcgeApplyError):
			apply_pcge("")


class TestPcgeOnStandardChart(PeruTestCase):
	"""A company that still has ERPNext's standard chart (as the setup wizard leaves it)."""

	def test_preview_of_both_modes_changes_nothing(self):
		before = frappe.db.count("Account", {"company": PERU_COMPANY})
		merge = apply_pcge(PERU_COMPANY, dry_run=True)
		self.assertEqual(len(merge.created), 1774)
		self.assertEqual(merge.existing, 0)
		self.assertFalse(merge.replaced_existing)
		self.assertIn("default_receivable_account", merge.defaults_kept)
		replace = apply_pcge(PERU_COMPANY, replace_existing=True, dry_run=True)
		self.assertTrue(replace.replaced_existing)
		self.assertEqual(len(replace.created), 1774)
		self.assertEqual(set(replace.defaults_set), set(COMPANY_DEFAULTS))
		self.assertEqual(frappe.db.count("Account", {"company": PERU_COMPANY}), before)
		self.assertTrue(frappe.db.exists("Account", f"Debtors - {PERU_ABBR}"))

	def test_replacing_is_refused_once_there_are_ledger_entries(self):
		customer = make_customer("_Test PE PCGE Customer", "6", make_ruc(80000001)).name
		make_series("01", "F001")
		make_sales_invoice(customer).submit()
		before = frappe.db.count("Account", {"company": PERU_COMPANY})
		for dry_run in (True, False):
			with self.assertRaises(PcgeApplyError):
				apply_pcge(PERU_COMPANY, replace_existing=True, dry_run=dry_run)
		self.assertEqual(frappe.db.count("Account", {"company": PERU_COMPANY}), before)
		self.assertTrue(frappe.db.exists("Account", f"Debtors - {PERU_ABBR}"))

	def test_adding_the_pcge_keeps_the_existing_chart_and_defaults(self):
		before_names = set(frappe.get_all("Account", {"company": PERU_COMPANY}, pluck="name"))
		defaults_before = frappe.db.get_value(
			"Company",
			PERU_COMPANY,
			["default_receivable_account", "default_income_account", "round_off_account"],
		)
		report = apply_pcge(PERU_COMPANY)
		after_names = set(frappe.get_all("Account", {"company": PERU_COMPANY}, pluck="name"))
		self.assertTrue(before_names <= after_names)  # nothing deleted or renamed
		self.assertEqual(len(after_names - before_names), 1774)
		self.assertEqual(len(report.created), 1774)
		self.assertEqual(report.conflicts, [])
		self.assertEqual(
			frappe.db.get_value(
				"Company",
				PERU_COMPANY,
				["default_receivable_account", "default_income_account", "round_off_account"],
			),
			defaults_before,
		)
		# the new accounts are positioned in the tree that reports use for roll-ups
		parent = frappe.db.get_value("Account", pcge_account("4011", PERU_COMPANY), ["lft", "rgt"])
		child = frappe.db.get_value("Account", pcge_account("40111", PERU_COMPANY), ["lft", "rgt"])
		self.assertTrue(parent[0] < child[0] < child[1] < parent[1])
		self.assertEqual(child[1], child[0] + 1)
		self.assertEqual(report.defaults_set, {})  # every default was already set: all kept
		self.assertEqual(set(report.defaults_kept), set(COMPANY_DEFAULTS))
		self.assertEqual(apply_pcge(PERU_COMPANY).created, [])  # CoA-UC-03 on this path too

		# ERPNext's own 16% template is taken out of use by the IGV setup
		old_template = f"Peru Tax - {PERU_ABBR}"
		self.assertEqual(frappe.db.get_value("Sales Taxes and Charges Template", old_template, "disabled"), 0)
		igv_report = setup_igv(PERU_COMPANY)
		self.assertEqual(
			sorted(igv_report.disabled),
			sorted(
				f"{doctype}: {old_template}"
				for doctype in (
					"Sales Taxes and Charges Template",
					"Purchase Taxes and Charges Template",
					"Item Tax Template",
				)
			),
		)
		for doctype in ("Sales Taxes and Charges Template", "Purchase Taxes and Charges Template"):
			self.assertEqual(frappe.db.get_value(doctype, old_template, ["disabled", "is_default"]), (1, 0))
		self.assertEqual(
			frappe.db.get_value(
				"Sales Taxes and Charges Template", {"company": PERU_COMPANY, "is_default": 1}
			),
			f"IGV 18% - Ventas gravadas - {PERU_ABBR}",
		)
		# the templates just created for this company point at its own account 40111
		purchase = frappe.get_doc(
			"Purchase Taxes and Charges Template", f"IGV 18% - Compras gravadas - {PERU_ABBR}"
		)
		row = purchase.taxes[0]
		self.assertEqual(
			(row.account_head, row.rate, row.charge_type, row.category, row.add_deduct_tax),
			(pcge_account("40111", PERU_COMPANY), 18.0, "On Net Total", "Total", "Add"),
		)
		sales = frappe.get_doc("Sales Taxes and Charges Template", f"IGV 0% - Exportación - {PERU_ABBR}")
		self.assertEqual(
			(sales.taxes[0].rate, sales.pe_igv_affectation_type, sales.tax_category),
			(0.0, "40", "IGV - Exportación"),
		)

	def test_merge_with_accounts_the_company_already_numbered(self):
		"""Nothing of the company's is overwritten; what cannot be reconciled is reported."""
		root = frappe.get_doc(
			{
				"doctype": "Account",
				"company": PERU_COMPANY,
				"account_name": "Activo de la empresa",
				"account_number": "1",
				"is_group": 1,
				"root_type": "Asset",
				"report_type": "Balance Sheet",
			}
		)
		root.flags.ignore_mandatory = True
		root.insert()

		def add(number, name, parent, is_group=0):
			return frappe.get_doc(
				{
					"doctype": "Account",
					"company": PERU_COMPANY,
					"account_name": name,
					"account_number": number,
					"parent_account": parent,
					"is_group": is_group,
				}
			).insert()

		cuenta_10 = add("10", "Caja y bancos", root.name, is_group=1)
		bancos = add("104", "Bancos", cuenta_10.name)  # the PCGE divides 104 into 1041 and 1042
		clientes = add("12", "Clientes", root.name)  # a ledger without entries
		journal_entry(PERU_COMPANY, bancos.name, f"Cash - {PERU_ABBR}", amount=50, abbr=PERU_ABBR)

		report = apply_pcge(PERU_COMPANY)

		self.assertEqual(report.existing, 4)
		self.assertEqual(
			{d["code"]: d["company_name"] for d in report.name_differences},
			{"1": "Activo de la empresa", "10": "Caja y bancos", "104": "Bancos", "12": "Clientes"},
		)
		self.assertEqual(
			[(c["code"], c["reason"]) for c in report.conflicts], [("104", "ledger_with_entries")]
		)
		self.assertEqual([s["code"] for s in report.skipped], ["1041", "1042"])
		self.assertEqual(report.converted_to_group, ["12"])
		self.assertEqual(len(report.created), 1774 - 4 - 2)

		# the company's accounts are untouched...
		self.assertEqual(
			frappe.db.get_value("Account", bancos.name, ["account_name", "is_group"]), ("Bancos", 0)
		)
		self.assertEqual(frappe.db.get_value("Account", cuenta_10.name, "account_name"), "Caja y bancos")
		self.assertFalse(frappe.db.exists("Account", {"company": PERU_COMPANY, "account_number": "1041"}))
		# ...its empty ledger became the group the PCGE needs, with the PCGE accounts under it
		self.assertEqual(
			frappe.db.get_value("Account", clientes.name, ["account_name", "is_group"]), ("Clientes", 1)
		)
		self.assertEqual(pcge_parent("121"), clientes.name)
		self.assertEqual(pcge_parent("101"), cuenta_10.name)
		self.assertEqual(pcge_parent("1212"), pcge_account("121", PERU_COMPANY))
		# the ledger balance is still there
		self.assertEqual(
			frappe.db.sql("select sum(debit) - sum(credit) from `tabGL Entry` where account=%s", bancos.name)[
				0
			][0],
			50,
		)
		# a second run reports the same situation and creates nothing
		again = apply_pcge(PERU_COMPANY)
		self.assertEqual(again.created, [])
		self.assertEqual(
			[(c["code"], c["reason"]) for c in again.conflicts], [("104", "ledger_with_entries")]
		)
		self.assertEqual([s["code"] for s in again.skipped], ["1041", "1042"])


def pcge_parent(code, company=PERU_COMPANY):
	return frappe.db.get_value("Account", {"company": company, "account_number": code}, "parent_account")


class TestClientAccounts(PeruTestCase):
	"""CoA-UC-02 and CoA-CC-04: the company's own sub-accounts go under the PCGE."""

	ROWS = [
		{"code": "104101", "name": "BCP Soles Cta. Cte. 193-1234567-0-12"},
		{"code": "104102", "name": "  BBVA   Soles  "},
		{"code": "1041", "name": "Cuentas corrientes operativas"},  # same as the PCGE
		{"code": "1212", "name": "Facturas por cobrar emitidas"},  # other name than the PCGE
		{"code": "94", "name": "Gastos de administración"},
		{"code": "941", "name": "Gastos de personal"},
		{"code": "9411", "name": "Sueldos administración"},
		{"code": "424001", "name": "Honorarios por pagar MN"},
		{"code": "X104", "name": "Código con letra"},
		{"code": "", "name": "Sin código"},
		{"code": "1043", "name": ""},
		{"code": "104101", "name": "Repetida"},
		{"code": "1", "name": "Demasiado corta"},
	]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_pcge_company()

	def test_coa_uc_02_import(self):
		before = frappe.db.count("Account", {"company": PCGE_COMPANY})
		preview = import_client_accounts(PCGE_COMPANY, self.ROWS, dry_run=True)
		self.assertEqual(frappe.db.count("Account", {"company": PCGE_COMPANY}), before)

		report = import_client_accounts(PCGE_COMPANY, self.ROWS)
		for key in (
			"created",
			"unchanged",
			"name_differences",
			"rejected",
			"converted_to_group",
			"conflicts",
			"renamed",
		):
			self.assertEqual(preview[key], report[key], key)  # the preview tells the truth

		self.assertEqual(report.created, ["104101", "104102", "424001", "94", "941", "9411"])
		self.assertEqual(report.unchanged, 1)
		self.assertEqual(report.converted_to_group, ["1041", "424"])
		self.assertEqual(
			report.name_differences,
			[
				{
					"line": 4,
					"code": "1212",
					"company_name": "Facturas por cobrar emitidas",
					"existing_name": "Emitidas en cartera",
				}
			],
		)
		self.assertEqual(report.renamed, [])
		self.assertEqual(
			[(r["line"], r["reason"]) for r in report.rejected],
			[
				(9, "code_not_numeric"),
				(10, "code_missing"),
				(11, "name_missing"),
				(12, "repeated_in_file"),
				(13, "code_too_short"),
			],
		)
		self.assertEqual(frappe.db.count("Account", {"company": PCGE_COMPANY}), before + 6)

		bcp = frappe.get_doc("Account", pcge_account("104101"))
		self.assertEqual(bcp.parent_account, pcge_account("1041"))
		self.assertEqual((bcp.is_group, bcp.root_type, bcp.account_type), (0, "Asset", "Bank"))
		self.assertEqual(frappe.db.get_value("Account", pcge_account("104102"), "account_name"), "BBVA Soles")
		# 1041 became a group and is still a bank account
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("1041"), ["is_group", "account_type"]), (1, "Bank")
		)
		fees = frappe.get_doc("Account", pcge_account("424001"))
		self.assertEqual((fees.parent_account, fees.account_type), (pcge_account("424"), "Payable"))
		# element 9 has no catalogue accounts: the company's hang from the element
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("94"), ["parent_account", "is_group", "root_type"]),
			(pcge_account("9"), 1, "Expense"),
		)
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("9411"), ["parent_account", "is_group"]),
			(pcge_account("941"), 0),
		)
		# the PCGE name was not overwritten
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("1212"), "account_name"), "Emitidas en cartera"
		)

		again = import_client_accounts(PCGE_COMPANY, self.ROWS)
		self.assertEqual(again.created, [])
		self.assertEqual(again.unchanged, 7)

	def test_coa_cc_04_invalid_code_is_rejected_and_the_rest_continues(self):
		rows = [
			{"code": "A0411", "name": "Empieza con una letra"},
			{"code": "104-105", "name": "Con guion"},
			{"code": "104105", "name": "Scotiabank Soles"},
		]
		report = import_client_accounts(PCGE_COMPANY, rows)
		self.assertEqual(
			[(r["line"], r["code"], r["reason"]) for r in report.rejected],
			[(1, "A0411", "code_not_numeric"), (2, "104-105", "code_not_numeric")],
		)
		self.assertEqual(report.created, ["104105"])
		self.assertTrue(pcge_account("104105"))
		self.assertEqual(frappe.db.count("Account", {"company": PCGE_COMPANY, "account_number": "A0411"}), 0)

	def test_company_names_can_be_preferred(self):
		report = import_client_accounts(
			PCGE_COMPANY, [{"code": "1212", "name": "Facturas por cobrar emitidas"}], prefer_client_names=True
		)
		self.assertEqual(report.renamed, ["1212"])
		self.assertEqual(len(report.name_differences), 1)  # still reported
		account = pcge_account("1212")
		self.assertEqual(account, f"1212 - Facturas por cobrar emitidas - {PCGE_ABBR}")
		self.assertEqual(frappe.db.get_value("Company", PCGE_COMPANY, "default_receivable_account"), account)

	def test_sub_account_under_a_ledger_with_entries_is_a_conflict(self):
		journal_entry(PCGE_COMPANY, pcge_account("1042"), pcge_account("5011"))
		report = import_client_accounts(
			PCGE_COMPANY,
			[{"code": "104201", "name": "Detracciones BN"}, {"code": "104103", "name": "Interbank"}],
		)
		self.assertEqual(
			[(c["code"], c["reason"]) for c in report.conflicts], [("104201", "ledger_with_entries")]
		)
		self.assertEqual(report.created, ["104103"])  # the rest continues
		self.assertFalse(pcge_account("104201"))
		self.assertEqual(frappe.db.get_value("Account", pcge_account("1042"), "is_group"), 0)

	def test_sub_account_under_a_company_default_is_a_conflict(self):
		"""ERPNext does not let the default receivable account become a group."""
		rows = [
			{"code": "121201", "name": "Facturas por cobrar MN"},
			{"code": "121301", "name": "En cobranza MN"},
		]
		for dry_run in (True, False):
			report = import_client_accounts(PCGE_COMPANY, rows, dry_run=dry_run)
			with self.subTest(dry_run=dry_run):
				self.assertEqual(
					[(c["code"], c["reason"]) for c in report.conflicts], [("121201", "company_default")]
				)
				self.assertIn("1212", report.conflicts[0]["detail"])
				self.assertEqual(report.created, ["121301"])  # the rest continues
				self.assertEqual(report.converted_to_group, ["1213"])
		self.assertFalse(pcge_account("121201"))
		self.assertEqual(frappe.db.get_value("Account", pcge_account("1212"), "is_group"), 0)

		# once the default points elsewhere, the same file goes through
		frappe.db.set_value("Company", PCGE_COMPANY, "default_receivable_account", pcge_account("1214"))
		report = import_client_accounts(PCGE_COMPANY, rows)
		self.assertEqual(report.conflicts, [])
		self.assertEqual(report.created, ["121201"])
		self.assertEqual(report.unchanged, 1)
		self.assertEqual(report.converted_to_group, ["1212"])
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("121201"), ["parent_account", "account_type"]),
			(pcge_account("1212"), "Receivable"),
		)

	def test_deeper_codes_hang_from_the_nearest_existing_account(self):
		report = import_client_accounts(
			PCGE_COMPANY,
			[{"code": "63110001", "name": "Fletes Lima"}, {"code": "60110001", "name": "Compras filtros"}],
		)
		self.assertEqual(report.created, ["60110001", "63110001"])
		# 63110 does not exist: the account hangs from 6311, which already is a group
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("63110001"), "parent_account"), pcge_account("6311")
		)
		# 6011 was a ledger without entries: it becomes the group
		self.assertEqual(report.converted_to_group, ["6011"])
		self.assertEqual(
			frappe.db.get_value("Account", pcge_account("60110001"), "parent_account"), pcge_account("6011")
		)

	def test_requires_the_pcge(self):
		with self.assertRaises(PcgeApplyError):
			import_client_accounts(PERU_COMPANY, [{"code": "104101", "name": "BCP"}])
		with self.assertRaises(PcgeApplyError):
			import_client_accounts(FOREIGN_COMPANY, [{"code": "104101", "name": "BCP"}])
