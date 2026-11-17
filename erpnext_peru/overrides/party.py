# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Identity document of Customers and Suppliers (SUNAT Catálogo N.° 06)."""

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from erpnext_peru.overrides.common import (
	DuplicateIdentityError,
	IdentityDocumentError,
	check_catalogue_entry,
	throw_identity_error,
)
from erpnext_peru.utils.identity import (
	IdentityError,
	normalize_identity_number,
	validate_identity_number,
)

IDENTITY_TYPE_DOCTYPE = "SUNAT Identity Document Type"


def validate(doc, method=None):
	"""Customer / Supplier ``validate`` hook.

	Nothing is required of parties that carry no identity document, so the
	hook is inert on sites or parties that do not use the Peruvian fields.
	"""
	identity_type = (doc.get("pe_identity_type") or "").strip()
	number = normalize_identity_number(doc.get("pe_identity_number"))

	if not identity_type and not number:
		doc.pe_identity_type = None
		doc.pe_identity_number = None
		_clear_tax_id_copied_from_identity(doc)
		return
	if not identity_type:
		frappe.throw(
			_("Select the identity document type for number {0}.").format(frappe.bold(number)),
			exc=IdentityDocumentError,
		)
	if not number:
		frappe.throw(_("Enter the identity document number."), exc=IdentityDocumentError)

	check_catalogue_entry(
		IDENTITY_TYPE_DOCTYPE, identity_type, _("Identity Document Type"), exc=IdentityDocumentError
	)
	try:
		number = validate_identity_number(identity_type, number)
	except IdentityError as error:
		throw_identity_error(error)

	doc.pe_identity_type = identity_type
	doc.pe_identity_number = number
	_check_duplicate(doc)
	# ERPNext prints and reports the party's Tax ID; keep it in step.
	doc.tax_id = number


def _clear_tax_id_copied_from_identity(doc):
	"""Removing the identity document also removes the Tax ID this hook copied from it.

	A Tax ID that differs from the old document number was entered separately
	and is kept.
	"""
	before = doc.get_doc_before_save() if not doc.is_new() else None
	old_number = before and before.get("pe_identity_number")
	if old_number and doc.get("tax_id") == old_number:
		doc.tax_id = None


def _check_duplicate(doc):
	"""The same document may not be registered twice within Customers (or within Suppliers).

	The same RUC may exist once as a Customer and once as a Supplier.
	"""
	filters = {
		"pe_identity_type": doc.pe_identity_type,
		"pe_identity_number": doc.pe_identity_number,
	}
	if doc.name:
		filters["name"] = ("!=", doc.name)
	existing = frappe.db.get_value(doc.doctype, filters, "name")
	if existing:
		frappe.throw(
			_(
				"{0} {1} already has identity document {2}. Use the existing record instead of creating a new one."
			).format(
				_(doc.doctype), get_link_to_form(doc.doctype, existing), frappe.bold(doc.pe_identity_number)
			),
			exc=DuplicateIdentityError,
			title=_("Duplicate Identity Document"),
		)
