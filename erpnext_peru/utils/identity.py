# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Validation of Peruvian identity document numbers (RUC, DNI, CE, passport...).

This module is deliberately free of Frappe imports so it can be unit-tested
on its own and reused by importers.

Sources
-------
* Document type codes: SUNAT "Anexo N.° 8 - Catálogo de códigos",
  Catálogo N.° 06 (Resolución de Superintendencia 097-2012/SUNAT and
  amendments).
* RUC check digit: modulus 11 over the first ten digits with the weights
  5, 4, 3, 2, 7, 6, 5, 4, 3, 2 (left to right). The check digit is
  ``11 - (sum % 11)``; a result of 10 becomes 0 and a result of 11 becomes 1.
"""

from __future__ import annotations

import re

from erpnext_peru.utils.errors import CodedError

# Catálogo 06 codes that receive specific handling.
DOC_NON_DOMICILED = "0"  # Doc. trib. no domiciliado sin RUC
DOC_DNI = "1"
DOC_CE = "4"  # Carnet de extranjería
DOC_RUC = "6"
DOC_PASSPORT = "7"

RUC_LENGTH = 11
DNI_LENGTH = 8
RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

# First two digits of a RUC identify the kind of taxpayer:
# 10 natural person (DNI), 15/16/17 natural persons and other entities
# without DNI, 20 legal entities.
RUC_PREFIXES = frozenset({"10", "15", "16", "17", "20"})

# Maximum lengths per Catálogo 06. Types that are not listed fall back to
# DEFAULT_MAX_LENGTH.
MAX_LENGTH = {
	DOC_NON_DOMICILED: 15,
	DOC_DNI: DNI_LENGTH,
	DOC_CE: 12,
	DOC_RUC: RUC_LENGTH,
	DOC_PASSPORT: 12,
}
DEFAULT_MAX_LENGTH = 15

# Document types whose number must be strictly letters and digits.
ALPHANUMERIC_ONLY = frozenset({DOC_CE, DOC_PASSPORT})

_ALNUM_RE = re.compile(r"^[A-Z0-9]+$")
_PRINTABLE_RE = re.compile(r"^[!-~]+$")  # visible ASCII, no spaces
# Characters of HTML that no document number has. Frappe would rewrite a value
# holding them after this validation, and they would reach printed documents.
_MARKUP_CHARACTERS = frozenset("<>&\"'`")


class IdentityError(CodedError):
	"""Raised when an identity document number is not valid."""


def normalize_identity_number(number) -> str:
	"""Return the number without surrounding/inner whitespace, upper-cased."""
	if number is None:
		return ""
	return re.sub(r"\s+", "", str(number)).upper()


def ruc_check_digit(first_ten_digits: str) -> int:
	"""Compute the check digit for the first ten digits of a RUC."""
	if len(first_ten_digits) != 10 or not _is_ascii_digits(first_ten_digits):
		raise ValueError("ruc_check_digit expects exactly ten digits")
	total = sum(int(d) * w for d, w in zip(first_ten_digits, RUC_WEIGHTS, strict=True))
	result = 11 - (total % 11)
	if result == 10:
		return 0
	if result == 11:
		return 1
	return result


def is_valid_ruc(number) -> bool:
	"""True when ``number`` is an 11-digit RUC with a correct prefix and check digit."""
	try:
		validate_ruc(number)
	except IdentityError:
		return False
	return True


def validate_ruc(number) -> str:
	"""Validate a RUC and return it normalized. Raises IdentityError."""
	ruc = normalize_identity_number(number)
	if not _is_ascii_digits(ruc) or len(ruc) != RUC_LENGTH:
		raise IdentityError("ruc_format", "RUC must have exactly 11 digits", value=ruc)
	if ruc[:2] not in RUC_PREFIXES:
		raise IdentityError(
			"ruc_prefix",
			"RUC must start with 10, 15, 16, 17 or 20",
			value=ruc,
		)
	if ruc_check_digit(ruc[:10]) != int(ruc[10]):
		raise IdentityError("ruc_check_digit", "RUC check digit is not valid", value=ruc)
	return ruc


def validate_dni(number) -> str:
	"""Validate a DNI (exactly eight digits) and return it normalized."""
	dni = normalize_identity_number(number)
	if not _is_ascii_digits(dni) or len(dni) != DNI_LENGTH:
		raise IdentityError("dni_format", "DNI must have exactly 8 digits", value=dni)
	return dni


def validate_identity_number(doc_type, number) -> str:
	"""Validate ``number`` for the Catálogo 06 ``doc_type`` code.

	Returns the normalized number. Raises IdentityError when it is not valid.
	Only the check digit / shape is verified; whether the taxpayer exists or is
	active with SUNAT is out of scope.
	"""
	doc_type = "" if doc_type is None else str(doc_type).strip().upper()
	value = normalize_identity_number(number)

	if not doc_type:
		raise IdentityError("type_missing", "Identity document type is required")
	if not value:
		raise IdentityError("number_missing", "Identity document number is required")

	if doc_type == DOC_RUC:
		return validate_ruc(value)
	if doc_type == DOC_DNI:
		return validate_dni(value)

	max_length = MAX_LENGTH.get(doc_type, DEFAULT_MAX_LENGTH)
	if len(value) > max_length:
		raise IdentityError(
			"too_long",
			"Identity document number is longer than allowed",
			value=value,
			max_length=max_length,
		)
	if doc_type in ALPHANUMERIC_ONLY:
		if not _ALNUM_RE.match(value):
			raise IdentityError(
				"not_alphanumeric",
				"Identity document number may only contain letters and digits",
				value=value,
			)
	elif not _PRINTABLE_RE.match(value) or _MARKUP_CHARACTERS & set(value):
		raise IdentityError(
			"invalid_characters",
			"Identity document number contains characters that are not allowed",
			value=value,
		)
	return value


def _is_ascii_digits(value: str) -> bool:
	# str.isdigit() accepts characters such as "²" or Arabic-Indic digits.
	return bool(value) and value.isascii() and value.isdigit()
