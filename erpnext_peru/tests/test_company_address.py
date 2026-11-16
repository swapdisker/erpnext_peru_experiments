# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import os
import tempfile

import frappe

from erpnext_peru.overrides.common import IdentityDocumentError
from erpnext_peru.setup.ubigeo import import_csv
from erpnext_peru.tests.utils import FOREIGN_COMPANY, PERU_COMPANY, PeruTestCase, make_ruc


def make_ubigeo(code="150122", department="Lima", province="Lima", district="Miraflores"):
	return frappe.get_doc(
		{
			"doctype": "Ubigeo",
			"code": code,
			"department": department,
			"province": province,
			"district": district,
		}
	).insert()


def make_address(**kwargs):
	values = {
		"doctype": "Address",
		"address_title": "_Test PE Address",
		"address_type": "Billing",
		"address_line1": "Av. Ejemplo 123",
		"city": "Lima",
		"country": "Peru",
	}
	values.update(kwargs)
	return frappe.get_doc(values).insert()


class TestCompany(PeruTestCase):
	def test_peruvian_company_ruc_is_validated(self):
		company = frappe.get_doc("Company", PERU_COMPANY)
		company.tax_id = "20123456780"
		with self.assertRaises(IdentityDocumentError):
			company.save()
		company.reload()
		company.tax_id = f" {make_ruc(60000002)} "
		company.save()
		self.assertEqual(company.tax_id, make_ruc(60000002))

	def test_peruvian_company_without_ruc_can_be_saved(self):
		# the setup wizard creates the company before the RUC is known
		company = frappe.get_doc("Company", PERU_COMPANY)
		company.tax_id = None
		company.save()

	def test_other_countries_are_untouched(self):
		company = frappe.get_doc("Company", FOREIGN_COMPANY)
		company.tax_id = "12-3456789"
		company.save()
		self.assertEqual(company.tax_id, "12-3456789")


class TestUbigeo(PeruTestCase):
	def test_ubigeo_record(self):
		ubigeo = make_ubigeo(district="  Miraflores ")
		self.assertEqual(ubigeo.name, "150122")
		self.assertEqual(ubigeo.full_name, "Miraflores, Lima, Lima")

	def test_code_must_have_six_digits(self):
		for code in ("15012", "1501222", "15012A", "15 122"):
			with self.subTest(code=code), self.assertRaises(frappe.ValidationError):
				make_ubigeo(code=code)

	def test_address_is_filled_from_the_ubigeo(self):
		make_ubigeo()
		address = make_address(city=None, pe_ubigeo="150122")
		self.assertEqual((address.city, address.county, address.state), ("Miraflores", "Lima", "Lima"))

	def test_address_values_typed_by_the_user_are_kept(self):
		make_ubigeo()
		address = make_address(city="Miraflores (Lima)", pe_ubigeo="150122")
		self.assertEqual(address.city, "Miraflores (Lima)")
		self.assertEqual(address.county, "Lima")

	def test_tx_cc_03_address_without_ubigeo_warns_but_saves(self):
		frappe.clear_messages()
		address = make_address()
		self.assertTrue(address.name)
		messages = " ".join(str(m) for m in frappe.get_message_log())
		self.assertIn("Ubigeo", messages)

	def test_no_warning_outside_peru_or_with_ubigeo(self):
		make_ubigeo()
		frappe.clear_messages()
		make_address(address_title="_Test PE Address US", country="United States")
		make_address(address_title="_Test PE Address OK", pe_ubigeo="150122")
		messages = " ".join(str(m) for m in frappe.get_message_log())
		self.assertNotIn("Ubigeo", messages)

	def test_unknown_ubigeo_is_rejected(self):
		with self.assertRaises(frappe.LinkValidationError):
			make_address(pe_ubigeo="999999")


class TestUbigeoImport(PeruTestCase):
	def write(self, text, encoding="utf-8"):
		handle, path = tempfile.mkstemp(suffix=".csv")
		with os.fdopen(handle, "w", encoding=encoding, newline="") as stream:
			stream.write(text)
		self.addCleanup(os.remove, path)
		return path

	def test_import(self):
		# Illustrative rows for the importer only; this is not an authoritative district list.
		path = self.write(
			"code,department,province,district\n"
			"150101,Lima,Lima,Lima\n"
			"150122,Lima,Lima,Miraflores\n"
			"990101,Áncash,Ñaña,Jesús María\n"
			'990102,"Departamento, con coma",Provincia,Distrito\n'
			"000001,  Con   espacios ,Provincia,Distrito\n"
		)
		counts = import_csv(path)
		self.assertEqual(counts, {"inserted": 5, "updated": 0, "unchanged": 0})
		self.assertEqual(frappe.db.get_value("Ubigeo", "990101", "department"), "Áncash")
		self.assertEqual(frappe.db.get_value("Ubigeo", "990101", "province"), "Ñaña")
		self.assertEqual(frappe.db.get_value("Ubigeo", "990101", "full_name"), "Jesús María, Ñaña, Áncash")
		self.assertEqual(frappe.db.get_value("Ubigeo", "990102", "department"), "Departamento, con coma")
		self.assertEqual(
			frappe.db.get_value("Ubigeo", "000001", "department"), "Con espacios"
		)  # leading zeros kept
		# running it again changes nothing
		self.assertEqual(import_csv(path), {"inserted": 0, "updated": 0, "unchanged": 5})

	def test_update_only_on_request(self):
		first = self.write("code,department,province,district\n150122,Lima,Lima,Miraflores\n")
		second = self.write("code,department,province,district\n150122,Lima,Lima,MIRAFLORES\n")
		import_csv(first)
		self.assertEqual(import_csv(second), {"inserted": 0, "updated": 0, "unchanged": 1})
		self.assertEqual(frappe.db.get_value("Ubigeo", "150122", "district"), "Miraflores")
		self.assertEqual(import_csv(second, update=True), {"inserted": 0, "updated": 1, "unchanged": 0})
		self.assertEqual(frappe.db.get_value("Ubigeo", "150122", "district"), "MIRAFLORES")

	def test_file_with_errors_writes_nothing(self):
		path = self.write(
			"code,department,province,district\n"
			"150122,Lima,Lima,Miraflores\n"
			"15012,Lima,Lima,Short code\n"
			"150122,Lima,Lima,Repeated\n"
			"150123,Lima,,No province\n"
		)
		with self.assertRaises(frappe.ValidationError) as ctx:
			import_csv(path)
		message = str(ctx.exception)
		self.assertIn("Line 3", message)
		self.assertIn("Line 4", message)
		self.assertIn("Line 5", message)
		self.assertEqual(frappe.db.count("Ubigeo"), 0)

	def test_missing_columns(self):
		path = self.write("codigo,departamento\n150122,Lima\n")
		with self.assertRaises(frappe.ValidationError):
			import_csv(path)

	def test_byte_order_mark_is_accepted(self):
		path = self.write(
			"code,department,province,district\n150122,Lima,Lima,Miraflores\n", encoding="utf-8-sig"
		)
		self.assertEqual(import_csv(path)["inserted"], 1)
