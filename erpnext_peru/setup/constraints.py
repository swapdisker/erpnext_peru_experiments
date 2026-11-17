# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Unique indexes that back up the application's own duplicate checks.

The hooks already refuse a second customer with the same identity document and
never hand out a voucher number twice. These indexes make the database refuse
it too, so that a future bug, a script that writes directly or two users in the
same instant cannot store a duplicate.

Columns that are empty hold NULL, and MariaDB allows any number of NULLs in a
unique index: drafts, parties without a document and invoices of other
countries are not affected.

``ensure_constraints`` runs on install and on every migrate. When the data
already contains duplicates the index cannot be created: it is skipped, the
duplicates are listed in the migrate output and in the Error Log, and the next
migrate tries again once they have been resolved. The migrate itself does not
fail, because stopping a site's upgrade over old data would be worse.
"""

import frappe

# (doctype, index name, columns): the most selective column first.
CONSTRAINTS = (
	("Sales Invoice", "pe_unique_voucher", ("pe_voucher_number", "pe_comprobante_type", "company")),
	("Customer", "pe_unique_identity", ("pe_identity_number", "pe_identity_type")),
	("Supplier", "pe_unique_identity", ("pe_identity_number", "pe_identity_type")),
)

# How many duplicate groups to show; the rest are counted.
SHOWN_DUPLICATES = 20


def ensure_constraints() -> dict[str, str]:
	"""Create the missing unique indexes. Returns {"doctype": "exists" | "created" | "duplicates"}."""
	return {doctype: ensure_constraint(doctype, name, columns) for doctype, name, columns in CONSTRAINTS}


def ensure_constraint(doctype: str, index_name: str, columns: tuple[str, ...]) -> str:
	table = f"tab{doctype}"
	if _has_index(table, index_name):
		return "exists"

	_empty_strings_to_null(table, columns)
	duplicates = find_duplicates(doctype, columns)
	if duplicates:
		_report(doctype, columns, duplicates)
		return "duplicates"

	# sql_ddl commits first: ALTER TABLE ends the transaction in MariaDB anyway.
	frappe.db.sql_ddl(
		f"ALTER TABLE `{table}` ADD UNIQUE INDEX `{index_name}` ({', '.join(f'`{c}`' for c in columns)})"
	)
	return "created"


def find_duplicates(doctype: str, columns: tuple[str, ...]) -> list[dict]:
	"""Groups of rows that share all ``columns``, none of them NULL."""
	select = ", ".join(f"`{c}`" for c in columns)
	not_null = " AND ".join(f"`{c}` IS NOT NULL" for c in columns)
	return frappe.db.sql(
		f"""SELECT {select}, COUNT(*) AS count, GROUP_CONCAT(name ORDER BY name SEPARATOR ', ') AS names
		FROM `tab{doctype}` WHERE {not_null}
		GROUP BY {select} HAVING COUNT(*) > 1 ORDER BY {select}""",
		as_dict=True,
	)


def _has_index(table: str, index_name: str) -> bool:
	# SHOW INDEX looks at this site's database only (information_schema would
	# also see the other sites of a shared database server).
	return bool(frappe.db.sql(f"SHOW INDEX FROM `{table}` WHERE Key_name = %s", (index_name,)))


def _empty_strings_to_null(table: str, columns: tuple[str, ...]):
	"""The hooks store empty as NULL; rows written around them may hold ''."""
	for column in columns:
		frappe.db.sql(f"UPDATE `{table}` SET `{column}` = NULL WHERE `{column}` = ''")


def _report(doctype: str, columns: tuple[str, ...], duplicates: list[dict]):
	lines = [
		", ".join(f"{column}={row[column]}" for column in columns) + f": {row['names']}"
		for row in duplicates[:SHOWN_DUPLICATES]
	]
	if len(duplicates) > SHOWN_DUPLICATES:
		lines.append(f"... and {len(duplicates) - SHOWN_DUPLICATES} more")
	message = (
		f"erpnext_peru: the unique index on {doctype} ({', '.join(columns)}) was NOT created because "
		f"these records share the same values. Correct them and run bench migrate again; until then "
		f"only the application's own check prevents new duplicates.\n" + "\n".join(lines)
	)
	print(message)
	frappe.log_error(title=f"erpnext_peru: duplicates block the unique index on {doctype}", message=message)
