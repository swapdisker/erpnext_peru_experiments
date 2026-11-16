# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""The shipped PCGE data must be exactly what the transcription of the MEF document produces."""

import importlib.util
import os
import unittest

REPOSITORY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPOSITORY, "tools", "pcge", "build_catalogue.py")


@unittest.skipUnless(os.path.exists(SCRIPT), "tools/pcge is only present in a source checkout")
class TestPcgeProvenance(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		spec = importlib.util.spec_from_file_location("pcge_build_catalogue", SCRIPT)
		cls.builder = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(cls.builder)

	def test_shipped_csv_is_reproducible(self):
		rows, _corrections = self.builder.build()
		with open(self.builder.CSV_PATH, encoding="utf-8", newline="") as handle:
			self.assertEqual(handle.read(), self.builder.render_csv(rows))

	def test_recorded_corrections_are_the_ones_applied(self):
		import json

		_rows, corrections = self.builder.build()
		with open(self.builder.NOTES_PATH, encoding="utf-8") as handle:
			self.assertEqual(json.load(handle)["corrections"], corrections)

	def test_raw_transcription_still_contains_the_misprints(self):
		"""The raw files are the document as printed: corrections live only in the script."""
		raw_codes = [row[0] for row in self.builder.read_raw()]
		for printed, _name, _occurrence, _fixed, _reason in self.builder.CODE_FIXES:
			self.assertIn(printed, raw_codes)
		self.assertEqual(len(raw_codes), 1764)
		self.assertEqual(raw_codes.count("27233"), 2)
		self.assertEqual(raw_codes.count("6882"), 2)

	def test_script_check_mode_passes(self):
		self.assertEqual(self.builder.main([]), 0)


if __name__ == "__main__":
	unittest.main()
