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
		"		total = flt(doc.base_grand_total, 2)",
		"		total = flt(doc.grand_total, 2)",
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
	(
		"overrides/sales_invoice.py",
		"	_validate_note(doc)\n\n	if not doc.pe_series:",
		"	if not doc.pe_series:",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
		'	return is_peru_company(doc.company) and doc.get("is_opening") != "Yes"',
		"	return is_peru_company(doc.company)",
		"b",
		"test_sales_invoice",
	),
	(
		"overrides/sales_invoice.py",
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
		'	if not dry_run and (report.created or report.converted_to_group):\n		rebuild_tree("Account", "parent_account")\n\n	_set_company_defaults',
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


def run(runner, module, bench, site):
	purge()
	env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
	if runner == "u":
		command = [
			os.path.join(bench, "env", "bin", "python"),
			"-m",
			"unittest",
			f"erpnext_peru.tests.{module}",
		]
		cwd = os.path.dirname(APP)
	else:
		command = [
			"bench",
			"--site",
			site,
			"run-tests",
			"--app",
			"erpnext_peru",
			"--module",
			f"erpnext_peru.tests.{module}",
		]
		cwd = bench
	result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=env)
	output = result.stdout + result.stderr
	failed = "FAILED" in output or ("Error" in output and "OK" not in output.splitlines()[-5:])
	return failed, output


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
			killed, output = run(runner, module, bench, args.site)
		finally:
			with open(path, "w", encoding="utf-8") as handle:
				handle.write(source)
		failing = re.findall(r"^(?:FAIL|ERROR): (\w+)", output, re.M)
		print(
			f"[{index:2d}] {'killed  ' if killed else 'SURVIVED'} {os.path.basename(filename):26s} "
			f"{old.strip()[:48]!r:52s} -> {len(failing)} failing: {', '.join(failing[:3])}",
			flush=True,
		)
		survived += 0 if killed else 1
	purge()
	print("SURVIVED:", survived)
	return 1 if survived else 0


if __name__ == "__main__":
	sys.exit(main())
