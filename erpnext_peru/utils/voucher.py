# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Series and correlative numbers of comprobantes de pago.

Free of Frappe imports so it can be unit-tested on its own.

A voucher is identified by ``<series>-<number>``, e.g. ``F001-00000123``.

Rules implemented for vouchers ISSUED by the company (electronic issue):

* Factura (01): series is four characters starting with ``F``.
* Boleta de venta (03): series is four characters starting with ``B``.
* Nota de crédito (07) / Nota de débito (08): series starts with ``F`` when
  the note modifies a Factura and with ``B`` when it modifies a Boleta.
* The correlative number has between one and eight digits (1 .. 99999999).

Source: SUNAT "Guía de elaboración de documentos electrónicos XML - UBL 2.1"
(serie ``F###`` / ``B###`` and number ``NNNNNNNN``) and Anexo N.° 8,
Catálogo N.° 01, of Resolución de Superintendencia 097-2012/SUNAT.
"""

from __future__ import annotations

import re

TYPE_FACTURA = "01"
TYPE_BOLETA = "03"
TYPE_CREDIT_NOTE = "07"
TYPE_DEBIT_NOTE = "08"

# Comprobantes the company issues from Sales Invoices.
ISSUABLE_TYPES = (TYPE_FACTURA, TYPE_BOLETA, TYPE_CREDIT_NOTE, TYPE_DEBIT_NOTE)
NOTE_TYPES = (TYPE_CREDIT_NOTE, TYPE_DEBIT_NOTE)
# Comprobantes a note can modify.
MODIFIABLE_TYPES = (TYPE_FACTURA, TYPE_BOLETA)

SERIES_LETTER = {TYPE_FACTURA: "F", TYPE_BOLETA: "B"}

MAX_NUMBER = 99_999_999
NUMBER_WIDTH = 8

_ISSUED_SERIES_RE = re.compile(r"^[FB][A-Z0-9]{3}$")
_FOUR_ALNUM_RE = re.compile(r"^[A-Z0-9]{4}$")
_GENERIC_SERIES_RE = re.compile(r"^[A-Z0-9-]{1,20}$")
_GENERIC_NUMBER_RE = re.compile(r"^[A-Z0-9-]{1,20}$")
_VOUCHER_RE = re.compile(r"^([A-Z0-9]{4})-(\d{1,8})$")


class VoucherError(ValueError):
	"""Raised when a series or number is not valid. See ``code`` / ``params``."""

	def __init__(self, code: str, message: str, **params):
		super().__init__(message)
		self.code = code
		self.params = params


def normalize_series(series) -> str:
	if series is None:
		return ""
	return re.sub(r"\s+", "", str(series)).upper()


def expected_series_letter(comprobante_type: str, original_type: str | None = None) -> str | None:
	"""Letter an issued series must start with, or None when it cannot be told yet."""
	if comprobante_type in SERIES_LETTER:
		return SERIES_LETTER[comprobante_type]
	if comprobante_type in NOTE_TYPES and original_type in SERIES_LETTER:
		return SERIES_LETTER[original_type]
	return None


def validate_issued_series(comprobante_type, series, original_type=None) -> str:
	"""Validate the series of a voucher issued by the company. Returns it normalized.

	``original_type`` is the type (01 or 03) of the voucher modified by a note.
	When it is not given for a note, only the general shape is checked.
	"""
	if comprobante_type not in ISSUABLE_TYPES:
		raise VoucherError(
			"type_not_issuable",
			"This type of comprobante cannot be issued from a Sales Invoice",
			comprobante_type=comprobante_type,
		)
	value = normalize_series(series)
	if not value:
		raise VoucherError("series_missing", "Series is required")
	if not _ISSUED_SERIES_RE.match(value):
		raise VoucherError(
			"series_format",
			"Series must have four characters and start with F or B",
			series=value,
		)
	letter = expected_series_letter(comprobante_type, original_type)
	if letter and value[0] != letter:
		raise VoucherError(
			"series_letter",
			"Series must start with the letter that corresponds to the comprobante",
			series=value,
			letter=letter,
		)
	return value


def validate_number(number) -> int:
	"""Validate a correlative number (1 .. 99999999) and return it as int."""
	if isinstance(number, bool):
		raise VoucherError("number_format", "Number must be a whole number", number=number)
	if isinstance(number, int):
		value = number
	else:
		text = "" if number is None else str(number).strip()
		if not (text.isascii() and text.isdigit()):
			raise VoucherError("number_format", "Number must be a whole number", number=number)
		value = int(text)
	if value < 1 or value > MAX_NUMBER:
		raise VoucherError(
			"number_range",
			"Number must be between 1 and 99999999",
			number=value,
		)
	return value


def format_voucher_number(series, number) -> str:
	"""Return ``SSSS-NNNNNNNN`` (number left-padded with zeros to eight digits)."""
	value = normalize_series(series)
	if not _FOUR_ALNUM_RE.match(value):
		raise VoucherError("series_format", "Series must have four characters", series=value)
	return f"{value}-{validate_number(number):0{NUMBER_WIDTH}d}"


def parse_voucher_number(text) -> tuple[str, int]:
	"""Split ``F001-123`` / ``F001-00000123`` into ``("F001", 123)``."""
	value = normalize_series(text)
	match = _VOUCHER_RE.match(value)
	if not match:
		raise VoucherError(
			"voucher_format",
			"Voucher number must look like F001-00000123",
			voucher=value,
		)
	return match.group(1), validate_number(match.group(2))


def normalize_voucher_number(text) -> str:
	"""Canonical ``SSSS-NNNNNNNN`` form of a voucher number typed by a user."""
	series, number = parse_voucher_number(text)
	return format_voucher_number(series, number)


def validate_received_voucher(comprobante_type, series, number) -> tuple[str, str]:
	"""Validate series/number of a voucher RECEIVED from a supplier.

	Returns ``(series, number)`` normalized. For Facturas, Boletas and their
	notes the series has four letters/digits and the number up to eight digits
	(stored zero-padded to eight). Other document types (public service
	receipts, customs declarations, ...) have their own shapes, so only a
	loose check is applied: series optional, both limited to 20 characters.
	"""
	series_value = normalize_series(series)
	number_value = normalize_series(number)
	if not number_value:
		raise VoucherError("number_missing", "Number is required")

	if comprobante_type in ISSUABLE_TYPES:
		if not _FOUR_ALNUM_RE.match(series_value):
			raise VoucherError(
				"series_format",
				"Series must have four characters",
				series=series_value,
			)
		return series_value, f"{validate_number(number_value):0{NUMBER_WIDTH}d}"

	if series_value and not _GENERIC_SERIES_RE.match(series_value):
		raise VoucherError(
			"series_format_generic",
			"Series may have up to 20 letters, digits or hyphens",
			series=series_value,
		)
	if not _GENERIC_NUMBER_RE.match(number_value):
		raise VoucherError(
			"number_format_generic",
			"Number may have up to 20 letters, digits or hyphens",
			number=number_value,
		)
	return series_value, number_value


def join_received_voucher(series: str, number: str) -> str:
	return f"{series}-{number}" if series else number
