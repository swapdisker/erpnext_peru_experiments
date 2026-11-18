# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""ERPNext's "Delete Company Transactions" tool and issued comprobantes.

The tool deletes with plain SQL, past the hook that keeps every issued voucher
on record (``sales_invoice.on_trash``), and also deletes the SUNAT Voucher
Series of the company. Afterwards a series could start again from 1 and hand
out numbers that SUNAT already has. So the tool is refused for a Peruvian
company that has issued any comprobante; companies that never issued one (a
test company, say) can still be emptied.
"""

import frappe
from frappe import _

from erpnext_peru.overrides.common import ComprobanteError, is_peru_company


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
