# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Pure tests of the PCGE catalogue (no database)."""

import collections
import json
import os
import tempfile
import unittest

from erpnext_peru.utils import pcge
from erpnext_peru.utils.pcge import PcgeError, load_catalogue, validate_client_code


class TestCatalogue(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.accounts = load_catalogue()
		cls.by_code = {account.code: account for account in cls.accounts}

	def test_size_of_the_catalogue(self):
		levels = collections.Counter(len(account.code) for account in self.accounts)
		# 10 element roots + the catalogue as published by the MEF
		self.assertEqual(dict(sorted(levels.items())), {1: 10, 2: 74, 3: 322, 4: 645, 5: 702, 6: 21})
		self.assertEqual(len(self.accounts), 1774)

	def test_two_digit_accounts_per_element(self):
		"""As in the "cuadro de clasificación": no cuenta 15, 53-55, 86, 87; elements 9 and 0 empty."""
		cuentas = sorted(code for code in self.by_code if len(code) == 2)
		expected = (
			["10", "11", "12", "13", "14", "16", "17", "18", "19"]
			+ [str(n) for n in range(20, 53)]
			+ ["56", "57", "58", "59"]
			+ [str(n) for n in range(60, 86)]
			+ ["88", "89"]
		)
		self.assertEqual(cuentas, expected)

	def test_tree_is_well_formed(self):
		self.assertEqual(len(self.by_code), len(self.accounts))  # no repeated codes
		position = {account.code: index for index, account in enumerate(self.accounts)}
		for account in self.accounts:
			if account.is_element_root:
				continue
			self.assertIn(account.parent_code, self.by_code, account.code)
			self.assertTrue(self.by_code[account.parent_code].is_group, account.code)
			self.assertLess(position[account.parent_code], position[account.code])  # parents first

	def test_group_flag(self):
		parents = {account.parent_code for account in self.accounts if not account.is_element_root}
		for account in self.accounts:
			expected = account.is_element_root or account.code in parents
			self.assertEqual(account.is_group, expected, account.code)
		for code in ("9", "0"):  # elements without catalogue accounts are still groups
			self.assertTrue(self.by_code[code].is_group)
		self.assertEqual(sum(1 for a in self.accounts if not a.is_group), 1218)

	def test_well_known_accounts(self):
		expected = {
			"10": "Efectivo y equivalentes de efectivo",
			"101": "Caja",
			"1041": "Cuentas corrientes operativas",
			"12": "Cuentas por cobrar comerciales – terceros",
			"1212": "Emitidas en cartera",
			"20111": "Costo",
			"33": "Propiedad, planta y equipo",
			"40": "Tributos, contraprestaciones y aportes al sistema público de pensiones y de salud por pagar",
			"40111": "IGV – Cuenta propia",
			"4212": "Emitidas",
			"50": "Capital",
			"59": "Resultados acumulados",
			"6011": "Mercaderías",
			"676": "Diferencia de cambio",
			"69121": "Terceros",
			"70": "Ventas",
			"70121": "Terceros",
			"776": "Diferencia en cambio",
			"79": "Cargas imputables a cuentas de costos y gastos",
			"89": "Determinación del resultado del ejercicio",
		}
		for code, name in expected.items():
			self.assertEqual(self.by_code[code].name, name, code)

	def test_leaf_and_group_examples(self):
		for code in ("101", "40111", "4212", "70121", "891", "683151"):
			self.assertFalse(self.by_code[code].is_group, code)
		for code in ("1", "10", "104", "4011", "701", "7012", "68315"):
			self.assertTrue(self.by_code[code].is_group, code)

	def test_names_are_clean_and_fit_erpnext(self):
		for account in self.accounts:
			self.assertEqual(account.name, account.name.strip())
			self.assertNotIn("  ", account.name)
			if len(account.code) == 2:  # headings are printed in capitals in the source
				self.assertFalse(account.name.isupper(), account.code)
			# ERPNext names an account "<number> - <name> - <company abbreviation>" (140 characters at most)
			self.assertLessEqual(len(f"{account.code} - {account.name} - ABCDE"), 140, account.code)

	def test_root_and_report_types(self):
		expected = {
			"1": "Asset",
			"2": "Asset",
			"3": "Asset",
			"4": "Liability",
			"5": "Equity",
			"6": "Expense",
			"7": "Income",
			"8": "Expense",
			"9": "Expense",
			"0": "Asset",
		}
		for account in self.accounts:
			self.assertEqual(account.root_type, expected[account.element], account.code)
			balance_sheet = account.root_type in ("Asset", "Liability", "Equity")
			self.assertEqual(account.report_type, "Balance Sheet" if balance_sheet else "Profit and Loss")

	def test_account_types(self):
		expected = {
			"101": "Cash",
			"102": "Cash",
			"103": "",
			"1031": "",
			"104": "Bank",
			"1041": "Bank",
			"1042": "Bank",
			"105": "",
			"1061": "Bank",
			"107": "",
			"12": "",
			"121": "Receivable",
			"1212": "Receivable",
			"122": "",
			"1232": "Receivable",
			"1312": "Receivable",
			"132": "",
			"1331": "Receivable",
			"14": "",
			"1411": "",
			"16": "",
			"1673": "",
			"20": "",
			"20111": "",
			"33": "",
			"33111": "",
			"39": "",
			"40": "",
			"401": "",
			"4011": "Tax",
			"40111": "Tax",
			"40117": "Tax",
			"4012": "",
			"4017": "",
			"40171": "",
			"41": "",
			"4111": "",
			"42": "",
			"421": "Payable",
			"4212": "Payable",
			"422": "",
			"423": "Payable",
			"424": "Payable",
			"4312": "Payable",
			"4321": "",
			"4331": "Payable",
			"4341": "Payable",
			"45": "",
			"60": "",
			"6011": "",
			"62": "",
			"676": "",
			"68": "",
			"69": "Cost of Goods Sold",
			"69121": "Cost of Goods Sold",
			"70": "Income Account",
			"70121": "Income Account",
			"709": "Income Account",
			"73": "",
			"776": "",
			"881": "",
			"1": "",
			"4": "",
			"7": "",
		}
		for code, account_type in expected.items():
			self.assertEqual(self.by_code[code].account_type, account_type, code)

	def test_typed_accounts_summary(self):
		counts = collections.Counter(a.account_type for a in self.accounts if a.account_type)
		self.assertEqual(
			set(counts),
			{"Cash", "Bank", "Receivable", "Payable", "Tax", "Cost of Goods Sold", "Income Account"},
		)
		self.assertEqual(counts["Tax"], 8)  # 4011 and 40111..40117
		self.assertEqual(counts["Cash"], 2)

	def test_recorded_corrections_are_reflected(self):
		with open(os.path.join(pcge.DATA_DIR, "pcge_2019_notes.json"), encoding="utf-8") as handle:
			notes = json.load(handle)
		self.assertIn("mef.gob.pe", notes["source_url"])
		code_fixes = [c for c in notes["corrections"] if "corrected_code" in c]
		name_fixes = [c for c in notes["corrections"] if "corrected_name" in c]
		self.assertEqual(len(code_fixes), 13)
		for fix in code_fixes:
			self.assertIn(fix["corrected_code"], self.by_code, fix)
		for printed_only in ("33404", "38472", "38473", "38474", "38352", "63432", "683351"):
			self.assertNotIn(printed_only, self.by_code)
		for fix in name_fixes:
			self.assertEqual(self.by_code[fix["code"]].name, fix["corrected_name"])
		# the corrected accounts sit where their neighbours say they should
		self.assertEqual(self.by_code["27243"].parent_code, "2724")
		self.assertEqual(self.by_code["30111"].name, "Costo")
		self.assertEqual(self.by_code["6881"].name, "Desvalorización de propiedad de inversión")
		self.assertEqual(
			self.by_code["6882"].name,
			"Desvalorización de activos por derecho de uso - arrendamiento financiero",
		)
		self.assertEqual(self.by_code["70111"].parent_code, "7011")
		self.assertEqual(self.by_code["70121"].parent_code, "7012")


class TestDamagedCatalogue(unittest.TestCase):
	def load(self, text):
		handle, path = tempfile.mkstemp(suffix=".csv")
		with os.fdopen(handle, "w", encoding="utf-8") as stream:
			stream.write("code,name\n" + text)
		self.addCleanup(os.remove, path)
		return load_catalogue(path)

	def test_valid_minimal_file(self):
		accounts = self.load("10,Caja y bancos\n101,Caja\n")
		self.assertEqual([a.code for a in accounts if len(a.code) > 1], ["10", "101"])

	def test_rejections(self):
		cases = {
			"10,A\n10,B\n": "duplicate_codes",
			"10,A\n1012,B\n": "orphan",
			"1A,A\n": "bad_code",
			"1,A\n": "bad_code",
			"10,\n": "empty_name",
		}
		for text, code in cases.items():
			with self.subTest(text=text):
				with self.assertRaises(PcgeError) as ctx:
					self.load(text)
				self.assertEqual(ctx.exception.code, code)


class TestClientCodes(unittest.TestCase):
	def test_valid(self):
		for code in ("10", "104101", " 4212001 ", "9411", "0111", 601101):
			self.assertEqual(validate_client_code(code), str(code).strip())

	def test_invalid(self):
		cases = {
			"": "code_missing",
			None: "code_missing",
			"  ": "code_missing",
			"X104": "code_not_numeric",
			"10.41": "code_not_numeric",
			"10-41": "code_not_numeric",
			"１０４": "code_not_numeric",
			"1": "code_too_short",
			"1" * 11: "code_too_long",
		}
		for code, error in cases.items():
			with self.subTest(code=code):
				with self.assertRaises(PcgeError) as ctx:
					validate_client_code(code)
				self.assertEqual(ctx.exception.code, error)


if __name__ == "__main__":
	unittest.main()
