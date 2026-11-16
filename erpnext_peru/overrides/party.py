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
		return
	if not identity_type:
		frappe.throw(
			_("Select the identity document type for number {0}.").format(frappe.bold(number)),
			exc=IdentityDocumentError,
		)
	if not number:
		frappe.throw(_("Enter the identity document number."), exc=IdentityDocumentError)

	check_catalogue_entry(IDENTITY_TYPE_DOCTYPE, identity_type, _("Identity Document Type"))
	try:
		number = validate_identity_number(identity_type, number)
	except IdentityError as error:
		throw_identity_error(error)

	doc.pe_identity_type = identity_type
	doc.pe_identity_number = number
	_check_duplicate(doc)
	# ERPNext prints and reports the party's Tax ID; keep it in step.
	doc.tax_id = number


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
