# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

_CODE_RE = re.compile(r"^[0-9]{6}$")


class Ubigeo(Document):
	def validate(self):
		self.code = (self.code or "").strip()
		if not _CODE_RE.match(self.code):
			frappe.throw(_("Ubigeo code {0} is not valid: it must have exactly 6 digits.").format(self.code))
		for fieldname in ("department", "province", "district"):
			self.set(fieldname, " ".join((self.get(fieldname) or "").split()))
		self.full_name = f"{self.district}, {self.province}, {self.department}"
