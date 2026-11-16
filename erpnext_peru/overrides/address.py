# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _

from erpnext_peru.overrides.common import PERU


def validate(doc, method=None):
	"""Fill district / province / department from the Ubigeo; warn when it is missing."""
	ubigeo = doc.get("pe_ubigeo")
	if ubigeo:
		row = frappe.db.get_value("Ubigeo", ubigeo, ["district", "province", "department"], as_dict=True)
		if row:
			# Only fill blanks: never overwrite what the user typed.
			if not doc.city:
				doc.city = row.district
			if not doc.county:
				doc.county = row.province
			if not doc.state:
				doc.state = row.department
		return
	if doc.country == PERU:
		frappe.msgprint(
			_("This address has no Ubigeo. The Ubigeo is mandatory for electronic invoicing."),
			indicator="orange",
			alert=True,
		)
