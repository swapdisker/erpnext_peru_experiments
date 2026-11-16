# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Comprobante de pago rules for Sales Invoices of Peruvian companies.

Summary
-------
* ``validate`` (every save): fills defaults, normalizes what the user typed and
  rejects values that can never be right (unknown type, malformed series...).
* ``before_submit``: enforces the rules that make the comprobante issuable and
  only then allocates the correlative number, inside the submit transaction.

Numbers are never typed by users and never reused: a cancelled voucher keeps
its number and an amended invoice receives a new one.

Invoices of companies whose country is not Peru, and opening invoices
(``is_opening = "Yes"``), are left untouched.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_peru.erpnext_peru.doctype.sunat_voucher_series.sunat_voucher_series import (
	allocate_next_number,
	get_enabled_series,
)
from erpnext_peru.overrides.common import (
	ComprobanteError,
	check_catalogue_entry,
	is_peru_company,
	throw_identity_error,
	throw_voucher_error,
)
from erpnext_peru.utils.identity import DOC_NON_DOMICILED, DOC_RUC, IdentityError, validate_ruc
from erpnext_peru.utils.voucher import (
	ISSUABLE_TYPES,
	MODIFIABLE_TYPES,
	NOTE_TYPES,
	TYPE_BOLETA,
	TYPE_CREDIT_NOTE,
	TYPE_DEBIT_NOTE,
	TYPE_FACTURA,
	VoucherError,
	expected_series_letter,
	format_voucher_number,
	normalize_series,
	normalize_voucher_number,
	validate_issued_series,
)

# Reglamento de Comprobantes de Pago (R.S. 007-99/SUNAT), art. 8, num. 3.10 and
# Anexo N.° 2 of R.S. 097-2012/SUNAT: the buyer must be identified when the
# total of a Boleta de venta EXCEEDS seven hundred soles.
BOLETA_ID_THRESHOLD = 700.0

COMPROBANTE_TYPE_DOCTYPE = "SUNAT Comprobante Type"
CREDIT_REASON_DOCTYPE = "SUNAT Credit Note Reason"
DEBIT_REASON_DOCTYPE = "SUNAT Debit Note Reason"


def applies_to(doc) -> bool:
	return is_peru_company(doc.company) and doc.get("is_opening") != "Yes"


def _is_submitted_in_database(doc) -> bool:
	"""True when the invoice already exists as a submitted (or cancelled) document."""
	if doc.is_new() or not doc.name:
		return False
	return cint(frappe.db.get_value(doc.doctype, doc.name, "docstatus")) != 0


# --------------------------------------------------------------------------- hooks


def validate(doc, method=None):
	if not applies_to(doc):
		return
	# Frappe runs "validate" only while saving a draft or submitting one. Should
	# other code ever run it on an issued voucher, the voucher must not change.
	if _is_submitted_in_database(doc):
		return

	# Never trust a number that arrives with the document (amended copies carry
	# the old one, API clients may send one): it is assigned in before_submit.
	doc.pe_number = 0
	doc.pe_voucher_number = None

	_snapshot_customer_identity(doc)
	_set_default_type(doc)
	_validate_type(doc)
	_set_note_fields(doc)
	_set_series(doc)
	_warn_boleta_to_ruc_customer(doc)


def before_submit(doc, method=None):
	if not applies_to(doc):
		return

	_validate_issuer(doc)
	_validate_customer_identity(doc)
	_validate_note(doc)

	if not doc.pe_series:
		options = _series_options(doc)
		if options:
			frappe.throw(
				_("Select the series of the comprobante. Available series: {0}.").format(", ".join(options)),
				exc=ComprobanteError,
			)
		frappe.throw(
			_(
				"There is no enabled series for comprobante type {0} in company {1}. Create one in SUNAT Voucher Series."
			).format(frappe.bold(doc.pe_comprobante_type), frappe.bold(doc.company)),
			exc=ComprobanteError,
		)
	try:
		validate_issued_series(doc.pe_comprobante_type, doc.pe_series, doc.pe_original_type)
	except VoucherError as error:
		throw_voucher_error(error)

	number = allocate_next_number(doc.company, doc.pe_comprobante_type, doc.pe_series, doc.name)
	doc.pe_number = number
	doc.pe_voucher_number = format_voucher_number(doc.pe_series, number)


def on_trash(doc, method=None):
	"""A voucher number, once issued, must stay on record even after cancellation."""
	if doc.get("pe_voucher_number"):
		frappe.throw(
			_(
				"{0} cannot be deleted: comprobante {1} was issued with it and its number must remain on record."
			).format(doc.name, frappe.bold(doc.pe_voucher_number)),
			exc=ComprobanteError,
		)


# ------------------------------------------------------------------------- helpers


def _snapshot_customer_identity(doc):
	"""Copy the customer's identity document onto the invoice.

	The copy is what the issued comprobante states, even if the customer
	master is corrected later.
	"""
	row = None
	if doc.customer:
		row = frappe.db.get_value(
			"Customer", doc.customer, ["pe_identity_type", "pe_identity_number"], as_dict=True
		)
	doc.pe_customer_identity_type = (row and row.pe_identity_type) or None
	doc.pe_customer_identity_number = (row and row.pe_identity_number) or None


def _set_default_type(doc):
	if doc.pe_comprobante_type:
		return
	if cint(doc.is_return):
		doc.pe_comprobante_type = TYPE_CREDIT_NOTE
	elif cint(doc.get("is_debit_note")):
		doc.pe_comprobante_type = TYPE_DEBIT_NOTE
	elif doc.pe_customer_identity_type == DOC_RUC:
		doc.pe_comprobante_type = TYPE_FACTURA
	else:
		doc.pe_comprobante_type = TYPE_BOLETA


def _warn_boleta_to_ruc_customer(doc):
	"""Allowed, but usually a slip: a Boleta gives the customer no tax credit."""
	if doc.pe_comprobante_type == TYPE_BOLETA and doc.pe_customer_identity_type == DOC_RUC:
		frappe.msgprint(
			_(
				"Customer {0} has a RUC but this invoice will be issued as a Boleta de venta. Change the comprobante type to Factura if that is what the customer needs."
			).format(frappe.bold(doc.customer)),
			indicator="orange",
			alert=True,
		)


def _validate_type(doc):
	comprobante_type = doc.pe_comprobante_type
	check_catalogue_entry(COMPROBANTE_TYPE_DOCTYPE, comprobante_type, _("Comprobante Type"))
	if comprobante_type not in ISSUABLE_TYPES:
		frappe.throw(
			_("Comprobante type {0} cannot be issued from a Sales Invoice. Use one of: {1}.").format(
				frappe.bold(comprobante_type), ", ".join(ISSUABLE_TYPES)
			),
			exc=ComprobanteError,
		)
	if cint(doc.is_return):
		if comprobante_type != TYPE_CREDIT_NOTE:
			frappe.throw(
				_("A return (credit note) must use comprobante type 07 - Nota de crédito."),
				exc=ComprobanteError,
			)
	elif cint(doc.get("is_debit_note")):
		if comprobante_type != TYPE_DEBIT_NOTE:
			frappe.throw(
				_("A debit note must use comprobante type 08 - Nota de débito."), exc=ComprobanteError
			)
	elif comprobante_type not in (TYPE_FACTURA, TYPE_BOLETA):
		frappe.throw(
			_(
				"An invoice must use comprobante type 01 - Factura or 03 - Boleta de venta. Credit and debit notes are created from the invoice they modify."
			),
			exc=ComprobanteError,
		)


def _set_note_fields(doc):
	"""Keep the reason / modified-voucher fields consistent with the type."""
	comprobante_type = doc.pe_comprobante_type
	if comprobante_type not in NOTE_TYPES:
		doc.pe_credit_note_reason = None
		doc.pe_debit_note_reason = None
		doc.pe_original_type = None
		doc.pe_original_voucher_number = None
		return

	if comprobante_type == TYPE_CREDIT_NOTE:
		doc.pe_debit_note_reason = None
	else:
		doc.pe_credit_note_reason = None

	if doc.get("return_against"):
		original = frappe.db.get_value(
			"Sales Invoice",
			doc.return_against,
			["pe_comprobante_type", "pe_voucher_number"],
			as_dict=True,
		)
		# The linked invoice is authoritative. Invoices issued before this app was
		# installed carry no voucher number: then the user fills the fields in.
		if original and original.pe_voucher_number and original.pe_comprobante_type:
			doc.pe_original_type = original.pe_comprobante_type
			doc.pe_original_voucher_number = original.pe_voucher_number

	if doc.pe_original_type:
		check_catalogue_entry(COMPROBANTE_TYPE_DOCTYPE, doc.pe_original_type, _("Modified Comprobante Type"))
		if doc.pe_original_type not in MODIFIABLE_TYPES:
			frappe.throw(
				_("A note can only modify a Factura (01) or a Boleta de venta (03)."), exc=ComprobanteError
			)
	if (doc.pe_original_voucher_number or "").strip():
		try:
			doc.pe_original_voucher_number = normalize_voucher_number(doc.pe_original_voucher_number)
		except VoucherError as error:
			throw_voucher_error(error)
	else:
		doc.pe_original_voucher_number = None


def _series_options(doc) -> list[str]:
	letter = expected_series_letter(doc.pe_comprobante_type, doc.pe_original_type)
	return get_enabled_series(doc.company, doc.pe_comprobante_type, letter)


def _set_series(doc):
	series = normalize_series(doc.pe_series)
	if not series:
		options = _series_options(doc)
		if len(options) == 1:
			series = options[0]
	doc.pe_series = series or None
	if series:
		try:
			validate_issued_series(doc.pe_comprobante_type, series, doc.pe_original_type)
		except VoucherError as error:
			throw_voucher_error(error)


def _validate_issuer(doc):
	tax_id = frappe.get_cached_value("Company", doc.company, "tax_id")
	if not (tax_id or "").strip():
		frappe.throw(
			_(
				"Company {0} has no RUC. Enter it in the Tax ID field of the company before issuing comprobantes."
			).format(frappe.bold(doc.company)),
			exc=ComprobanteError,
		)
	try:
		validate_ruc(tax_id)
	except IdentityError as error:
		throw_identity_error(error)


def _validate_customer_identity(doc):
	comprobante_type = doc.pe_comprobante_type
	identity_type = doc.pe_customer_identity_type
	identity_number = doc.pe_customer_identity_number
	# A note is governed by the comprobante it modifies.
	governing_type = doc.pe_original_type if comprobante_type in NOTE_TYPES else comprobante_type

	if governing_type == TYPE_FACTURA:
		# Anexo N.° 1 of R.S. 097-2012/SUNAT, field "Tipo y número de documento del
		# adquirente": RUC, except in export operations, where the buyer is
		# identified with type 0 (non-domiciled without RUC).
		if identity_type not in (DOC_RUC, DOC_NON_DOMICILED) or not identity_number:
			frappe.throw(
				_(
					"A Factura can only be issued to a customer identified with a RUC. Customer {0} has no RUC: register it on the customer, or issue a Boleta de venta."
				).format(frappe.bold(doc.customer)),
				exc=ComprobanteError,
				title=_("Factura Requires RUC"),
			)
	elif comprobante_type == TYPE_BOLETA:
		total = flt(doc.base_grand_total, 2)
		if total > BOLETA_ID_THRESHOLD and not (identity_type and identity_number):
			frappe.throw(
				_(
					"A Boleta de venta above S/ {0} must identify the customer. Register the identity document (DNI, carnet de extranjería, passport...) of customer {1}."
				).format(f"{BOLETA_ID_THRESHOLD:,.2f}", frappe.bold(doc.customer)),
				exc=ComprobanteError,
				title=_("Customer Identity Required"),
			)


def _validate_note(doc):
	comprobante_type = doc.pe_comprobante_type
	if comprobante_type not in NOTE_TYPES:
		return

	if comprobante_type == TYPE_CREDIT_NOTE:
		if not doc.pe_credit_note_reason:
			frappe.throw(
				_("Select the reason of the credit note (SUNAT catalogue 09)."), exc=ComprobanteError
			)
		check_catalogue_entry(CREDIT_REASON_DOCTYPE, doc.pe_credit_note_reason, _("Credit Note Reason"))
	else:
		if not doc.pe_debit_note_reason:
			frappe.throw(_("Select the reason of the debit note (SUNAT catalogue 10)."), exc=ComprobanteError)
		check_catalogue_entry(DEBIT_REASON_DOCTYPE, doc.pe_debit_note_reason, _("Debit Note Reason"))

	if not doc.pe_original_type or not doc.pe_original_voucher_number:
		frappe.throw(
			_(
				"Indicate the comprobante this note modifies: its type and its number (for example F001-00000123)."
			),
			exc=ComprobanteError,
		)
	# The series of the modified voucher is not constrained here: a note may
	# modify a paper comprobante (numeric series such as 0001).
