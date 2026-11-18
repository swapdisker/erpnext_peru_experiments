# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Load the Ubigeo master from ``data/ubigeo.csv`` (INEI codes, all districts).

The CSV is generated from the official sources by ``tools/ubigeo/build_ubigeo.py``.
It runs on every migrate and makes the table match the file:

- missing codes are inserted;
- names that differ are set back to the file's (the list is reference data:
  a rename by law reaches every site with the next release);
- codes the file no longer has are disabled, never deleted: addresses may use
  them, and the address form only offers enabled codes;
- a disabled code that is in the file is enabled again.
"""

import csv
import os

import frappe
from frappe.utils import now_datetime

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ubigeo.csv")
NAME_FIELDS = ("department", "province", "district")


def read_ubigeo_file(path: str = PATH) -> dict:
	with open(path, encoding="utf-8", newline="") as handle:
		return {row["code"]: tuple(row[f] for f in NAME_FIELDS) for row in csv.DictReader(handle)}


def full_name(department: str, province: str, district: str) -> str:
	# Same text as Ubigeo.validate builds.
	return f"{district}, {province}, {department}"


def load_ubigeo(path: str = PATH) -> dict:
	"""Make the Ubigeo table match the file. Returns what was done, by count."""
	official = read_ubigeo_file(path)
	existing = {
		row.name: row
		for row in frappe.get_all("Ubigeo", fields=["name", *NAME_FIELDS, "enabled"], limit_page_length=0)
	}
	counts = {"inserted": 0, "updated": 0, "disabled": 0, "enabled": 0}

	missing = [code for code in official if code not in existing]
	if missing:
		now = now_datetime()
		user = frappe.session.user or "Administrator"
		fields = [
			"name",
			"code",
			*NAME_FIELDS,
			"full_name",
			"enabled",
			"owner",
			"modified_by",
			"creation",
			"modified",
		]
		values = [
			(code, code, *official[code], full_name(*official[code]), 1, user, user, now, now)
			for code in sorted(missing)
		]
		frappe.db.bulk_insert("Ubigeo", fields, values)
		counts["inserted"] = len(values)

	for code, row in existing.items():
		if code in official:
			names = official[code]
			changes = {}
			if tuple(row.get(f) for f in NAME_FIELDS) != names:
				changes.update(dict(zip(NAME_FIELDS, names, strict=True)), full_name=full_name(*names))
				counts["updated"] += 1
			if not row.enabled:
				changes["enabled"] = 1
				counts["enabled"] += 1
			if changes:
				frappe.db.set_value("Ubigeo", code, changes)
		elif row.enabled:
			frappe.db.set_value("Ubigeo", code, "enabled", 0)
			counts["disabled"] += 1

	if any(counts.values()):
		print(f"Ubigeo: {counts}")
	return counts
