# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Pure unit tests (no database). Run with ``python -m unittest`` or bench."""

import random
import unittest

from erpnext_peru.utils.identity import (
	IdentityError,
	is_valid_ruc,
	normalize_identity_number,
	ruc_check_digit,
	validate_dni,
	validate_identity_number,
	validate_ruc,
)

# RUCs of public institutions / listed companies, used only as algorithm vectors.
KNOWN_VALID_RUCS = (
	"20131312955",  # SUNAT
	"20100047218",
	"20100017491",
	"20100053455",
)

# Independent statement of the rule: remainder of the weighted sum -> check digit.
REMAINDER_TO_DIGIT = {0: 1, 1: 0, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 3, 9: 2, 10: 1}


def reference_check_digit(first_ten: str) -> int:
	weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
	total = 0
	for position in range(10):
		total += int(first_ten[position]) * weights[position]
	return REMAINDER_TO_DIGIT[total % 11]


class TestRuc(unittest.TestCase):
	def test_known_rucs_are_valid(self):
		for ruc in KNOWN_VALID_RUCS:
			with self.subTest(ruc=ruc):
				self.assertTrue(is_valid_ruc(ruc))
				self.assertEqual(validate_ruc(ruc), ruc)

	def test_hand_computed_example(self):
		# 2 0 1 3 1 3 1 2 9 5 x 5 4 3 2 7 6 5 4 3 2
		# = 10+0+3+6+7+18+5+8+27+10 = 94; 94 % 11 = 6; 11 - 6 = 5
		self.assertEqual(ruc_check_digit("2013131295"), 5)

	def test_every_wrong_last_digit_is_rejected(self):
		# MD-CC-01: RUC with wrong check digit is blocked.
		for ruc in KNOWN_VALID_RUCS:
			for digit in "0123456789":
				candidate = ruc[:10] + digit
				with self.subTest(candidate=candidate):
					self.assertEqual(is_valid_ruc(candidate), digit == ruc[10])

	def test_single_digit_typos_are_detected(self):
		# Modulus 11 with these weights detects any single-digit substitution
		# in the first ten positions... except when the result collapses onto
		# the shared digits (remainders 0 and 10 both give 1). Verify against
		# the independent reference rather than assuming.
		for ruc in KNOWN_VALID_RUCS:
			for position in range(2, 10):
				for digit in "0123456789":
					if digit == ruc[position]:
						continue
					candidate = ruc[:position] + digit + ruc[position + 1 :]
					expected = reference_check_digit(candidate[:10]) == int(candidate[10])
					with self.subTest(candidate=candidate):
						self.assertEqual(is_valid_ruc(candidate), expected)

	def test_matches_reference_on_random_numbers(self):
		rng = random.Random(20261115)
		for _ in range(20000):
			first_ten = rng.choice(["10", "15", "16", "17", "20"]) + f"{rng.randrange(10**8):08d}"
			self.assertEqual(ruc_check_digit(first_ten), reference_check_digit(first_ten), first_ten)

	def test_special_results_ten_and_eleven(self):
		# 11 - remainder == 10 -> 0 ; == 11 -> 1
		seen = set()
		for body in range(100000):
			first_ten = "20" + f"{body:08d}"
			weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
			remainder = sum(int(d) * w for d, w in zip(first_ten, weights, strict=True)) % 11
			if remainder == 1:
				self.assertEqual(ruc_check_digit(first_ten), 0)
				seen.add(1)
			elif remainder == 0:
				self.assertEqual(ruc_check_digit(first_ten), 1)
				seen.add(0)
			if seen == {0, 1} and body > 1000:
				break
		self.assertEqual(seen, {0, 1})

	def test_check_digit_is_always_a_single_digit(self):
		rng = random.Random(7)
		for _ in range(5000):
			self.assertIn(ruc_check_digit(f"{rng.randrange(10**10):010d}"), range(10))

	def test_format_errors(self):
		cases = {
			"": "ruc_format",
			"2013131295": "ruc_format",  # 10 digits
			"201313129550": "ruc_format",  # 12 digits
			"2013131295A": "ruc_format",
			"20-13131295": "ruc_format",
			"２０１３１３１２９５５": "ruc_format",  # full-width digits
			"20131312955.0": "ruc_format",
		}
		for value, code in cases.items():
			with self.subTest(value=value):
				with self.assertRaises(IdentityError) as ctx:
					validate_ruc(value)
				self.assertEqual(ctx.exception.code, code)

	def test_prefix_is_checked(self):
		# A number with a correct check digit but an unknown prefix.
		first_ten = "3012345678"
		candidate = first_ten + str(ruc_check_digit(first_ten))
		with self.assertRaises(IdentityError) as ctx:
			validate_ruc(candidate)
		self.assertEqual(ctx.exception.code, "ruc_prefix")
		for prefix in ("10", "15", "16", "17", "20"):
			first_ten = prefix + "12345678"
			self.assertTrue(is_valid_ruc(first_ten + str(ruc_check_digit(first_ten))))

	def test_whitespace_is_ignored(self):
		self.assertEqual(validate_ruc(" 20131312955 "), "20131312955")
		self.assertEqual(validate_ruc("2013 1312 955"), "20131312955")

	def test_accepts_int(self):
		self.assertEqual(validate_ruc(20131312955), "20131312955")

	def test_check_digit_argument_validation(self):
		for bad in ("", "123", "12345678901", "12345678a0"):
			with self.subTest(bad=bad), self.assertRaises(ValueError):
				ruc_check_digit(bad)


class TestDni(unittest.TestCase):
	def test_valid(self):
		self.assertEqual(validate_dni("12345678"), "12345678")
		self.assertEqual(validate_dni("00012345"), "00012345")  # leading zeros kept
		self.assertEqual(validate_dni(" 12345678 "), "12345678")

	def test_invalid(self):
		for value in ("", "1234567", "123456789", "1234567A", "1234-5678", None):
			with self.subTest(value=value):
				with self.assertRaises(IdentityError) as ctx:
					validate_dni(value)
				self.assertEqual(ctx.exception.code, "dni_format")


class TestValidateIdentityNumber(unittest.TestCase):
	def test_dispatch(self):
		self.assertEqual(validate_identity_number("6", "20131312955"), "20131312955")
		self.assertEqual(validate_identity_number("1", "12345678"), "12345678")
		with self.assertRaises(IdentityError):
			validate_identity_number("6", "12345678")  # a DNI is not a RUC
		with self.assertRaises(IdentityError):
			validate_identity_number("1", "20131312955")  # a RUC is not a DNI

	def test_missing_parts(self):
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number("", "12345678")
		self.assertEqual(ctx.exception.code, "type_missing")
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number("1", "  ")
		self.assertEqual(ctx.exception.code, "number_missing")
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number(None, None)
		self.assertEqual(ctx.exception.code, "type_missing")

	def test_carnet_de_extranjeria_and_passport(self):
		# MD-UC-03: foreign documents are saved without the RUC check.
		self.assertEqual(validate_identity_number("4", "001234567"), "001234567")
		self.assertEqual(validate_identity_number("7", "ab123456"), "AB123456")
		self.assertEqual(validate_identity_number("7", "A" * 12), "A" * 12)
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number("7", "A" * 13)
		self.assertEqual(ctx.exception.code, "too_long")
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number("4", "12345678901234")
		self.assertEqual(ctx.exception.code, "too_long")
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number("7", "AB-123456")
		self.assertEqual(ctx.exception.code, "not_alphanumeric")

	def test_foreign_tax_documents(self):
		self.assertEqual(validate_identity_number("0", "12-3456789"), "12-3456789")
		self.assertEqual(validate_identity_number("B", "x123.456"), "X123.456")
		self.assertEqual(validate_identity_number("b", "x123"), "X123")
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number("0", "1" * 16)
		self.assertEqual(ctx.exception.code, "too_long")
		with self.assertRaises(IdentityError) as ctx:
			validate_identity_number("0", "ÑANDÚ")
		self.assertEqual(ctx.exception.code, "invalid_characters")

	def test_normalize(self):
		self.assertEqual(normalize_identity_number(None), "")
		self.assertEqual(normalize_identity_number(" a b\t1 "), "AB1")
		self.assertEqual(normalize_identity_number(123), "123")


if __name__ == "__main__":
	unittest.main()
