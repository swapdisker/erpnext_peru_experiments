# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Pure unit tests (no database)."""

import random
import re
import unittest
from decimal import Decimal

from erpnext_peru.utils.amount_in_words import amount_in_words, number_to_words_es

EXPECTED = {
	0: "cero",
	1: "uno",
	2: "dos",
	9: "nueve",
	10: "diez",
	11: "once",
	15: "quince",
	16: "dieciséis",
	19: "diecinueve",
	20: "veinte",
	21: "veintiuno",
	22: "veintidós",
	23: "veintitrés",
	26: "veintiséis",
	29: "veintinueve",
	30: "treinta",
	31: "treinta y uno",
	45: "cuarenta y cinco",
	99: "noventa y nueve",
	100: "cien",
	101: "ciento uno",
	110: "ciento diez",
	118: "ciento dieciocho",
	121: "ciento veintiuno",
	200: "doscientos",
	500: "quinientos",
	700: "setecientos",
	900: "novecientos",
	999: "novecientos noventa y nueve",
	1000: "mil",
	1001: "mil uno",
	1021: "mil veintiuno",
	1100: "mil cien",
	1234: "mil doscientos treinta y cuatro",
	2000: "dos mil",
	10000: "diez mil",
	# apocope before "mil"
	21000: "veintiún mil",
	31000: "treinta y un mil",
	41001: "cuarenta y un mil uno",
	100000: "cien mil",
	101000: "ciento un mil",
	121000: "ciento veintiún mil",
	201021: "doscientos un mil veintiuno",
	999999: "novecientos noventa y nueve mil novecientos noventa y nueve",
	1000000: "un millón",
	1000001: "un millón uno",
	1001000: "un millón mil",
	2000000: "dos millones",
	# apocope before "millones"
	21000000: "veintiún millones",
	31000000: "treinta y un millones",
	101000000: "ciento un millones",
	100000000: "cien millones",
	1000000000: "mil millones",
	1001000000: "mil un millones",
	21021021021: "veintiún mil veintiún millones veintiún mil veintiuno",
	999999999999: (
		"novecientos noventa y nueve mil novecientos noventa y nueve millones "
		"novecientos noventa y nueve mil novecientos noventa y nueve"
	),
}


class TestNumberToWords(unittest.TestCase):
	def test_expected_values(self):
		for number, words in EXPECTED.items():
			with self.subTest(number=number):
				self.assertEqual(number_to_words_es(number), words)

	def test_bounds_and_types(self):
		for bad in (-1, 10**12):
			with self.assertRaises(ValueError):
				number_to_words_es(bad)
		for bad in (1.0, "1", None, True):
			with self.assertRaises(TypeError):
				number_to_words_es(bad)

	def test_every_number_below_a_thousand_is_well_formed(self):
		seen = set()
		for number in range(1000):
			words = number_to_words_es(number)
			self.assertRegex(words, r"^[a-záéíóúñ]+( [a-záéíóú]+)*$")
			self.assertNotIn(words, seen)  # no two numbers share a spelling
			seen.add(words)

	def test_cross_check_with_num2words(self):
		"""Compare with num2words, correcting its known apocope bug.

		num2words 0.5.x writes "veintiuno mil"/"uno millones"; everything else
		is expected to match exactly. Skipped when the library is not installed.
		"""
		try:
			from num2words import num2words
		except ImportError:  # pragma: no cover
			self.skipTest("num2words not installed")

		def reference(number: int) -> str:
			text = num2words(number, lang="es")
			text = re.sub(r"veintiuno (mil|millones)", r"veintiún \1", text)
			text = re.sub(r"uno (mil|millones)", r"un \1", text)
			return text

		for number in range(0, 100000):
			self.assertEqual(number_to_words_es(number), reference(number), number)
		rng = random.Random(20261115)
		for _ in range(50000):
			number = rng.randrange(10**12)
			self.assertEqual(number_to_words_es(number), reference(number), number)


class TestAmountInWords(unittest.TestCase):
	def test_examples(self):
		cases = {
			("118", "PEN"): "SON: CIENTO DIECIOCHO CON 00/100 SOLES",
			("1234.56", "PEN"): "SON: MIL DOSCIENTOS TREINTA Y CUATRO CON 56/100 SOLES",
			("0.05", "PEN"): "SON: CERO CON 05/100 SOLES",
			("0", "PEN"): "SON: CERO CON 00/100 SOLES",
			("1", "PEN"): "SON: UNO CON 00/100 SOLES",
			("21000.10", "PEN"): "SON: VEINTIÚN MIL CON 10/100 SOLES",
			("1000000", "USD"): "SON: UN MILLÓN CON 00/100 DÓLARES AMERICANOS",
			("16.16", "usd"): "SON: DIECISÉIS CON 16/100 DÓLARES AMERICANOS",
			("700.00", "EUR"): "SON: SETECIENTOS CON 00/100 EUROS",
			("10", "CLP"): "SON: DIEZ CON 00/100 CLP",
		}
		for (amount, currency), expected in cases.items():
			with self.subTest(amount=amount):
				self.assertEqual(amount_in_words(amount, currency), expected)

	def test_input_types(self):
		expected = "SON: CIENTO DIECIOCHO CON 00/100 SOLES"
		for amount in (118, 118.0, "118.00", Decimal("118"), Decimal("118.000")):
			self.assertEqual(amount_in_words(amount), expected)

	def test_float_artefacts(self):
		# 0.1 + 0.2 == 0.30000000000000004
		self.assertEqual(amount_in_words(0.1 + 0.2), "SON: CERO CON 30/100 SOLES")
		self.assertEqual(amount_in_words(1.15), "SON: UNO CON 15/100 SOLES")
		self.assertEqual(amount_in_words(2.675), "SON: DOS CON 68/100 SOLES")

	def test_rounding_half_up(self):
		self.assertEqual(amount_in_words("0.005"), "SON: CERO CON 01/100 SOLES")
		self.assertEqual(amount_in_words("0.004"), "SON: CERO CON 00/100 SOLES")
		self.assertEqual(amount_in_words("1.995"), "SON: DOS CON 00/100 SOLES")
		self.assertEqual(amount_in_words("99.999"), "SON: CIEN CON 00/100 SOLES")
		self.assertEqual(amount_in_words("999.994"), "SON: NOVECIENTOS NOVENTA Y NUEVE CON 99/100 SOLES")

	def test_cents_are_always_exact(self):
		for cents in range(100):
			amount = Decimal(5) + Decimal(cents) / 100
			self.assertEqual(amount_in_words(amount), f"SON: CINCO CON {cents:02d}/100 SOLES")

	def test_prefix(self):
		self.assertEqual(amount_in_words("5", prefix=""), "CINCO CON 00/100 SOLES")
		self.assertEqual(amount_in_words("5", prefix=None), "CINCO CON 00/100 SOLES")

	def test_rejects_bad_amounts(self):
		for bad in ("-0.01", -5, "abc", "", None, "NaN", "Infinity", 10**12):
			with self.subTest(bad=bad), self.assertRaises(ValueError):
				amount_in_words(bad)

	def test_negative_zero_after_rounding(self):
		self.assertEqual(amount_in_words("-0.001"), "SON: CERO CON 00/100 SOLES")


if __name__ == "__main__":
	unittest.main()
