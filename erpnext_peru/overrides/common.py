# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Helpers shared by the document hooks."""

import frappe
from frappe import _

from erpnext_peru.utils.identity import IdentityError
from erpnext_peru.utils.voucher import VoucherError

PERU = "Peru"


class PeruValidationError(frappe.ValidationError):
	"""Base class of the validation errors raised by this app."""


class IdentityDocumentError(PeruValidationError):
	pass


class DuplicateIdentityError(PeruValidationError):
	pass


class ComprobanteError(PeruValidationError):
	pass


class DuplicateVoucherError(PeruValidationError):
	pass


def is_peru_company(company: str | None) -> bool:
	"""True when the company exists and its country is Peru."""
	if not company:
		return False
	return frappe.get_cached_value("Company", company, "country") == PERU


def identity_error_message(error: IdentityError) -> str:
	value = frappe.bold(error.params.get("value") or "")
	messages = {
		"type_missing": _("Select the identity document type."),
		"number_missing": _("Enter the identity document number."),
		"ruc_format": _("RUC {0} is not valid: it must have exactly 11 digits.").format(value),
		"ruc_prefix": _("RUC {0} is not valid: it must start with 10, 15, 16, 17 or 20.").format(value),
		"ruc_check_digit": _(
			"RUC {0} is not valid: the check digit does not match. Please review the number."
		).format(value),
		"dni_format": _("DNI {0} is not valid: it must have exactly 8 digits.").format(value),
		"too_long": _(
			"Identity document number {0} is too long: this document type allows at most {1} characters."
		).format(value, error.params.get("max_length")),
		"not_alphanumeric": _("Identity document number {0} may only contain letters and digits.").format(
			value
		),
		"invalid_characters": _(
			"Identity document number {0} contains characters that are not allowed."
		).format(value),
	}
	return messages.get(error.code) or str(error)


def throw_identity_error(error: IdentityError):
	frappe.throw(
		identity_error_message(error), exc=IdentityDocumentError, title=_("Invalid Identity Document")
	)


def voucher_error_message(error: VoucherError) -> str:
	params = error.params
	messages = {
		"type_not_issuable": _("Comprobante type {0} cannot be issued from a Sales Invoice.").format(
			frappe.bold(params.get("comprobante_type") or "")
		),
		"series_missing": _("Enter the series of the comprobante."),
		"series_format": _(
			"Series {0} is not valid: it must have four letters or digits (for example F001 or B001)."
		).format(frappe.bold(params.get("series") or "")),
		"series_letter": _("Series {0} is not valid for this comprobante: it must start with {1}.").format(
			frappe.bold(params.get("series") or ""), frappe.bold(params.get("letter") or "")
		),
		"series_format_generic": _(
			"Series {0} is not valid: it may have up to 20 letters, digits or hyphens."
		).format(frappe.bold(params.get("series") or "")),
		"number_missing": _("Enter the number of the comprobante."),
		"number_format": _("Number {0} is not valid: it must contain digits only.").format(
			frappe.bold(str(params.get("number") or ""))
		),
		"number_range": _("Number {0} is not valid: it must be between 1 and 99999999.").format(
			frappe.bold(str(params.get("number")))
		),
		"number_format_generic": _(
			"Number {0} is not valid: it may have up to 20 letters, digits or hyphens."
		).format(frappe.bold(str(params.get("number") or ""))),
		"voucher_format": _(
			"Voucher number {0} is not valid: write the series and the number, for example F001-00000123."
		).format(frappe.bold(params.get("voucher") or "")),
	}
	return messages.get(error.code) or str(error)


def throw_voucher_error(error: VoucherError):
	frappe.throw(voucher_error_message(error), exc=ComprobanteError, title=_("Invalid Comprobante"))


def check_catalogue_entry(doctype: str, code: str | None, label: str):
	"""Throw unless ``code`` exists in the catalogue ``doctype`` and is enabled."""
	if not code:
		return
	enabled = frappe.db.get_value(doctype, code, "enabled")
	if enabled is None:
		frappe.throw(
			_("{0}: code {1} does not exist in {2}.").format(label, frappe.bold(code), _(doctype)),
			exc=ComprobanteError,
		)
	if not int(enabled):
		frappe.throw(
			_("{0}: code {1} is disabled in {2}.").format(label, frappe.bold(code), _(doctype)),
			exc=ComprobanteError,
		)
