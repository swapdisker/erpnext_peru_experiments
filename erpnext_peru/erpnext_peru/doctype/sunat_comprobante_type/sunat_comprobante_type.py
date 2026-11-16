# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_peru.utils.voucher import ISSUABLE_TYPES


class SUNATComprobanteType(Document):
	def validate(self):
		self.code = (self.code or "").strip().upper()
		self.description = (self.description or "").strip()
		if not self.code:
			frappe.throw(_("Code is required"))
		if self.sales_issuable and self.code not in ISSUABLE_TYPES:
			frappe.throw(
				_("Only comprobante types {0} can be issued from Sales Invoices.").format(
					", ".join(ISSUABLE_TYPES)
				)
			)
