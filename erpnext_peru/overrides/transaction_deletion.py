# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""ERPNext's "Delete Company Transactions" tool and issued comprobantes.

The tool deletes with plain SQL, past the hook that keeps every issued voucher
on record (``sales_invoice.on_trash``). Afterwards the vouchers SUNAT already
has would be gone from the books. So the tool is refused for a Peruvian
company that has issued any comprobante; companies that never issued one (a
test company, say) can still be emptied.

The check runs when the deletion is submitted and again whenever the submitted
record is saved: ERPNext's "Retry" of a failed deletion does that, calling the
record's own checks directly and not this hook, and it may come long after
comprobantes were issued.

The SUNAT Voucher Series themselves are never deleted with the transactions
(``company_data_to_be_ignored`` in hooks.py): a series carries its last number,
which may continue the numbering of a previous system even before the first
voucher is issued here.
"""

import frappe
from frappe import _

from erpnext_peru.overrides.common import ComprobanteError, is_peru_company

SERIES_DOCTYPE = "SUNAT Voucher Series"


def before_submit(doc, method=None):
	company = doc.get("company")
	if not is_peru_company(company):
		return
	issued = frappe.db.count("Sales Invoice", {"company": company, "pe_voucher_number": ("is", "set")})
	if issued:
		frappe.throw(
			_(
				"The transactions of {0} cannot be deleted: {1} comprobantes have been issued with their numbers, and they must remain on record."
			).format(frappe.bold(company), issued),
			exc=ComprobanteError,
			title=_("Comprobantes Issued"),
		)
	if any(row.get("doctype_name") == SERIES_DOCTYPE for row in doc.get("doctypes_to_delete") or []):
		frappe.throw(
			_(
				"{0} is not deleted with the transactions: each series keeps its last number issued. Remove it from DocTypes To Delete."
			).format(_(SERIES_DOCTYPE)),
			exc=ComprobanteError,
		)
