# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe

from erpnext_peru.overrides.common import PERU, throw_identity_error
from erpnext_peru.utils.identity import IdentityError, validate_ruc


def validate(doc, method=None):
	"""A Peruvian company's Tax ID, when filled in, must be a valid RUC."""
	if doc.country != PERU or not (doc.tax_id or "").strip():
		return
	try:
		doc.tax_id = validate_ruc(doc.tax_id)
	except IdentityError as error:
		throw_identity_error(error)


def on_update(doc, method=None):
	"""Keep ERPNext's 16% "Peru Tax" templates disabled once IGV is set up.

	ERPNext creates them again when a company's country changes, or when the
	company is saved while it has no accounts, if they no longer exist (replacing
	the chart deletes them). Before the IGV setup they are left alone.
	"""
	from erpnext_peru.accounts.igv import CATEGORY_GRAVADO, disable_erpnext_default_templates

	if doc.country != PERU:
		return
	if not frappe.db.exists("Tax Rule", {"company": doc.name, "tax_category": CATEGORY_GRAVADO}):
		return
	disable_erpnext_default_templates(doc.name, doc.abbr)
