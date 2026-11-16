# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from erpnext_peru.overrides.common import is_peru_company, throw_voucher_error
from erpnext_peru.utils.voucher import (
	ISSUABLE_TYPES,
	MAX_NUMBER,
	VoucherError,
	format_voucher_number,
	normalize_series,
	validate_issued_series,
)


class SUNATVoucherSeries(Document):
	"""Running number of one series of comprobantes issued by a company.

	The number is advanced only by ``allocate_next_number`` while a Sales
	Invoice is being submitted, inside the same database transaction, so a
	failed submission never consumes a number.
	"""

	def autoname(self):
		self.series = normalize_series(self.series)
		if not (self.company and self.comprobante_type and self.series):
			frappe.throw(_("Company, Comprobante Type and Series are required"))
		self.name = f"{self.comprobante_type}-{self.series}-{self.company}"

	def validate(self):
		self.series = normalize_series(self.series)
		if not is_peru_company(self.company):
			frappe.throw(_("Company {0} is not a Peruvian company.").format(frappe.bold(self.company)))
		if self.comprobante_type not in ISSUABLE_TYPES:
			frappe.throw(
				_("Only comprobante types {0} can be issued from Sales Invoices.").format(
					", ".join(ISSUABLE_TYPES)
				)
			)
		try:
			validate_issued_series(self.comprobante_type, self.series)
		except VoucherError as error:
			throw_voucher_error(error)

		self.current_number = cint(self.current_number)
		if self.current_number < 0 or self.current_number > MAX_NUMBER:
			frappe.throw(_("Last Number Issued must be between 0 and {0}.").format(MAX_NUMBER))

		highest_used = get_highest_used_number(self.company, self.comprobante_type, self.series)
		if self.current_number < highest_used:
			frappe.throw(
				_(
					"Last Number Issued cannot be lower than {0}: voucher {1} has already been issued in this series."
				).format(highest_used, frappe.bold(format_voucher_number(self.series, highest_used)))
			)

	def on_trash(self):
		if get_highest_used_number(self.company, self.comprobante_type, self.series):
			frappe.throw(
				_(
					"Series {0} cannot be deleted because vouchers have been issued with it. Disable it instead."
				).format(frappe.bold(self.series))
			)


def get_highest_used_number(company: str, comprobante_type: str, series: str) -> int:
	"""Highest number carried by a submitted or cancelled Sales Invoice in the series."""
	result = frappe.db.sql(
		"""
		select max(pe_number) from `tabSales Invoice`
		where company = %s and pe_comprobante_type = %s and pe_series = %s and docstatus in (1, 2)
		""",
		(company, comprobante_type, series),
	)
	return cint(result[0][0]) if result else 0


def get_series_name(company: str, comprobante_type: str, series: str) -> str | None:
	return frappe.db.get_value(
		"SUNAT Voucher Series",
		{"company": company, "comprobante_type": comprobante_type, "series": series},
		"name",
	)


def get_enabled_series(company: str, comprobante_type: str, letter: str | None = None) -> list[str]:
	"""Enabled series codes for a company and type, optionally limited to F... or B..."""
	filters = {"company": company, "comprobante_type": comprobante_type, "enabled": 1}
	if letter:
		filters["series"] = ("like", f"{letter}%")
	return frappe.get_all("SUNAT Voucher Series", filters=filters, pluck="series", order_by="series asc")


def allocate_next_number(
	company: str, comprobante_type: str, series: str, for_document: str | None = None
) -> int:
	"""Lock the series row, advance its counter and return the allocated number.

	Must be called inside the transaction that submits the document: the row
	lock is held until that transaction commits or rolls back, which makes the
	numbering gapless and free of duplicates under concurrent submissions.
	"""
	name = get_series_name(company, comprobante_type, series)
	if not name:
		frappe.throw(
			_(
				"Series {0} is not registered for comprobante type {1} and company {2}. Create it in SUNAT Voucher Series."
			).format(frappe.bold(series), frappe.bold(comprobante_type), frappe.bold(company))
		)

	row = frappe.db.get_value(
		"SUNAT Voucher Series", name, ["current_number", "enabled"], as_dict=True, for_update=True
	)
	if not row or not cint(row.enabled):
		frappe.throw(_("Series {0} is disabled.").format(frappe.bold(series)))

	number = cint(row.current_number) + 1
	if number > MAX_NUMBER:
		frappe.throw(
			_("Series {0} has reached its last number. Register a new series.").format(frappe.bold(series))
		)

	# Defence in depth: the counter should make this impossible.
	filters = {
		"company": company,
		"pe_comprobante_type": comprobante_type,
		"pe_series": series,
		"pe_number": number,
		"docstatus": ("in", (1, 2)),
	}
	if for_document:
		filters["name"] = ("!=", for_document)
	duplicate = frappe.db.get_value("Sales Invoice", filters, "name")
	if duplicate:
		frappe.throw(
			_("Voucher {0} already exists ({1}). Review Last Number Issued of series {2}.").format(
				frappe.bold(format_voucher_number(series, number)), duplicate, frappe.bold(series)
			)
		)

	frappe.db.set_value("SUNAT Voucher Series", name, "current_number", number)
	return number
