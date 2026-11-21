# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _

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
	_check_series_not_shared(doc)


def _check_series_not_shared(doc):
	"""A RUC given to a second company must not bring a series the other company uses."""
	from erpnext_peru.erpnext_peru.doctype.sunat_voucher_series.sunat_voucher_series import (
		series_shared_with_same_ruc,
	)

	if doc.is_new():
		return
	own = frappe.get_all(
		"SUNAT Voucher Series", filters={"company": doc.name}, fields=["comprobante_type", "series"]
	)
	pairs = [(row.comprobante_type, row.series) for row in own]
	shared = series_shared_with_same_ruc(doc.name, pairs, ruc=doc.tax_id)
	if shared:
		frappe.throw(
			_(
				"Company {0} has the same RUC and uses series {1} as well: SUNAT identifies a comprobante by the RUC, the type, the series and the number, so the two companies would issue the same vouchers."
			).format(frappe.bold(shared[0].company), frappe.bold(shared[0].series)),
			frappe.DuplicateEntryError,
		)


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
