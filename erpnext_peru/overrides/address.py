# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _

from erpnext_peru.overrides.common import PERU


def validate(doc, method=None):
	"""Fill district / province / department from the Ubigeo; warn when it is missing.

	The warning appears only once the Ubigeo list has been loaded.
	"""
	ubigeo = doc.get("pe_ubigeo")
	if ubigeo:
		row = frappe.db.get_value(
			"Ubigeo", ubigeo, ["district", "province", "department", "enabled"], as_dict=True
		)
		if row and not row.enabled:
			frappe.msgprint(
				_("Ubigeo {0} is no longer in INEI's list. Choose the current code of the district.").format(
					frappe.bold(ubigeo)
				),
				indicator="orange",
				alert=True,
			)
		if row:
			# Only fill blanks: never overwrite what the user typed.
			if not doc.city:
				doc.city = row.district
			if not doc.county:
				doc.county = row.province
			if not doc.state:
				doc.state = row.department
		return
	# Until the Ubigeo list is loaded nobody can fill the field: a warning on
	# every save would only teach users to ignore warnings.
	if doc.country == PERU and frappe.db.exists("Ubigeo", {}):
		frappe.msgprint(
			_("This address has no Ubigeo. The Ubigeo is mandatory for electronic invoicing."),
			indicator="orange",
			alert=True,
		)
