# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Every message and label of the app has a Spanish translation (pure test, no database)."""

import ast
import csv
import glob
import json
import os
import re
import unittest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Identical in Spanish, or already translated by Frappe / ERPNext themselves.
NOT_TRANSLATED_HERE = {
	"Ubigeo",
	"Comprobante de pago (SUNAT)",
	"Code",
	"Description",
	"Enabled",
	"Company",
	"Series",
	"Number",
	"Full Name",
	"Setup",
	"Documents",
}


def source_strings() -> set[str]:
	strings: set[str] = set()
	for path in glob.glob(os.path.join(APP_DIR, "**", "*.py"), recursive=True):
		if os.sep + "tests" + os.sep in path:
			continue
		with open(path, encoding="utf-8") as handle:
			tree = ast.parse(handle.read())
		is_custom_fields = path.endswith("custom_fields.py")
		for node in ast.walk(tree):
			if (
				isinstance(node, ast.Call)
				and isinstance(node.func, ast.Name)
				and node.func.id == "_"
				and node.args
				and isinstance(node.args[0], ast.Constant)
			):
				strings.add(node.args[0].value)
			if is_custom_fields and isinstance(node, ast.Dict):
				for key, value in zip(node.keys, node.values, strict=True):
					if (
						isinstance(key, ast.Constant)
						and key.value in ("label", "description")
						and isinstance(value, ast.Constant)
						and value.value  # "" clears an obsolete description
					):
						strings.add(value.value)
	# __("...") calls in the form scripts
	for path in glob.glob(os.path.join(APP_DIR, "public", "js", "*.js")):
		with open(path, encoding="utf-8") as handle:
			strings.update(re.findall(r'__\(\s*"((?:[^"\\]|\\.)*)"', handle.read()))
	for path in glob.glob(os.path.join(APP_DIR, "erpnext_peru", "doctype", "*", "*.json")):
		with open(path, encoding="utf-8") as handle:
			doctype = json.load(handle)
		strings.add(doctype["name"])
		for field in doctype["fields"]:
			for key in ("label", "description"):
				if field.get(key):
					strings.add(field[key])
	# card titles of the workspace that are the app's own wording
	for path in glob.glob(os.path.join(APP_DIR, "erpnext_peru", "workspace", "*", "*.json")):
		with open(path, encoding="utf-8") as handle:
			workspace = json.load(handle)
		strings.add(workspace["label"])
		strings.update(row["label"] for row in workspace["links"] if row["type"] == "Card Break")
	return strings


def translations() -> dict[str, str]:
	with open(os.path.join(APP_DIR, "translations", "es.csv"), encoding="utf-8", newline="") as handle:
		rows = list(csv.reader(handle))
	return {row[0]: row[1] for row in rows}


class TestSpanishTranslations(unittest.TestCase):
	def test_every_string_is_translated(self):
		missing = sorted(source_strings() - set(translations()) - NOT_TRANSLATED_HERE)
		self.assertEqual(missing, [])

	def test_no_stale_rows(self):
		stale = sorted(set(translations()) - source_strings())
		self.assertEqual(stale, [])

	def test_rows_are_well_formed(self):
		with open(os.path.join(APP_DIR, "translations", "es.csv"), encoding="utf-8", newline="") as handle:
			rows = list(csv.reader(handle))
		self.assertEqual(len(rows), len({row[0] for row in rows}))  # no repeated source
		for row in rows:
			self.assertEqual(len(row), 3, row)
			self.assertTrue(row[1].strip(), row)

	def test_placeholders_are_preserved(self):
		for source, translated in translations().items():
			with self.subTest(source=source):
				self.assertEqual(
					sorted(re.findall(r"\{\d+\}", source)), sorted(re.findall(r"\{\d+\}", translated))
				)


if __name__ == "__main__":
	unittest.main()
