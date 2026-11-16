# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Loader for the Ubigeo master.

The district list is NOT shipped with the app yet: it has to come from the
official INEI / SUNAT publication and be verified before it is committed.
Until then, load it on a site with::

    bench --site <site> execute erpnext_peru.setup.ubigeo.import_csv --kwargs "{'path': '/path/ubigeo.csv'}"

The CSV needs a header row with the columns ``code``, ``department``,
``province`` and ``district`` (UTF-8, comma separated).
"""

import csv

import frappe
from frappe import _

REQUIRED_COLUMNS = ("code", "department", "province", "district")


def import_csv(path: str, update: bool = False) -> dict:
	"""Insert (and optionally update) Ubigeo records from a CSV file.

	The whole file is validated before anything is written. Returns the counts
	``{"inserted": n, "updated": n, "unchanged": n}``.
	"""
	with open(path, encoding="utf-8-sig", newline="") as handle:
		reader = csv.DictReader(handle)
		missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
		if missing:
			frappe.throw(_("The Ubigeo file is missing the columns: {0}").format(", ".join(missing)))
		# collapse runs of whitespace, as the Ubigeo document does on save
		rows = [
			{column: " ".join((row.get(column) or "").split()) for column in REQUIRED_COLUMNS}
			for row in reader
		]

	errors = []
	seen = set()
	for line, row in enumerate(rows, start=2):
		code = row["code"]
		if not (len(code) == 6 and code.isascii() and code.isdigit()):
			errors.append(_("Line {0}: code {1} must have exactly 6 digits").format(line, code or "-"))
		elif code in seen:
			errors.append(_("Line {0}: code {1} is repeated").format(line, code))
		seen.add(code)
		for column in ("department", "province", "district"):
			if not row[column]:
				errors.append(_("Line {0}: {1} is empty").format(line, column))
	if errors:
		frappe.throw("<br>".join(errors[:50]), title=_("Ubigeo file has errors"))

	counts = {"inserted": 0, "updated": 0, "unchanged": 0}
	for row in rows:
		if frappe.db.exists("Ubigeo", row["code"]):
			doc = frappe.get_doc("Ubigeo", row["code"])
			changed = any(doc.get(column) != row[column] for column in ("department", "province", "district"))
			if changed and update:
				doc.update({c: row[c] for c in ("department", "province", "district")})
				doc.save(ignore_permissions=True)
				counts["updated"] += 1
			else:
				counts["unchanged"] += 1
		else:
			frappe.get_doc({"doctype": "Ubigeo", **row}).insert(ignore_permissions=True)
			counts["inserted"] += 1
	return counts
