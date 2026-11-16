# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Pure unit tests (no database)."""

import unittest

from erpnext_peru.utils.voucher import (
	VoucherError,
	expected_series_letter,
	format_voucher_number,
	join_received_voucher,
	normalize_voucher_number,
	parse_voucher_number,
	validate_issued_series,
	validate_number,
	validate_received_voucher,
)


class TestIssuedSeries(unittest.TestCase):
	def test_factura_and_boleta(self):
		self.assertEqual(validate_issued_series("01", "F001"), "F001")
		self.assertEqual(validate_issued_series("01", " f0a1 "), "F0A1")
		self.assertEqual(validate_issued_series("03", "B001"), "B001")
		self.assertEqual(validate_issued_series("03", "BB99"), "BB99")

	def test_wrong_letter(self):
		for comprobante_type, series in (("01", "B001"), ("03", "F001")):
			with self.subTest(series=series):
				with self.assertRaises(VoucherError) as ctx:
					validate_issued_series(comprobante_type, series)
				self.assertEqual(ctx.exception.code, "series_letter")

	def test_bad_shape(self):
		for series in ("0001", "F01", "F0001", "F-01", "E001", "FÑ01", "F 0 1"):
			with self.subTest(series=series):
				with self.assertRaises(VoucherError) as ctx:
					validate_issued_series("01", series)
				self.assertEqual(ctx.exception.code, "series_format")

	def test_missing(self):
		for series in ("", None, "   "):
			with self.assertRaises(VoucherError) as ctx:
				validate_issued_series("01", series)
			self.assertEqual(ctx.exception.code, "series_missing")

	def test_notes_follow_the_modified_voucher(self):
		for note in ("07", "08"):
			self.assertEqual(validate_issued_series(note, "FC01", "01"), "FC01")
			self.assertEqual(validate_issued_series(note, "BC01", "03"), "BC01")
			with self.assertRaises(VoucherError) as ctx:
				validate_issued_series(note, "BC01", "01")
			self.assertEqual(ctx.exception.code, "series_letter")
			with self.assertRaises(VoucherError) as ctx:
				validate_issued_series(note, "FC01", "03")
			self.assertEqual(ctx.exception.code, "series_letter")
			# original not known yet: only the shape is checked
			self.assertEqual(validate_issued_series(note, "FC01"), "FC01")
			self.assertEqual(validate_issued_series(note, "BC01"), "BC01")

	def test_only_issuable_types(self):
		for comprobante_type in ("09", "12", "", None, "1"):
			with self.subTest(comprobante_type=comprobante_type):
				with self.assertRaises(VoucherError) as ctx:
					validate_issued_series(comprobante_type, "F001")
				self.assertEqual(ctx.exception.code, "type_not_issuable")

	def test_expected_letter(self):
		self.assertEqual(expected_series_letter("01"), "F")
		self.assertEqual(expected_series_letter("03"), "B")
		self.assertEqual(expected_series_letter("07", "01"), "F")
		self.assertEqual(expected_series_letter("08", "03"), "B")
		self.assertIsNone(expected_series_letter("07"))
		self.assertIsNone(expected_series_letter("09"))


class TestNumber(unittest.TestCase):
	def test_valid(self):
		self.assertEqual(validate_number(1), 1)
		self.assertEqual(validate_number("00000123"), 123)
		self.assertEqual(validate_number(" 7 "), 7)
		self.assertEqual(validate_number(99999999), 99999999)

	def test_range(self):
		for value in (0, -1, 100000000, "000000000", "100000000"):
			with self.subTest(value=value):
				with self.assertRaises(VoucherError) as ctx:
					validate_number(value)
				self.assertEqual(ctx.exception.code, "number_range")

	def test_format(self):
		for value in ("", None, "12a", "1.0", 1.0, True, "１２"):
			with self.subTest(value=value):
				with self.assertRaises(VoucherError) as ctx:
					validate_number(value)
				self.assertEqual(ctx.exception.code, "number_format")


class TestFormatting(unittest.TestCase):
	def test_format(self):
		self.assertEqual(format_voucher_number("F001", 123), "F001-00000123")
		self.assertEqual(format_voucher_number("b001", "1"), "B001-00000001")
		self.assertEqual(format_voucher_number("F001", 99999999), "F001-99999999")
		with self.assertRaises(VoucherError):
			format_voucher_number("F01", 1)
		with self.assertRaises(VoucherError):
			format_voucher_number("F001", 0)

	def test_parse(self):
		self.assertEqual(parse_voucher_number("F001-00000123"), ("F001", 123))
		self.assertEqual(parse_voucher_number("f001-123"), ("F001", 123))
		self.assertEqual(parse_voucher_number(" 0001 - 45 "), ("0001", 45))
		for bad in ("F001", "F001-", "-123", "F001-12A", "F001-123456789", "F01-1", "F001-0", "", None):
			with self.subTest(bad=bad), self.assertRaises(VoucherError):
				parse_voucher_number(bad)

	def test_round_trip(self):
		for series in ("F001", "B123", "0001", "FC01"):
			for number in (1, 9, 10, 12345, 99999999):
				text = format_voucher_number(series, number)
				self.assertEqual(parse_voucher_number(text), (series, number))
				self.assertEqual(normalize_voucher_number(text), text)
		self.assertEqual(normalize_voucher_number("f001-7"), "F001-00000007")


class TestReceivedVoucher(unittest.TestCase):
	def test_standard_types(self):
		self.assertEqual(validate_received_voucher("01", "f001", "123"), ("F001", "00000123"))
		self.assertEqual(validate_received_voucher("01", "E001", "5"), ("E001", "00000005"))
		self.assertEqual(validate_received_voucher("03", "0001", "00000045"), ("0001", "00000045"))
		self.assertEqual(validate_received_voucher("07", "FC01", 9), ("FC01", "00000009"))

	def test_standard_types_errors(self):
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("01", "001", "1")
		self.assertEqual(ctx.exception.code, "series_format")
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("01", "", "1")
		self.assertEqual(ctx.exception.code, "series_format")
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("01", "F001", "")
		self.assertEqual(ctx.exception.code, "number_missing")
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("01", "F001", "123456789")
		self.assertEqual(ctx.exception.code, "number_range")
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("01", "F001", "12A")
		self.assertEqual(ctx.exception.code, "number_format")

	def test_other_types_are_loose(self):
		self.assertEqual(validate_received_voucher("14", "", "s123-456"), ("", "S123-456"))
		self.assertEqual(validate_received_voucher("14", "001", "0012345"), ("001", "0012345"))
		self.assertEqual(validate_received_voucher(None, "", "X1"), ("", "X1"))
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("14", "", "1" * 21)
		self.assertEqual(ctx.exception.code, "number_format_generic")
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("14", "A" * 21, "1")
		self.assertEqual(ctx.exception.code, "series_format_generic")
		with self.assertRaises(VoucherError) as ctx:
			validate_received_voucher("14", "", "12/34")
		self.assertEqual(ctx.exception.code, "number_format_generic")

	def test_join(self):
		self.assertEqual(join_received_voucher("F001", "00000123"), "F001-00000123")
		self.assertEqual(join_received_voucher("", "S123"), "S123")


if __name__ == "__main__":
	unittest.main()
