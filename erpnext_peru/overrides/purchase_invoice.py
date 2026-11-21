# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Comprobante de pago received from a supplier (Purchase Invoices of Peruvian companies).

The comprobante type, series and number are those printed on the supplier's
document. They are optional at this stage (the purchase register will make
them mandatory), but whatever is entered is validated and the same supplier
document cannot be registered twice.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_link_to_form

from erpnext_peru.erpnext_peru.doctype.sunat_voucher_series.sunat_voucher_series import (
	_is_concurrent_change,
	_locking_read_sees_latest,
)
from erpnext_peru.overrides.common import (
	COMPROBANTE_TYPE_DOCTYPE,
	ComprobanteError,
	DuplicateVoucherError,
	check_catalogue_entry,
	is_peru_invoice,
	throw_voucher_error,
)
from erpnext_peru.utils.voucher import (
	ISSUABLE_TYPES,
	NOTE_TYPES,
	TYPE_CREDIT_NOTE,
	VoucherError,
	join_received_voucher,
	normalize_series,
	normalize_voucher_number,
	validate_received_voucher,
)


def applies_to(doc) -> bool:
	return is_peru_invoice(doc)


def validate(doc, method=None):
	if not applies_to(doc):
		return

	comprobante_type = (doc.get("pe_comprobante_type") or "").strip()
	series = normalize_series(doc.get("pe_series"))
	number = normalize_series(doc.get("pe_number"))

	if not comprobante_type and cint(doc.is_return) and (series or number):
		comprobante_type = TYPE_CREDIT_NOTE

	if not comprobante_type:
		if series or number:
			frappe.throw(
				_("Select the comprobante type of the supplier's document {0}.").format(
					frappe.bold(join_received_voucher(series, number))
				),
				exc=ComprobanteError,
			)
		_clear(doc)
		_sync_bill_no(doc)
		return

	check_catalogue_entry(COMPROBANTE_TYPE_DOCTYPE, comprobante_type, _("Comprobante Type"))
	if cint(doc.is_return) and comprobante_type != TYPE_CREDIT_NOTE:
		frappe.throw(
			_("A purchase return must be registered with comprobante type 07 - Nota de crédito."),
			exc=ComprobanteError,
		)
	if comprobante_type == TYPE_CREDIT_NOTE and not cint(doc.is_return):
		frappe.throw(
			_(
				"A supplier's credit note (type 07) must be registered as a return: tick 'Is Return (Debit Note)'."
			),
			exc=ComprobanteError,
		)

	try:
		series, number = validate_received_voucher(comprobante_type, series, number)
	except VoucherError as error:
		throw_voucher_error(error)

	doc.pe_comprobante_type = comprobante_type
	doc.pe_series = series or None
	doc.pe_number = number
	doc.pe_voucher_number = join_received_voucher(series, number)

	_set_original_reference(doc)
	_check_duplicate(doc)
	_sync_bill_no(doc)


def before_submit(doc, method=None):
	if not applies_to(doc):
		return
	if doc.get("pe_comprobante_type") in NOTE_TYPES and not (
		doc.get("pe_original_type") and doc.get("pe_original_voucher_number")
	):
		frappe.throw(
			_(
				"Indicate the comprobante this note modifies: its type and its number (for example F001-00000123)."
			),
			exc=ComprobanteError,
		)


def _sync_bill_no(doc):
	"""Keep ERPNext's Supplier Invoice No in step with the supplier's document.

	It is filled in when empty, and follows a corrected (or removed) number while
	it still holds the number copied here before. A Supplier Invoice No typed
	separately is kept.
	"""
	current = (doc.get("bill_no") or "").strip()
	before = None if doc.is_new() else doc.get_doc_before_save()
	previous = before.get("pe_voucher_number") if before else None
	if not current or (previous and current == previous):
		doc.bill_no = doc.pe_voucher_number


def _clear(doc):
	doc.pe_comprobante_type = None
	doc.pe_series = None
	doc.pe_number = None
	doc.pe_voucher_number = None
	doc.pe_original_type = None
	doc.pe_original_voucher_number = None


def _set_original_reference(doc):
	if doc.pe_comprobante_type not in NOTE_TYPES:
		doc.pe_original_type = None
		doc.pe_original_voucher_number = None
		return

	if doc.get("return_against"):
		original = frappe.db.get_value(
			"Purchase Invoice",
			doc.return_against,
			["pe_comprobante_type", "pe_voucher_number"],
			as_dict=True,
		)
		if original and original.pe_comprobante_type and original.pe_voucher_number:
			doc.pe_original_type = original.pe_comprobante_type
			doc.pe_original_voucher_number = original.pe_voucher_number

	if doc.pe_original_type:
		check_catalogue_entry(COMPROBANTE_TYPE_DOCTYPE, doc.pe_original_type, _("Modified Comprobante Type"))

	text = normalize_series(doc.pe_original_voucher_number)
	if text and doc.pe_original_type in ISSUABLE_TYPES:
		try:
			text = normalize_voucher_number(text)
		except VoucherError as error:
			throw_voucher_error(error)
	doc.pe_original_voucher_number = text or None


def _check_duplicate(doc):
	"""The same supplier document must not be booked twice in a company.

	Two users registering it at the same moment would both find nothing and
	both book its IGV credit. So the documents of one supplier are checked one
	at a time: the supplier's row is locked until the transaction ends, and the
	check is a locking read, which sees what the previous registration committed.
	"""
	filters = {
		"company": doc.company,
		"supplier": doc.supplier,
		"pe_comprobante_type": doc.pe_comprobante_type,
		"pe_voucher_number": doc.pe_voucher_number,
		"docstatus": ("<", 2),
	}
	if doc.name:
		filters["name"] = ("!=", doc.name)
	with _locking_read_sees_latest():
		try:
			frappe.db.sql("select name from `tabSupplier` where name = %s for update", (doc.supplier,))
			existing = frappe.db.get_value("Purchase Invoice", filters, "name", for_update=True)
		except Exception as error:
			if not _is_concurrent_change(error):
				raise
			frappe.throw(
				_(
					"Another document of supplier {0} was being registered at the same moment. Save this one again."
				).format(frappe.bold(doc.supplier)),
				exc=ComprobanteError,
			)
	if existing:
		frappe.throw(
			_("Comprobante {0} of supplier {1} is already registered in {2}.").format(
				frappe.bold(doc.pe_voucher_number),
				frappe.bold(doc.supplier),
				get_link_to_form("Purchase Invoice", existing),
			),
			exc=DuplicateVoucherError,
			title=_("Duplicate Comprobante"),
		)
