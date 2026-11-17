# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Plan Contable General Empresarial (PCGE) Modificado 2019 as data.

Free of Frappe imports so it can be unit-tested on its own.

The catalogue (``data/pcge_2019.csv``) is the one published by the MEF; see
``data/pcge_2019_notes.json`` for the source and for the misprints that were
corrected. This module adds what ERPNext needs on top of it: the element
roots, which accounts are groups, and a root type / account type for each.

The root types and account types are a mapping chosen for ERPNext. They are
NOT part of the PCGE and must be confirmed by the company's accountant.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from erpnext_peru.utils.errors import CodedError

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CATALOGUE_FILE = os.path.join(DATA_DIR, "pcge_2019.csv")

# Element -> (name, ERPNext root type). Names as in the MEF document.
ELEMENTS: dict[str, tuple[str, str]] = {
	"0": ("Cuentas de orden", "Asset"),
	"1": ("Activo disponible y exigible", "Asset"),
	"2": ("Activo realizable", "Asset"),
	"3": ("Activo inmovilizado", "Asset"),
	"4": ("Pasivo", "Liability"),
	"5": ("Patrimonio neto", "Equity"),
	"6": ("Gastos por naturaleza", "Expense"),
	"7": ("Ingresos", "Income"),
	"8": ("Saldos intermediarios de gestión y determinación del resultado del periodo", "Expense"),
	"9": ("Contabilidad analítica de explotación: costos de producción y gastos por función", "Expense"),
}

BALANCE_SHEET_ROOT_TYPES = ("Asset", "Liability", "Equity")

# Account types by code prefix (the longest matching prefix wins). Kept to the
# minimum ERPNext needs to issue and pay invoices. In particular, inventory
# (20-28) and fixed assets (33, 39) are deliberately left without a type:
# typing them switches on ERPNext's stock and asset rules, which is a decision
# for whoever designs those processes.
ACCOUNT_TYPES: dict[str, str] = {
	"101": "Cash",
	"102": "Cash",
	"104": "Bank",
	"106": "Bank",
	"121": "Receivable",
	"123": "Receivable",
	"131": "Receivable",
	"133": "Receivable",
	"4011": "Tax",
	"421": "Payable",
	"423": "Payable",
	"424": "Payable",
	"431": "Payable",
	"433": "Payable",
	"434": "Payable",
	"69": "Cost of Goods Sold",
	"70": "Income Account",
}

MIN_CODE_LENGTH = 2
MAX_CODE_LENGTH = 10


class PcgeError(CodedError):
	"""Raised when a catalogue or a client account code is not valid."""


@dataclass(frozen=True)
class PcgeAccount:
	code: str
	name: str
	is_group: bool

	@property
	def element(self) -> str:
		return self.code[0]

	@property
	def parent_code(self) -> str:
		"""Code of the account above. For a two-digit cuenta it is the element digit."""
		return self.code[:-1]

	@property
	def is_element_root(self) -> bool:
		return len(self.code) == 1

	@property
	def root_type(self) -> str:
		return root_type_for(self.code)

	@property
	def report_type(self) -> str:
		return report_type_for(self.code)

	@property
	def account_type(self) -> str:
		return account_type_for(self.code)


def root_type_for(code: str) -> str:
	return ELEMENTS[code[0]][1]


def report_type_for(code: str) -> str:
	return "Balance Sheet" if root_type_for(code) in BALANCE_SHEET_ROOT_TYPES else "Profit and Loss"


def account_type_for(code: str) -> str:
	"""Account type of the longest prefix listed in ACCOUNT_TYPES, or ''."""
	for length in range(len(code), 0, -1):
		account_type = ACCOUNT_TYPES.get(code[:length])
		if account_type:
			return account_type
	return ""


def read_catalogue_rows(path: str = CATALOGUE_FILE) -> list[tuple[str, str]]:
	with open(path, encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		return [(row["code"].strip(), row["name"].strip()) for row in reader]


def load_catalogue(path: str = CATALOGUE_FILE) -> list[PcgeAccount]:
	"""Element roots followed by every catalogue account, parents before children.

	Raises PcgeError if the file is not a well-formed tree, so a damaged data
	file can never be applied to a company.
	"""
	rows = read_catalogue_rows(path)
	codes = [code for code, _ in rows]
	known = set(codes)

	if len(known) != len(codes):
		repeated = sorted({code for code in codes if codes.count(code) > 1})
		raise PcgeError("duplicate_codes", "Catalogue has repeated codes", codes=repeated)
	for code, name in rows:
		if not (code.isascii() and code.isdigit()) or len(code) < MIN_CODE_LENGTH:
			raise PcgeError("bad_code", "Catalogue code is not valid", account=code)
		if not name:
			raise PcgeError("empty_name", "Catalogue account has no name", account=code)
		if code[0] not in ELEMENTS:
			raise PcgeError("bad_element", "Catalogue code has an unknown element", account=code)
		if len(code) > MIN_CODE_LENGTH and code[:-1] not in known:
			raise PcgeError("orphan", "Catalogue account has no parent", account=code)

	parents = {code[:-1] for code in codes}
	accounts = [
		PcgeAccount(code=digit, name=name, is_group=True) for digit, (name, _) in sorted(ELEMENTS.items())
	]
	accounts += [PcgeAccount(code=code, name=name, is_group=code in parents) for code, name in sorted(rows)]
	return accounts


def validate_client_code(code) -> str:
	"""Check that an account code of the company's own chart fits the PCGE structure.

	Returns the code normalized. The PCGE fixes the first two digits (elemento
	and cuenta); below that every entity may add its own sub-accounts.
	"""
	value = "" if code is None else str(code).strip()
	if not value:
		raise PcgeError("code_missing", "Account code is required")
	if not (value.isascii() and value.isdigit()):
		raise PcgeError("code_not_numeric", "Account code must contain digits only", account=value)
	if len(value) < MIN_CODE_LENGTH:
		raise PcgeError("code_too_short", "Account code must have at least two digits", account=value)
	if len(value) > MAX_CODE_LENGTH:
		raise PcgeError("code_too_long", "Account code is too long", account=value)
	return value
