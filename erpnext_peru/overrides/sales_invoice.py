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

Invoices of companies whose country is not Peru, opening invoices
(``is_opening = "Yes"``) and the invoices ERPNext merges from POS Invoices when
a point-of-sale shift is closed are left untouched (see ``is_merged_pos_invoice``).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_peru.erpnext_peru.doctype.sunat_voucher_series.sunat_voucher_series import (
	allocate_next_number,
	get_enabled_series,
)
from erpnext_peru.overrides.common import (
	COMPROBANTE_TYPE_DOCTYPE,
	ComprobanteError,
	check_catalogue_entry,
	is_peru_invoice,
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
	parse_voucher_number,
	validate_issued_series,
)

# Reglamento de Comprobantes de Pago (R.S. 007-99/SUNAT), art. 8, num. 3.10 and
# Anexo N.° 2 of R.S. 097-2012/SUNAT: the buyer must be identified when the
# total of a Boleta de venta EXCEEDS seven hundred soles.
BOLETA_ID_THRESHOLD = 700.0
SOLES = "PEN"

CREDIT_REASON_DOCTYPE = "SUNAT Credit Note Reason"
DEBIT_REASON_DOCTYPE = "SUNAT Debit Note Reason"

# SUNAT catalogue 09 reasons for a return made at the point of sale, whose
# screen has no field for the reason.
REASON_TOTAL_RETURN = "06"  # Devolución total
REASON_ITEM_RETURN = "07"  # Devolución por ítem


def applies_to(doc) -> bool:
	return is_peru_invoice(doc) and not is_merged_pos_invoice(doc)


def is_merged_pos_invoice(doc) -> bool:
	"""True for an invoice ERPNext built by merging submitted POS Invoices.

	Closing a POS shift merges the shift's sales into one Sales Invoice per
	customer (often the generic walk-in customer) and the returns into credit
	notes without a reason. That document is not a comprobante: every sale at
	the counter needs its own, which this app does not issue yet. Applying the
	rules to it would only make the shift impossible to close.

	``is_consolidated`` alone is not trusted, because an API client can set it:
	every item must also come from a submitted POS Invoice.
	"""
	if not cint(doc.get("is_consolidated")):
		return False
	pos_invoices = {row.get("pos_invoice") for row in doc.get("items") or []}
	if not pos_invoices:
		return False
	# An item without a POS Invoice (None) never appears among the submitted ones.
	submitted = frappe.get_all(
		"POS Invoice", filters={"name": ("in", list(pos_invoices)), "docstatus": 1}, pluck="name"
	)
	return set(submitted) == pos_invoices


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
	_validate_igv_is_stated(doc)
	_validate_customer_identity(doc)
	_fill_pos_return_reason(doc)
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
	if doc.pe_comprobante_type and not _type_left_from_previous_save(doc):
		return
	doc.pe_comprobante_type = _default_type(doc)


def _default_type(doc) -> str:
	if cint(doc.get("is_return")):
		return TYPE_CREDIT_NOTE
	if cint(doc.get("is_debit_note")):
		return TYPE_DEBIT_NOTE
	if doc.get("pe_customer_identity_type") == DOC_RUC:
		return TYPE_FACTURA
	return TYPE_BOLETA


def _type_left_from_previous_save(doc) -> bool:
	"""True when the type was given automatically and what decided it has changed since.

	A draft saved for a customer without RUC gets a Boleta; switched to a
	customer with RUC, it becomes a Factura instead of keeping the Boleta (the
	point of sale has no field to change it). A type that differs from the
	default, or that was changed in this save, is the user's choice and is kept.
	"""
	if doc.is_new():
		return False
	before = doc.get_doc_before_save()
	if not before or before.get("pe_comprobante_type") != doc.pe_comprobante_type:
		return False
	return doc.pe_comprobante_type == _default_type(before) != _default_type(doc)


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

	linked = None
	if doc.get("return_against"):
		original = _linked_original(doc)
		# The linked invoice is authoritative. Invoices issued before this app was
		# installed carry no voucher number: then the user fills the fields in.
		if original and original.pe_voucher_number and original.pe_comprobante_type:
			doc.pe_original_type = original.pe_comprobante_type
			doc.pe_original_voucher_number = original.pe_voucher_number
			linked = original

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

	if not linked and doc.pe_original_type and doc.pe_original_voucher_number:
		linked = _check_typed_reference(doc)
	if linked:
		_take_identity_from(linked, doc)


def _linked_original(doc):
	"""The invoice a note is linked to ("Return Against"), which must be one this note can modify.

	ERPNext checks it for returns only: a debit note could be linked to another
	customer's invoice, another company's, or a draft, and would then name a
	voucher of somebody else. A note is issued to the buyer of the comprobante it
	modifies (SUNAT, Informe N.° 033-2002).
	"""
	original = frappe.db.get_value(
		"Sales Invoice",
		doc.return_against,
		[
			"company",
			"customer",
			"docstatus",
			"pe_comprobante_type",
			"pe_voucher_number",
			"pe_customer_identity_type",
			"pe_customer_identity_number",
		],
		as_dict=True,
	)
	if not original:
		return None
	if original.docstatus != 1:
		frappe.throw(
			_("{0} is not submitted: a note can only modify an invoice that was issued.").format(
				frappe.bold(doc.return_against)
			),
			exc=ComprobanteError,
		)
	if original.company != doc.company or original.customer != doc.customer:
		frappe.throw(
			_(
				"{0} was issued to {1} of company {2}: a note is issued to the same customer, by the same company, as the invoice it modifies."
			).format(
				frappe.bold(doc.return_against), frappe.bold(original.customer), frappe.bold(original.company)
			),
			exc=ComprobanteError,
		)
	return original


def _take_identity_from(original, doc):
	"""A note states the buyer of the voucher it modifies, as that voucher states it.

	SUNAT: a note is issued to the same buyer, and cannot change it. When the
	customer's document was corrected after the voucher was issued (a wrong RUC,
	say), the customer master no longer shows the buyer the voucher names.
	"""
	doc.pe_customer_identity_type = original.pe_customer_identity_type or None
	doc.pe_customer_identity_number = original.pe_customer_identity_number or None


def _check_typed_reference(doc):
	"""A modified voucher typed by hand, checked against the vouchers issued here.

	It may be a voucher of a previous system or on paper, which this app cannot
	know. But when its series is one of the company's, the voucher must have
	been issued, to this customer, and not cancelled. Returns it, if issued here.
	"""
	issued = frappe.db.get_value(
		"Sales Invoice",
		{
			"company": doc.company,
			"pe_comprobante_type": doc.pe_original_type,
			"pe_voucher_number": doc.pe_original_voucher_number,
		},
		["name", "customer", "docstatus", "pe_customer_identity_type", "pe_customer_identity_number"],
		as_dict=True,
	)
	voucher = frappe.bold(doc.pe_original_voucher_number)
	if issued:
		if issued.docstatus == 2:
			frappe.throw(
				_("Comprobante {0} ({1}) is cancelled: a note cannot modify it.").format(
					voucher, issued.name
				),
				exc=ComprobanteError,
			)
		if issued.customer != doc.customer:
			frappe.throw(
				_(
					"Comprobante {0} ({1}) was issued to {2}: a note is issued to the same customer as the comprobante it modifies."
				).format(voucher, issued.name, frappe.bold(issued.customer)),
				exc=ComprobanteError,
			)
		return issued
	series, number = parse_voucher_number(doc.pe_original_voucher_number)
	last = frappe.db.get_value(
		"SUNAT Voucher Series",
		{"company": doc.company, "comprobante_type": doc.pe_original_type, "series": series},
		"current_number",
	)
	if last is not None and number > cint(last):
		frappe.throw(
			_("Comprobante {0} has not been issued: the last number issued in series {1} is {2}.").format(
				voucher, frappe.bold(series), cint(last)
			),
			exc=ComprobanteError,
		)
	if last is None:
		other_type = frappe.db.get_value(
			"SUNAT Voucher Series",
			{
				"company": doc.company,
				"series": series,
				"comprobante_type": ("in", [t for t in MODIFIABLE_TYPES if t != doc.pe_original_type]),
			},
			"comprobante_type",
		)
		if other_type:
			frappe.throw(
				_(
					"Series {0} is the company's series for comprobante type {1}, not {2}: check the type of the comprobante the note modifies."
				).format(frappe.bold(series), other_type, doc.pe_original_type),
				exc=ComprobanteError,
			)
	return None


def _fill_pos_return_reason(doc):
	"""Give a return made at the point of sale its reason, from the cart as submitted.

	Not on save: the point of sale saves the draft when the cashier goes to the
	payment and still lets them edit the cart afterwards. A reason chosen on the
	desk form is kept.
	"""
	if (
		doc.pe_comprobante_type == TYPE_CREDIT_NOTE
		and cint(doc.get("is_pos"))
		and not doc.pe_credit_note_reason
	):
		doc.pe_credit_note_reason = _pos_return_reason(doc)


def _pos_return_reason(doc) -> str:
	"""06 when the return gives back everything the original sale had, 07 otherwise.

	Only quantities per item are compared; an earlier partial return of the same
	sale makes this one a return by item.
	"""
	if not doc.get("return_against"):
		return REASON_ITEM_RETURN
	sold = _quantities_by_item(
		frappe.get_all(
			"Sales Invoice Item", filters={"parent": doc.return_against}, fields=["item_code", "stock_qty"]
		)
	)
	returned = _quantities_by_item(doc.get("items") or [])
	return REASON_TOTAL_RETURN if sold and returned == sold else REASON_ITEM_RETURN


def _quantities_by_item(rows) -> dict:
	totals = {}
	for row in rows:
		code = row.get("item_code")
		totals[code] = totals.get(code, 0) + abs(flt(row.get("stock_qty")))
	return {code: flt(qty, 6) for code, qty in totals.items() if qty}


def _series_options(doc) -> list[str]:
	letter = expected_series_letter(doc.pe_comprobante_type, doc.pe_original_type)
	return get_enabled_series(doc.company, doc.pe_comprobante_type, letter)


def _set_series(doc):
	series = normalize_series(doc.pe_series)
	if series and _series_left_from_previous_type(doc, series):
		series = ""  # pick again for the new type
	if not series:
		options = _series_options(doc)
		if len(options) == 1:
			series = options[0]
		elif doc.is_new():
			series = _series_of_repeated_invoice(doc, options)
	doc.pe_series = series or None
	if series:
		try:
			validate_issued_series(doc.pe_comprobante_type, series, doc.pe_original_type)
		except VoucherError as error:
			throw_voucher_error(error)


def _series_of_repeated_invoice(doc, options) -> str:
	"""An invoice made by Auto Repeat takes the series of the invoice it repeats.

	Auto Repeat copies the invoice without the fields that are not copied, the
	series among them, and can submit the copy at once: with several series to
	choose from, the submission failed and Auto Repeat switched itself off. The
	series is taken only while it is still one of the enabled ones for the type.
	"""
	if not doc.get("auto_repeat"):
		return ""
	reference = frappe.db.get_value(
		"Auto Repeat", doc.auto_repeat, ["reference_doctype", "reference_document"], as_dict=True
	)
	if not reference or reference.reference_doctype != doc.doctype:
		return ""
	series = frappe.db.get_value(doc.doctype, reference.reference_document, "pe_series")
	return series if series in options else ""


def _series_left_from_previous_type(doc, series) -> bool:
	"""True when the series is the one of the last save and no longer fits the new type.

	A draft first saved as a Boleta gets B001; switched to Factura, that series
	is replaced instead of refused. The same holds for a note whose modified
	comprobante type is corrected (FC01 -> BC01), and for an invoice that became
	a note. A series typed in the same save is checked as usual.
	"""
	if doc.is_new():
		return False
	before = doc.get_doc_before_save()
	if not before or _type_and_modified_type(before) == _type_and_modified_type(doc):
		return False
	if normalize_series(before.get("pe_series")) != series:
		return False
	return series not in _series_options(doc)


def _type_and_modified_type(doc) -> tuple:
	return (doc.get("pe_comprobante_type") or None, doc.get("pe_original_type") or None)


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


def _validate_igv_is_stated(doc):
	"""Once the company has IGV templates, an invoice must say how it is treated for IGV.

	ERPNext only pre-selects the default tax template in the browser. A document
	created through the API, an import or another app arrives with no tax rows
	and would otherwise be issued without IGV by omission. Exempt, unaffected
	and export sales state it with one of the 0% templates.
	"""
	if doc.get("taxes"):
		return
	has_igv_setup = frappe.db.exists(
		"Sales Taxes and Charges Template",
		{"company": doc.company, "disabled": 0, "pe_igv_affectation_type": ("is", "set")},
	)
	if not has_igv_setup:
		return
	frappe.throw(
		_(
			"This invoice has no IGV line. Select a tax template: IGV 18% for taxed sales, or one of the 0% templates for exempt, unaffected or export sales."
		),
		exc=ComprobanteError,
		title=_("IGV Not Stated"),
	)


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
	elif governing_type == TYPE_BOLETA:
		total = _total_in_soles(doc)
		if total > BOLETA_ID_THRESHOLD and not _identifies(identity_type, identity_number):
			frappe.throw(
				_(
					"A Boleta de venta above S/ {0} must identify the customer. Register the identity document (DNI, carnet de extranjería, passport...) of customer {1}."
				).format(f"{BOLETA_ID_THRESHOLD:,.2f}", frappe.bold(doc.customer)),
				exc=ComprobanteError,
				title=_("Customer Identity Required"),
			)


def _identifies(identity_type, identity_number) -> bool:
	"""True when the document names a buyer.

	Some systems register "clientes varios" with 00000000 or "-" as the number:
	that is allowed on a customer, but above S/ 700 the law asks for the buyer's
	own document, and no document is made of zeros and dashes only.
	"""
	number = (identity_number or "").strip()
	return bool(identity_type) and bool(number.strip("0-"))


def _total_in_soles(doc) -> float:
	"""The invoice total, IGV included, in soles, whatever currency the company keeps its books in.

	Notes have negative totals when they reduce the sale: the amount counts.
	"""
	if doc.get("currency") == SOLES:
		return abs(flt(doc.grand_total, 2))
	if _company_currency(doc.company) == SOLES:
		return abs(flt(doc.base_grand_total, 2))
	from erpnext.setup.utils import get_exchange_rate

	rate = flt(get_exchange_rate(doc.currency, SOLES, doc.posting_date, "for_selling"))
	if not rate:
		frappe.throw(
			_(
				"There is no exchange rate from {0} to PEN for {1}: it is needed to check the S/ 700 limit of the Boleta de venta. Register it in Currency Exchange."
			).format(doc.currency, frappe.format(doc.posting_date, "Date")),
			exc=ComprobanteError,
		)
	return abs(flt(flt(doc.grand_total) * rate, 2))


def _company_currency(company: str) -> str:
	return frappe.get_cached_value("Company", company, "default_currency")


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
