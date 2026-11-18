# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import collections
import unicodedata

import frappe

from erpnext_peru.overrides.common import IdentityDocumentError
from erpnext_peru.setup import install
from erpnext_peru.setup.ubigeo import load_ubigeo, read_ubigeo_file
from erpnext_peru.tests.utils import FOREIGN_COMPANY, PERU_COMPANY, PeruTestCase, make_ruc

# A code no district has: department 99 does not exist.
FAKE_CODE = "990101"


def make_ubigeo(code=FAKE_CODE, department="Prueba", province="Prueba", district="Prueba"):
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
	def setUp(self):
		super().setUp()
		load_ubigeo()  # a no-op once the site has migrated

	def messages(self):
		return " ".join(str(m) for m in frappe.get_message_log())

	def test_ubigeo_record(self):
		ubigeo = make_ubigeo(district="  Distrito   de prueba ")
		self.assertEqual(ubigeo.name, FAKE_CODE)
		self.assertEqual(ubigeo.full_name, "Distrito de prueba, Prueba, Prueba")
		self.assertEqual(ubigeo.enabled, 1)

	def test_code_must_have_six_digits(self):
		for code in ("99012", "9901222", "99012A", "99 122"):
			with self.subTest(code=code), self.assertRaises(frappe.ValidationError):
				make_ubigeo(code=code)

	def test_address_is_filled_from_the_ubigeo(self):
		address = make_address(city=None, pe_ubigeo="150113")
		self.assertEqual((address.city, address.county, address.state), ("Jesús María", "Lima", "Lima"))

	def test_address_values_typed_by_the_user_are_kept(self):
		address = make_address(city="Miraflores (Lima)", pe_ubigeo="150122")
		self.assertEqual(address.city, "Miraflores (Lima)")
		self.assertEqual(address.county, "Lima")

	def test_tx_cc_03_address_without_ubigeo_warns_but_saves(self):
		address = make_address()
		self.assertTrue(address.name)
		self.assertIn("Ubigeo", self.messages())

	def test_no_warning_before_the_ubigeo_list_is_loaded(self):
		frappe.db.delete("Ubigeo")
		make_address()
		self.assertNotIn("Ubigeo", self.messages())

	def test_no_warning_outside_peru_or_with_ubigeo(self):
		make_address(address_title="_Test PE Address US", country="United States")
		make_address(address_title="_Test PE Address OK", pe_ubigeo="150122")
		self.assertNotIn("Ubigeo", self.messages())

	def test_unknown_ubigeo_is_rejected(self):
		with self.assertRaises(frappe.LinkValidationError):
			make_address(pe_ubigeo="999999")

	def test_retired_ubigeo_warns_but_saves(self):
		frappe.db.set_value("Ubigeo", "150122", "enabled", 0)
		address = make_address(pe_ubigeo="150122")
		self.assertTrue(address.name)
		self.assertIn("no longer", self.messages())

	def test_the_address_form_offers_only_enabled_codes(self):
		from erpnext_peru.setup.custom_fields import CUSTOM_FIELDS

		definition = next(f for f in CUSTOM_FIELDS["Address"] if f["fieldname"] == "pe_ubigeo")
		field = frappe.get_meta("Address").get_field("pe_ubigeo")
		for link_filters in (definition.get("link_filters"), field.link_filters):
			self.assertEqual(frappe.parse_json(link_filters), [["Ubigeo", "enabled", "=", 1]])

	def test_the_address_form_fills_city_from_the_ubigeo(self):
		# City is mandatory in the form: the script must fill it before saving.
		import os

		[path] = frappe.get_hooks("doctype_js", app_name="erpnext_peru")["Address"]
		with open(frappe.get_app_path("erpnext_peru", path), encoding="utf-8") as handle:
			script = handle.read()
		self.assertIn("pe_ubigeo", script)
		self.assertIn("city: message.district", script)
		self.assertTrue(os.path.isfile(frappe.get_app_path("erpnext_peru", path)))

	def test_search_by_district_name_ignores_accents(self):
		from frappe.desk.search import search_link

		found = [row["value"] for row in search_link("Ubigeo", "jesus maria")]
		self.assertIn("150113", found)
		found = [row["value"] for row in search_link("Ubigeo", "Miraflores", page_length=20)]
		self.assertTrue({"150122", "040110", "100506", "151021"} <= set(found), found)


class TestUbigeoData(PeruTestCase):
	"""The shipped file. tools/ubigeo checks it against the official sources."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.rows = read_ubigeo_file()

	def test_size_and_shape(self):
		self.assertEqual(len(self.rows), 1893)
		departments, provinces = collections.defaultdict(set), collections.defaultdict(set)
		for code, (department, province, district) in self.rows.items():
			self.assertRegex(code, r"^[0-9]{6}$")
			departments[code[:2]].add(department)
			provinces[code[:4]].add(province)
			for name in (department, province, district):
				self.assertEqual(name, " ".join(name.split()))
				self.assertEqual(name, unicodedata.normalize("NFC", name))
		self.assertEqual(len(departments), 25)
		self.assertEqual(len(provinces), 196)
		self.assertTrue(all(len(names) == 1 for names in [*departments.values(), *provinces.values()]))

	def test_known_districts(self):
		expected = {
			"150101": ("Lima", "Lima", "Lima"),
			"150108": ("Lima", "Lima", "Chorrillos"),  # 140108 is RENIEC's code, not INEI's
			"070101": ("Callao", "Callao", "Callao"),
			"150113": ("Lima", "Lima", "Jesús María"),
			"150120": ("Lima", "Lima", "Magdalena del Mar"),
			"110301": ("Ica", "Nasca", "Nasca"),
			"030602": ("Apurímac", "Chincheros", "Anco-Huallo"),
			"160701": ("Loreto", "Datem del Marañón", "Barranca"),
			"160801": ("Loreto", "Putumayo", "Putumayo"),
			"160405": ("Loreto", "Mariscal Ramón Castilla", "Santa Rosa de Loreto"),  # Ley 32403
			"120307": ("Junín", "Chanchamayo", "Sangani"),  # Ley 32729
		}
		for code, names in expected.items():
			with self.subTest(code=code):
				self.assertEqual(self.rows[code], names)


class TestUbigeoLoad(PeruTestCase):
	def test_load_into_an_empty_table(self):
		frappe.db.delete("Ubigeo")
		counts = load_ubigeo()
		self.assertEqual(counts, {"inserted": 1893, "updated": 0, "disabled": 0, "enabled": 0})
		self.assertEqual(frappe.db.count("Ubigeo", {"enabled": 1}), 1893)
		row = frappe.db.get_value("Ubigeo", "150113", ["code", "district", "full_name"], as_dict=True)
		self.assertEqual(
			(row.code, row.district, row.full_name), ("150113", "Jesús María", "Jesús María, Lima, Lima")
		)
		self.assertEqual(load_ubigeo(), {"inserted": 0, "updated": 0, "disabled": 0, "enabled": 0})

	def test_the_file_wins_and_nothing_is_deleted(self):
		load_ubigeo()
		frappe.db.set_value("Ubigeo", "150113", {"district": "JESUS MARIA", "full_name": "x"})
		frappe.db.set_value("Ubigeo", "150122", "enabled", 0)
		frappe.db.delete("Ubigeo", "160405")
		make_ubigeo()  # a code INEI does not have
		make_address(pe_ubigeo=FAKE_CODE)
		counts = load_ubigeo()
		self.assertEqual(counts, {"inserted": 1, "updated": 1, "disabled": 1, "enabled": 1})
		self.assertEqual(
			frappe.db.get_value("Ubigeo", "150113", ["district", "full_name"]),
			("Jesús María", "Jesús María, Lima, Lima"),
		)
		self.assertEqual(frappe.db.get_value("Ubigeo", "150122", "enabled"), 1)
		self.assertEqual(frappe.db.get_value("Ubigeo", "160405", "district"), "Santa Rosa de Loreto")
		self.assertEqual(frappe.db.get_value("Ubigeo", FAKE_CODE, "enabled"), 0)
		self.assertTrue(frappe.db.exists("Address", {"pe_ubigeo": FAKE_CODE}))

	def test_migrate_loads_it(self):
		frappe.db.delete("Ubigeo", "120307")
		install.setup()
		self.assertEqual(frappe.db.get_value("Ubigeo", "120307", "district"), "Sangani")
