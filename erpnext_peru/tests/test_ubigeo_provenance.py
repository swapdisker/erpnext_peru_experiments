# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""The shipped Ubigeo file must be exactly what the official sources produce."""

import copy
import importlib.util
import os
import unittest

REPOSITORY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPOSITORY, "tools", "ubigeo", "build_ubigeo.py")


@unittest.skipUnless(os.path.exists(SCRIPT), "tools/ubigeo is only present in a source checkout")
class TestUbigeoProvenance(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		spec = importlib.util.spec_from_file_location("ubigeo_build", SCRIPT)
		cls.builder = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(cls.builder)

	def setUp(self):
		# Each test may change the declarations; give it its own copies.
		for name in ("CREATED_SINCE_2022", "RENAMED_SINCE_2022", "CORRECTIONS", "SUNAT_RENAMED"):
			setattr(self, name, getattr(self.builder, name))
			setattr(self.builder, name, copy.deepcopy(getattr(self.builder, name)))

	def tearDown(self):
		for name in ("CREATED_SINCE_2022", "RENAMED_SINCE_2022", "CORRECTIONS", "SUNAT_RENAMED"):
			setattr(self.builder, name, getattr(self, name))

	def test_shipped_csv_is_reproducible(self):
		with open(self.builder.OUTPUT, encoding="utf-8", newline="") as handle:
			self.assertEqual(handle.read(), self.builder.build())

	def test_an_undeclared_new_district_stops_the_build(self):
		del self.builder.CREATED_SINCE_2022["120307"]
		with self.assertRaisesRegex(self.builder.BuildError, "120307"):
			self.builder.build()

	def test_an_undeclared_rename_stops_the_build(self):
		del self.builder.RENAMED_SINCE_2022["100106"]
		with self.assertRaisesRegex(self.builder.BuildError, "100106"):
			self.builder.build()

	def test_a_correction_may_not_change_letters(self):
		self.builder.CORRECTIONS[("district", "150120")] = ("Magdalena Del Mar", "Magdalena del Sur")
		with self.assertRaisesRegex(self.builder.BuildError, "changes letters"):
			self.builder.build()

	def test_a_stale_correction_stops_the_build(self):
		self.builder.CORRECTIONS[("district", "150101")] = ("Lima Cercado", "Lima cercado")
		with self.assertRaisesRegex(self.builder.BuildError, "150101"):
			self.builder.build()

	def test_sunat_2014_differences_are_all_declared(self):
		del self.builder.SUNAT_RENAMED["110301"]  # Nazca -> Nasca
		with self.assertRaisesRegex(self.builder.BuildError, "110301"):
			self.builder.build()

	def test_raw_files_are_the_published_ones(self):
		self.assertEqual(self.builder.sha256_file(self.builder.INEI_2022), self.builder.INEI_2022_SHA256)
		self.builder.read_directory()  # raises if the extraction was edited

	def test_inei_codes_not_reniec(self):
		inei = self.builder.read_inei_2022()
		self.assertEqual(inei["150108"][2], "CHORRILLOS")
		self.assertEqual(inei["140108"][2], "MONSEFU")
