# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe

from erpnext_peru.setup import install
from erpnext_peru.setup.custom_fields import CUSTOM_FIELDS
from erpnext_peru.tests.utils import PeruTestCase


class TestInstall(PeruTestCase):
	def test_catalogues_are_loaded(self):
		data = install.read_catalogues()
		for key, doctype in install.CATALOGUE_DOCTYPES.items():
			for row in data[key]:
				with self.subTest(doctype=doctype, code=row["code"]):
					self.assertEqual(
						frappe.db.get_value(doctype, row["code"], "description"), row["description"]
					)

	def test_expected_codes(self):
		self.assertEqual(frappe.db.get_value("SUNAT Comprobante Type", "01", "description"), "Factura")
		self.assertEqual(
			frappe.db.get_value("SUNAT Comprobante Type", "03", "description"), "Boleta de venta"
		)
		self.assertEqual(
			frappe.db.get_value("SUNAT Comprobante Type", "07", "description"), "Nota de crédito"
		)
		self.assertEqual(frappe.db.get_value("SUNAT Comprobante Type", "08", "description"), "Nota de débito")
		self.assertEqual(
			sorted(frappe.get_all("SUNAT Comprobante Type", {"sales_issuable": 1}, pluck="name")),
			["01", "03", "07", "08"],
		)
		self.assertTrue(frappe.db.exists("SUNAT Identity Document Type", "0"))
		self.assertIn("DNI", frappe.db.get_value("SUNAT Identity Document Type", "1", "description"))
		self.assertIn("RUC", frappe.db.get_value("SUNAT Identity Document Type", "6", "description"))
		self.assertEqual(frappe.db.count("SUNAT Credit Note Reason"), 13)
		self.assertEqual(frappe.db.count("SUNAT Debit Note Reason"), 3)

	def test_custom_fields_exist_with_database_columns(self):
		for doctype, fields in CUSTOM_FIELDS.items():
			meta = frappe.get_meta(doctype)
			columns = set(frappe.db.get_table_columns(doctype))
			for field in fields:
				with self.subTest(doctype=doctype, field=field["fieldname"]):
					docfield = meta.get_field(field["fieldname"])
					self.assertIsNotNone(docfield)
					self.assertEqual(docfield.fieldtype, field["fieldtype"])
					if field["fieldtype"] not in ("Section Break", "Column Break"):
						self.assertIn(field["fieldname"], columns)

	def test_identity_fields_are_in_the_quick_entry_dialog(self):
		for doctype in ("Customer", "Supplier"):
			meta = frappe.get_meta(doctype)
			for fieldname in ("pe_identity_type", "pe_identity_number"):
				with self.subTest(doctype=doctype, fieldname=fieldname):
					self.assertEqual(meta.get_field(fieldname).allow_in_quick_entry, 1)

	def test_all_custom_fields_use_the_pe_prefix(self):
		for fields in CUSTOM_FIELDS.values():
			for field in fields:
				self.assertTrue(field["fieldname"].startswith("pe_"), field["fieldname"])

	def test_setup_is_idempotent_and_keeps_local_changes(self):
		before_fields = frappe.db.count("Custom Field", {"fieldname": ("like", "pe_%")})
		before_types = frappe.db.count("SUNAT Comprobante Type")
		frappe.db.set_value("SUNAT Credit Note Reason", "10", {"description": "Local wording", "enabled": 0})
		install.setup()
		install.setup()
		self.assertEqual(frappe.db.count("Custom Field", {"fieldname": ("like", "pe_%")}), before_fields)
		self.assertEqual(frappe.db.count("SUNAT Comprobante Type"), before_types)
		self.assertEqual(
			frappe.db.get_value("SUNAT Credit Note Reason", "10", "description"), "Local wording"
		)
		self.assertEqual(frappe.db.get_value("SUNAT Credit Note Reason", "10", "enabled"), 0)

	def test_missing_catalogue_entry_is_restored(self):
		frappe.delete_doc("SUNAT Debit Note Reason", "03", force=True)
		self.assertFalse(frappe.db.exists("SUNAT Debit Note Reason", "03"))
		install.setup()
		self.assertTrue(frappe.db.exists("SUNAT Debit Note Reason", "03"))

	def test_only_issuable_types_can_be_flagged(self):
		doc = frappe.get_doc("SUNAT Comprobante Type", "09")
		doc.sales_issuable = 1
		with self.assertRaises(frappe.ValidationError):
			doc.save()
