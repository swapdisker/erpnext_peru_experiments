# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SUNATDebitNoteReason(Document):
	def validate(self):
		self.code = (self.code or "").strip().upper()
		self.description = (self.description or "").strip()
		if not self.code:
			frappe.throw(_("Code is required"))
