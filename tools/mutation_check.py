#!/usr/bin/env python3
# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Mutation check: every deliberate bug below must make at least one test fail.

Each entry replaces one piece of code with a wrong version, runs the tests that
should notice, and restores the file. A mutant that "SURVIVED" means the tests
would not catch that bug: add a test, do not delete the mutant.

    python tools/mutation_check.py --bench ~/frappe-bench --site test.localhost
    python tools/mutation_check.py --bench ~/frappe-bench --site test.localhost 11 12 23

Run it on a dedicated test site, with a clean working tree: the script edits
source files in place while it runs (and restores them, also on Ctrl-C).
Entries marked "u" are pure unit tests; "b" need the bench site. The whole
list takes a long time (one test-module run per mutant).

Python bytecode caching is switched off for the runs: a mutant that has the
same size as the original and is restored within the same second would
otherwise leave a stale .pyc behind and poison later runs.
"""

import argparse
import os
import re
import subprocess
import sys

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "erpnext_peru")

# (file under erpnext_peru/, original text, mutated text, runner, test module)
M = [
	# (file, old, new, runner, module)
	(
		"utils/identity.py",
		"RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)",
		"RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 3)",
		"u",
		"test_identity",
	),
	(
		"utils/identity.py",
		"	if result == 10:\n		return 0",
		"	if result == 10:\n		return 1",
		"u",
		"test_identity",
	),
	(
		"utils/identity.py",
		"	if result == 11:\n		return 1",
		"	if result == 11:\n		return 0",
		"u",
		"test_identity",
	),
	("utils/identity.py", "	if ruc[:2] not in RUC_PREFIXES:", "	if False:", "u", "test_identity"),
	("utils/identity.py", "len(dni) != DNI_LENGTH", "len(dni) > DNI_LENGTH", "u", "test_identity"),
	("utils/voucher.py", "MAX_NUMBER = 99_999_999", "MAX_NUMBER = 999_999_999", "u", "test_voucher"),
	("utils/voucher.py", "	if letter and value[0] != letter:", "	if False:", "u", "test_voucher"),
	(
		"utils/voucher.py",
		"if value < 1 or value > MAX_NUMBER",
		"if value < 0 or value > MAX_NUMBER",
		"u",
		"test_voucher",
	),
	(
		"utils/amount_in_words.py",
		"rounding=ROUND_HALF_UP",
		"rounding='ROUND_HALF_EVEN'",
		"u",
		"test_amount_in_words",
	),
	(
		"utils/amount_in_words.py",
		'	if words.endswith("veintiuno"):',
		"	if False:",
		"u",
		"test_amount_in_words",
	),
	(
		"utils/amount_in_words.py",
		'	if n == 100:\n		return "cien"',
		'	if n == 100:\n		return "ciento"',
		"u",
		"test_amount_in_words",
	),
	(
		"overrides/sales_invoice.py",
		"if total > BOLETA_ID_THRESHOLD and",
		"if total >= BOLETA_ID_THRESHOLD and",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"BOLETA_ID_THRESHOLD = 700.0",
		"BOLETA_ID_THRESHOLD = 700.01",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"		return abs(flt(doc.base_grand_total, 2))",
		"		return abs(flt(doc.grand_total, 2))",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"	doc.pe_number = 0\n	doc.pe_voucher_number = None\n\n	_snapshot",
		"	_snapshot",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"	if _is_submitted_in_database(doc):\n		return\n",
		"",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"		if identity_type not in (DOC_RUC, DOC_NON_DOMICILED) or not identity_number:",
		"		if False:",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		'	if doc.get("pe_voucher_number"):\n		frappe.throw(',
		"	if False:\n		frappe.throw(",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"		if original and original.pe_voucher_number and original.pe_comprobante_type:",
		"		if False:",
		"b",
		"test_sales_invoice",
	),
	("overrides/sales_invoice.py", "	_validate_issuer(doc)\n", "", "b", "test_sales_invoice"),
	# Ubigeo: loading on migrate, disabling, the address form
	("setup/ubigeo.py", "		elif row.enabled:", "		elif False:", "b", "test_company_address"),
	(
		"setup/ubigeo.py",
		"			if not row.enabled:",
		"			if False:",
		"b",
		"test_company_address",
	),
	(
		"setup/ubigeo.py",
		"			if tuple(row.get(f) for f in NAME_FIELDS) != names:",
		"			if False:",
		"b",
		"test_company_address",
	),
	("setup/ubigeo.py", "	if missing:", "	if False:", "b", "test_company_address"),
	("setup/install.py", "	load_ubigeo()\n", "", "b", "test_company_address"),
	# Review fixes of 17 November (v16 only)
	(
		"overrides/sales_invoice.py",
		"	_fill_pos_return_reason(doc)\n	_validate_note(doc)",
		"	_validate_note(doc)",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		'		and cint(doc.get("is_pos"))\n		and not doc.pe_credit_note_reason\n',
		'		and cint(doc.get("is_pos"))\n',
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"	return REASON_TOTAL_RETURN if sold and returned == sold else REASON_ITEM_RETURN",
		"	return REASON_ITEM_RETURN",
		"b",
		"test_sales_invoice",
	),
	("overrides/transaction_deletion.py", "	if issued:", "	if False:", "b", "test_sales_invoice"),
	(
		"hooks.py",
		'		"before_submit": "erpnext_peru.overrides.transaction_deletion.before_submit",\n',
		"",
		"b",
		"test_sales_invoice",
	),
	(
		"setup/custom_fields.py",
		'			"link_filters": MODIFIABLE_FILTER,',
		'			"link_filters": ISSUABLE_FILTER,',
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/company.py",
		"	disable_erpnext_default_templates(doc.name, doc.abbr)",
		"	pass",
		"b",
		"test_igv",
	),
	(
		"overrides/company.py",
		'	if not frappe.db.exists("Tax Rule", {"company": doc.name, "tax_category": CATEGORY_GRAVADO}):\n		return',
		"	if False:\n		return",
		"b",
		"test_igv",
	),
	(
		"hooks.py",
		'		"on_update": "erpnext_peru.overrides.company.on_update",\n',
		"",
		"b",
		"test_igv",
	),
	(
		"setup/install.py",
		"		if major != str(SUPPORTED_MAJOR_VERSION):",
		"		if False:",
		"b",
		"test_install",
	),
	(
		"hooks.py",
		'before_install = "erpnext_peru.setup.install.before_install"\n',
		"",
		"b",
		"test_install",
	),
	("hooks.py", ', "Address": "public/js/address.js"}', "}", "b", "test_company_address"),
	(
		"overrides/address.py",
		"		if row and not row.enabled:",
		"		if False:",
		"b",
		"test_company_address",
	),
	(
		"setup/custom_fields.py",
		"""			"link_filters": '[["Ubigeo", "enabled", "=", 1]]',\n""",
		"",
		"b",
		"test_company_address",
	),
	(
		"overrides/sales_invoice.py",
		"	_validate_note(doc)\n\n	if not doc.pe_series:",
		"	if not doc.pe_series:",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/common.py",
		'	return is_peru_company(doc.company) and doc.get("is_opening") != "Yes"',
		"	return is_peru_company(doc.company)",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/common.py",
		'	return is_peru_company(doc.company) and doc.get("is_opening") != "Yes"',
		'	return doc.get("is_opening") != "Yes"',
		"b",
		"test_sales_invoice",
	),
	(
		"erpnext_peru/doctype/sunat_voucher_series/sunat_voucher_series.py",
		"as_dict=True, for_update=True",
		"as_dict=True, for_update=False",
		"b",
		"test_voucher_series",
	),
	(
		"erpnext_peru/doctype/sunat_voucher_series/sunat_voucher_series.py",
		"		if self.current_number < highest_used:",
		"		if False:",
		"b",
		"test_voucher_series",
	),
	(
		"erpnext_peru/doctype/sunat_voucher_series/sunat_voucher_series.py",
		"	if duplicate:\n",
		"	if False:\n",
		"b",
		"test_voucher_series",
	),
	(
		"erpnext_peru/doctype/sunat_voucher_series/sunat_voucher_series.py",
		"where company = %s and pe_comprobante_type = %s and pe_series = %s and docstatus in (1, 2)",
		"where company = %s and pe_comprobante_type = %s and pe_series = %s and docstatus in (1)",
		"b",
		"test_voucher_series",
	),
	("overrides/party.py", "	_check_duplicate(doc)\n", "", "b", "test_party"),
	("overrides/party.py", "	doc.tax_id = number\n", "", "b", "test_party"),
	("overrides/party.py", '		"pe_identity_type": doc.pe_identity_type,\n', "", "b", "test_party"),
	("overrides/purchase_invoice.py", "	_check_duplicate(doc)\n", "", "b", "test_purchase_invoice"),
	(
		"overrides/purchase_invoice.py",
		'		"docstatus": ("<", 2),',
		'		"docstatus": ("<", 3),',
		"b",
		"test_purchase_invoice",
	),
	(
		"overrides/purchase_invoice.py",
		'		"supplier": doc.supplier,\n',
		"",
		"b",
		"test_purchase_invoice",
	),
	("overrides/company.py", "	if doc.country != PERU or not", "	if not", "b", "test_company_address"),
	(
		"overrides/address.py",
		"			if not doc.city:\n",
		"			if True:\n",
		"b",
		"test_company_address",
	),
	("utils/pcge.py", '"4011": "Tax",', '"4012": "Tax",', "u", "test_pcge_data"),
	("utils/pcge.py", '"4": ("Pasivo", "Liability"),', '"4": ("Pasivo", "Asset"),', "u", "test_pcge_data"),
	("utils/pcge.py", "is_group=code in parents", "is_group=False", "u", "test_pcge_data"),
	(
		"utils/pcge.py",
		"		if len(code) > MIN_CODE_LENGTH and code[:-1] not in known:",
		"		if False:",
		"u",
		"test_pcge_data",
	),
	(
		"utils/pcge.py",
		'	if not (value.isascii() and value.isdigit()):\n		raise PcgeError("code_not_numeric"',
		'	if False:\n		raise PcgeError("code_not_numeric"',
		"u",
		"test_pcge_data",
	),
	(
		"accounts/pcge.py",
		"		if _company_has_ledger_entries(company):",
		"		if False:",
		"b",
		"test_pcge_apply",
	),
	(
		"accounts/pcge.py",
		"		if _normalize(current.account_name) != _normalize(account.name):",
		"		if False:",
		"b",
		"test_pcge_apply",
	),
	(
		"accounts/pcge.py",
		"		if current.root_type != account.root_type:",
		"		if False:",
		"b",
		"test_pcge_apply",
	),
	(
		"accounts/pcge.py",
		"			obstacle = _why_not_a_group(company, current)",
		"			obstacle = None",
		"b",
		"test_pcge_apply",
	),
	(
		"accounts/pcge.py",
		"		obstacle = _why_not_a_group(company, parent)",
		"		obstacle = None",
		"b",
		"test_pcge_apply",
	),
	("accounts/pcge.py", "		if current.get(fieldname):", "		if False:", "b", "test_pcge_apply"),
	(
		"accounts/pcge.py",
		"		if values.get(df.fieldname) == account:",
		"		if False:",
		"b",
		"test_pcge_apply",
	),
	("accounts/pcge.py", "		if code in seen:", "		if False:", "b", "test_pcge_apply"),
	(
		"accounts/pcge.py",
		'\tif not dry_run and (report.created or report.converted_to_group):\n\t\trebuild_tree("Account")  # one argument: Frappe v16 no longer accepts the parent field\n\n\t_set_company_defaults',
		"	_set_company_defaults",
		"b",
		"test_pcge_apply",
	),
	(
		"accounts/pcge.py",
		'	return " ".join(text.replace("–", "-").split())',
		"	return text",
		"b",
		"test_pcge_apply",
	),
	("accounts/pcge.py", "	if missing_roots:", "	if False:", "b", "test_pcge_apply"),
	("accounts/igv.py", "IGV_RATE = 18.0", "IGV_RATE = 16.0", "b", "test_igv"),
	(
		"accounts/igv.py",
		'("IGV 0% - Ventas exoneradas", CATEGORY_EXONERADO, 0.0, "20", "Exonerado")',
		'("IGV 0% - Ventas exoneradas", CATEGORY_EXONERADO, 0.0, "30", "Exonerado")',
		"b",
		"test_igv",
	),
	("accounts/igv.py", '	if row.account_type != "Tax":', "	if False:", "b", "test_igv"),
	(
		"accounts/igv.py",
		'		values = {"disabled": 1}',
		'		values = {"disabled": 0}',
		"b",
		"test_pcge_apply",
	),
	(
		"accounts/igv.py",
		'			row_extra={"category": "Total", "add_deduct_tax": "Add"},',
		'			row_extra={"category": "Valuation and Total", "add_deduct_tax": "Add"},',
		"b",
		"test_pcge_apply",
	),
	("accounts/igv.py", '	if method.startswith("Banker"):', "	if False:", "b", "test_igv"),
	("overrides/sales_invoice.py", "	_validate_igv_is_stated(doc)\n", "", "b", "test_igv"),
	(
		"overrides/sales_invoice.py",
		"	if not has_igv_setup:\n		return\n",
		"",
		"b",
		"test_sales_invoice",
	),
	(
		"accounts/api.py",
		"return frappe.cache.get_value(_state_key(company), expires=True)",
		"return frappe.cache.get_value(_state_key(company))",
		"b",
		"test_pcge_job",
	),
	(
		"accounts/api.py",
		"\t\tfrappe.db.rollback(save_point=JOB_SAVEPOINT)",
		"\t\tpass",
		"b",
		"test_pcge_job",
	),
	(
		"accounts/api.py",
		'\t\tfrappe.has_permission("Company", "write", company, throw=True)',
		"\t\tpass",
		"b",
		"test_pcge_job",
	),
	(
		"accounts/api.py",
		'\tif get_job_state(company).get("status") in IN_PROGRESS:',
		"\tif False:",
		"b",
		"test_pcge_job",
	),
	("accounts/api.py", "> JOB_STALE_AFTER:", "> JOB_STALE_AFTER * 2:", "b", "test_pcge_job"),
	(
		"accounts/api.py",
		"\tapply_pcge(company, replace_existing=replace, dry_run=True)",
		"\tpass",
		"b",
		"test_pcge_job",
	),
	(
		"accounts/api.py",
		"\t\t_set_state(company, status=STATUS_FAILED, error=message)",
		"\t\t_set_state(company, status=STATUS_DONE, error=message)",
		"b",
		"test_pcge_job",
	),
	("accounts/api.py", "\t\tdeduplicate=True,", "\t\tdeduplicate=False,", "b", "test_pcge_job"),
	(
		"erpnext_peru/doctype/sunat_voucher_series/sunat_voucher_series.py",
		"_CONCURRENT_CHANGE_ERRORS = (1213, 1020)",
		"_CONCURRENT_CHANGE_ERRORS = (1213,)",
		"b",
		"test_voucher_series",
	),
	(
		"erpnext_peru/doctype/sunat_voucher_series/sunat_voucher_series.py",
		"\t\t\tif not _is_concurrent_change(error):",
		"\t\t\tif False:",
		"b",
		"test_voucher_series",
	),
	(
		"overrides/sales_invoice.py",
		"\treturn is_peru_invoice(doc) and not is_merged_pos_invoice(doc)",
		"\treturn is_peru_invoice(doc)",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"\treturn set(submitted) == pos_invoices",
		"\treturn bool(submitted)",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		'filters={"name": ("in", list(pos_invoices)), "docstatus": 1}',
		'filters={"name": ("in", list(pos_invoices))}',
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"\telif governing_type == TYPE_BOLETA:",
		"\telif comprobante_type == TYPE_BOLETA:",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		'\tif doc.get("currency") == SOLES:\n\t\treturn abs(flt(doc.grand_total, 2))',
		'\tif doc.get("currency") == SOLES:\n\t\treturn flt(doc.grand_total, 2)',
		"b",
		"test_sales_invoice",
	),
	(
		"setup/constraints.py",
		"\t_empty_strings_to_null(table, columns)\n",
		"\tpass\n",
		"b",
		"test_constraints",
	),
	("setup/constraints.py", "\tif duplicates:\n", "\tif False:\n", "b", "test_constraints"),
	(
		"accounts/pcge.py",
		"CHART_LOCK_WAIT))[0][0] != 1:",
		"CHART_LOCK_WAIT))[0][0] == 2:",
		"b",
		"test_chart_lock",
	),
	(
		"accounts/pcge.py",
		'\t\tfrappe.db.sql("SELECT RELEASE_LOCK(%s)", (name,))',
		"\t\tpass",
		"b",
		"test_chart_lock",
	),
	("accounts/pcge.py", "\t\tif not frappe.db.transaction_writes:", "\t\tif True:", "b", "test_chart_lock"),
	(
		"accounts/api.py",
		"\texcept Exception:\n\t\tfrappe.db.rollback()",
		"\texcept Exception:\n\t\tpass",
		"b",
		"test_pcge_job",
	),
	("overrides/party.py", "\t\t_clear_tax_id_copied_from_identity(doc)\n", "", "b", "test_party"),
	(
		"overrides/party.py",
		'_("Identity Document Type"), exc=IdentityDocumentError',
		'_("Identity Document Type")',
		"b",
		"test_party",
	),
	("overrides/address.py", ' and frappe.db.exists("Ubigeo", {})', "", "b", "test_company_address"),
	(
		"overrides/purchase_invoice.py",
		"	if not current or (previous and current == previous):",
		"	if not current:",
		"b",
		"test_purchase_invoice",
	),
	(
		"overrides/purchase_invoice.py",
		"		_clear(doc)\n		_sync_bill_no(doc)\n",
		"		_clear(doc)\n",
		"b",
		"test_purchase_invoice",
	),
	(
		"erpnext_peru/doctype/sunat_voucher_series/sunat_voucher_series.py",
		"		self._check_not_registered_twice()\n",
		"",
		"b",
		"test_voucher_series",
	),
	(
		"overrides/sales_invoice.py",
		"	if series and _series_left_from_previous_type(doc, series):",
		"	if False:",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		'	if normalize_series(before.get("pe_series")) != series:\n		return False\n',
		"",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"	return abs(flt(flt(doc.grand_total) * rate, 2))",
		"	return abs(flt(doc.grand_total, 2))",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		"	if _company_currency(doc.company) == SOLES:",
		"	if True:",
		"b",
		"test_sales_invoice",
	),
]


def purge():
	subprocess.run(
		[
			"find",
			os.path.dirname(APP),
			"-name",
			"__pycache__",
			"-type",
			"d",
			"-prune",
			"-exec",
			"rm",
			"-rf",
			"{}",
			"+",
		],
		check=False,
	)


# Names of failing tests. unittest prints "FAIL: test_x (...)"; Frappe v16's
# runner prints " FAIL  test_x (...)" and a summary line "✖  test_x", in colour.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_FAILING_TEST_RE = re.compile(r"^\s*(?:FAIL|ERROR):?\s+(test\w+)|✖\s+(test\w+)", re.M)


def failing_tests(output: str) -> list[str]:
	text = _ANSI_RE.sub("", output)
	names = [a or b for a, b in _FAILING_TEST_RE.findall(text)]
	if not names and re.search(r"^FAILED \(", text, re.M):
		names = ["(unnamed)"]  # the summary says so even if no name could be read
	return list(dict.fromkeys(names))


def run(runner, module, bench, site):
	"""Run the module's tests. Returns (names of the failing tests, finished, output).

	``finished`` is False when the test run itself broke (no summary line):
	that says nothing about the mutant and must not count as killing it.
	"""
	purge()
	env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
	python = os.path.join(bench, "env", "bin", "python")
	if runner == "u":
		command = [python, "-m", "unittest", f"erpnext_peru.tests.{module}"]
		cwd = os.path.dirname(APP)
	else:
		# Frappe's own entry point, as `bench` calls it: works on any bench layout.
		command = [python, "-m", "frappe.utils.bench_helper", "frappe", "--site", site, "run-tests"]
		command += ["--app", "erpnext_peru", "--module", f"erpnext_peru.tests.{module}"]
		cwd = os.path.join(bench, "sites")
	result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=env)
	output = result.stdout + result.stderr
	finished = bool(re.search(r"^Ran \d+ tests? in ", output, re.M))
	return failing_tests(output), finished, output


def main():
	parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	parser.add_argument("--bench", required=True, help="path of the bench directory")
	parser.add_argument("--site", required=True, help="test site with erpnext_peru installed")
	parser.add_argument("indices", nargs="*", type=int, help="run only these mutants")
	args = parser.parse_args()
	bench = os.path.abspath(os.path.expanduser(args.bench))

	survived = 0
	for index, (filename, old, new, runner, module) in enumerate(M):
		if args.indices and index not in args.indices:
			continue
		path = os.path.join(APP, filename)
		with open(path, encoding="utf-8") as handle:
			source = handle.read()
		if source.count(old) != 1:
			print(
				f"[{index:2d}] STALE    {filename}: the original text was found {source.count(old)} times; update this entry"
			)
			survived += 1
			continue
		with open(path, "w", encoding="utf-8") as handle:
			handle.write(source.replace(old, new))
		try:
			failing, finished, output = run(runner, module, bench, args.site)
		finally:
			with open(path, "w", encoding="utf-8") as handle:
				handle.write(source)
		if failing:
			verdict = "killed  "
		elif finished:
			verdict = "SURVIVED"
		else:
			# The tests did not run (import error, bench problem...): not a kill.
			verdict = "BROKEN  "
			print(output[-2000:])
		print(
			f"[{index:2d}] {verdict} {os.path.basename(filename):26s} "
			f"{old.strip()[:48]!r:52s} -> {len(failing)} failing: {', '.join(failing[:3])}",
			flush=True,
		)
		survived += 0 if failing else 1
	purge()
	print("SURVIVED or BROKEN:", survived)
	return 1 if survived else 0


if __name__ == "__main__":
	sys.exit(main())
