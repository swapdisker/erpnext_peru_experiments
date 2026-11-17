# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Apply the PCGE Modificado 2019 to a company's chart of accounts.

Two entry points:

* ``apply_pcge`` creates the catalogue accounts that the company does not have
  yet. It never deletes, renames or re-types an existing account, so it can be
  run again at any time (running it twice creates nothing the second time).
  With ``replace_existing`` it first removes the company's current chart, which
  ERPNext only allows while the company has no ledger entries.
* ``import_client_accounts`` adds the company's own sub-accounts (for example
  the bank accounts under 1041) below the right PCGE account.

Both accept ``dry_run=True`` and return a report of what was or would be done.
"""

import unicodedata
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils.nestedset import rebuild_tree

from erpnext_peru.overrides.common import PeruValidationError, is_peru_company
from erpnext_peru.utils.pcge import (
	ELEMENTS,
	PcgeAccount,
	PcgeError,
	account_type_for,
	load_catalogue,
	report_type_for,
	root_type_for,
	validate_client_code,
)

# Company default -> PCGE account. Only what an invoice needs. Everything else
# (cost of sales, inventory, rounding, exchange differences...) depends on how
# the accountant wants those processes booked and is left empty on purpose.
COMPANY_DEFAULTS = {
	"default_receivable_account": "1212",
	"default_payable_account": "4212",
	"default_income_account": "70121",
	# ERPNext refuses to submit any invoice unless the company has a round-off
	# account, even when nothing is rounded. 7599 (Otros ingresos de gestión) is
	# a PROVISIONAL choice so that the company is usable; see PROVISIONAL_DEFAULTS.
	"round_off_account": "7599",
}
# Set so that ERPNext works, but the account is the accountant's call.
PROVISIONAL_DEFAULTS = ("round_off_account",)
# Cash and bank are not defaulted either: every company opens its own accounts
# under 101 and 1041, and ERPNext does not let an account that is a company
# default become the group of those sub-accounts.
DEFAULTS_LEFT_TO_THE_ACCOUNTANT = (
	"default_cash_account",
	"default_bank_account",
	"default_expense_account",
	"exchange_gain_loss_account",
	"default_inventory_account",
	"stock_received_but_not_billed",
	"stock_adjustment_account",
)


class PcgeApplyError(PeruValidationError):
	pass


# One change to a chart of accounts at a time on a site. Creating accounts ends
# with rebuilding the account tree of every company (as ERPNext does), and two
# rebuilds at the same moment can deadlock or, on MariaDB before 11.6, leave
# the tree's internal numbering inconsistent.
CHART_LOCK = "erpnext_peru_chart"
CHART_LOCK_WAIT = 120  # seconds


@contextmanager
def chart_lock():
	"""Hold a database-wide named lock for this site while a chart is changed.

	MariaDB's GET_LOCK works across processes and servers that share the
	database, and is released if the connection dies. Users creating single
	accounts by hand do not take it; ERPNext locks those itself.

	If nothing has been written in the current transaction yet, it is
	committed after the lock is taken: reads then start from a fresh snapshot
	and see what the previous holder of the lock committed.
	"""
	if frappe.db.db_type != "mariadb":  # pragma: no cover - the app targets MariaDB
		yield
		return
	name = f"{frappe.conf.db_name}:{CHART_LOCK}"
	if frappe.db.sql("SELECT GET_LOCK(%s, %s)", (name, CHART_LOCK_WAIT))[0][0] != 1:
		frappe.throw(
			_("Another chart of accounts is being changed on this site. Try again in a few minutes."),
			exc=PcgeApplyError,
		)
	try:
		if not frappe.db.transaction_writes:
			frappe.db.commit()  # nosemgrep: nothing written yet; only renews the snapshot
		yield
	finally:
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (name,))


def _normalize(text: str) -> str:
	text = unicodedata.normalize("NFKD", (text or "").casefold())
	text = "".join(char for char in text if not unicodedata.combining(char))
	return " ".join(text.replace("–", "-").split())


def _existing_accounts(company: str) -> dict[str, frappe._dict]:
	"""Company accounts that carry an account number, keyed by that number."""
	rows = frappe.get_all(
		"Account",
		# "is set", not ("not in", ("", None)): Frappe v16 turns the latter into SQL
		# that matches nothing, and every account would look missing.
		filters={"company": company, "account_number": ("is", "set")},
		fields=["name", "account_name", "account_number", "is_group", "root_type", "parent_account"],
	)
	return {row.account_number.strip(): row for row in rows}


def _has_ledger_entries(account: str) -> bool:
	return bool(frappe.db.exists("GL Entry", {"account": account}))


def _default_using(company: str, account: str) -> str | None:
	"""Label of the Company default that points at ``account``, if any.

	ERPNext refuses to turn such an account into a group.
	"""
	meta = frappe.get_meta("Company")
	fields = [df for df in meta.fields if df.fieldtype == "Link" and df.options == "Account"]
	if not fields:
		return None
	values = frappe.db.get_value("Company", company, [df.fieldname for df in fields], as_dict=True) or {}
	for df in fields:
		if values.get(df.fieldname) == account:
			return df.label
	return None


def _why_not_a_group(company: str, row) -> tuple[str, str] | None:
	"""(reason, detail) when an existing ledger cannot become a group; None when it can."""
	if row.get("simulated"):
		return None
	if _has_ledger_entries(row.name):
		return (
			"ledger_with_entries",
			_("Account {0} already has ledger entries, so sub-accounts cannot be created under it.").format(
				row.account_number
			),
		)
	label = _default_using(company, row.name)
	if label:
		return (
			"company_default",
			_(
				"Account {0} is the company's {1}. Choose another account for that default, then run this again."
			).format(row.account_number, _(label)),
		)
	return None


def _company_has_ledger_entries(company: str) -> bool:
	return bool(frappe.db.exists("GL Entry", {"company": company}))


def _check_company(company: str):
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(frappe.bold(company or "")), exc=PcgeApplyError)
	if not is_peru_company(company):
		frappe.throw(
			_("Company {0} is not a Peruvian company.").format(frappe.bold(company)), exc=PcgeApplyError
		)


def _remove_existing_chart(company: str):
	"""Delete the company's chart the way ERPNext's Chart of Accounts Importer does.

	Every deletion goes through ERPNext's own link checks: if anything still
	refers to an account (an item, a bank account, a draft document...) the whole
	operation stops with that message and nothing is changed.
	"""
	from erpnext.accounts.doctype.chart_of_accounts_importer.chart_of_accounts_importer import (
		unset_existing_data,
	)

	# ERPNext creates a default "<Country> Tax" item tax template with every
	# company; its importer forgets to remove it and then cannot delete the
	# tax account it points to.
	for name in frappe.get_all("Item Tax Template", filters={"company": company}, pluck="name"):
		frappe.delete_doc("Item Tax Template", name, ignore_permissions=True)
	unset_existing_data(company)
	frappe.clear_cache(doctype="Company")


def _insert_account(company, currency, code, name, parent, is_group):
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": name,
			"account_number": code,
			"company": company,
			"parent_account": parent,
			"is_group": 1 if is_group else 0,
			"root_type": root_type_for(code),
			"report_type": report_type_for(code),
			"account_type": account_type_for(code),
			"account_currency": currency,
		}
	)
	doc.flags.ignore_permissions = True
	if not parent:
		doc.flags.ignore_mandatory = True  # root accounts have no parent
	doc.insert()
	return doc


def _convert_to_group(account_name: str):
	doc = frappe.get_doc("Account", account_name)
	doc.flags.ignore_permissions = True
	# ERPNext's own flag: a typed ledger (a bank account, a payable account...)
	# keeps its account type when it becomes the group of its sub-accounts.
	doc.flags.exclude_account_type_check = True
	doc.convert_ledger_to_group()


def _new_report(company, dry_run, **extra):
	report = frappe._dict(
		company=company,
		dry_run=bool(dry_run),
		created=[],
		existing=0,
		name_differences=[],
		conflicts=[],
		converted_to_group=[],
		skipped=[],
	)
	report.update(extra)
	return report


def apply_pcge(company: str, replace_existing: bool = False, dry_run: bool = False) -> dict:
	"""Create the PCGE accounts missing from ``company``. Returns a report.

	Report keys: ``created`` (codes), ``existing`` (count), ``name_differences``
	(same code, other name: the company's name is kept), ``conflicts`` (nothing
	is overwritten; a person must decide), ``converted_to_group``, ``skipped``,
	``defaults_set``, ``defaults_provisional``, ``defaults_kept`` and
	``defaults_left_empty``.
	"""
	if dry_run:
		return _apply_pcge(company, replace_existing, dry_run=True)
	with chart_lock():
		return _apply_pcge(company, replace_existing, dry_run=False)


def _apply_pcge(company: str, replace_existing: bool, dry_run: bool) -> dict:
	_check_company(company)
	catalogue = load_catalogue()
	report = _new_report(company, dry_run, replaced_existing=False, total_in_catalogue=len(catalogue))

	if replace_existing:
		if _company_has_ledger_entries(company):
			frappe.throw(
				_(
					"The chart of accounts of {0} cannot be replaced because the company already has ledger entries. Apply the PCGE without replacing: it only adds the missing accounts."
				).format(frappe.bold(company)),
				exc=PcgeApplyError,
			)
		report.replaced_existing = True
		if not dry_run:
			_remove_existing_chart(company)

	existing = {} if (replace_existing and dry_run) else _existing_accounts(company)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	blocked: set[str] = set()

	previous_nsm_flag = frappe.local.flags.ignore_update_nsm
	frappe.local.flags.ignore_update_nsm = True
	try:
		for account in catalogue:
			_apply_one(account, company, currency, existing, blocked, report, dry_run)
	finally:
		frappe.local.flags.ignore_update_nsm = previous_nsm_flag

	if not dry_run and (report.created or report.converted_to_group):
		rebuild_tree("Account")  # one argument: Frappe v16 no longer accepts the parent field

	_set_company_defaults(company, existing, report, dry_run)
	return report


def _apply_one(account: PcgeAccount, company, currency, existing, blocked, report, dry_run):
	code = account.code
	current = existing.get(code)

	if current:
		report.existing += 1
		if _normalize(current.account_name) != _normalize(account.name):
			report.name_differences.append(
				{"code": code, "company_name": current.account_name, "pcge_name": account.name}
			)
		if current.root_type != account.root_type:
			report.conflicts.append(
				{
					"code": code,
					"account": current.name,
					"reason": "root_type",
					"detail": _("The company's account is {0}; the PCGE mapping expects {1}.").format(
						current.root_type, account.root_type
					),
				}
			)
		if account.is_group and not current.is_group:
			obstacle = _why_not_a_group(company, current)
			if obstacle:
				blocked.add(code)
				report.conflicts.append(
					{"code": code, "account": current.name, "reason": obstacle[0], "detail": obstacle[1]}
				)
			else:
				report.converted_to_group.append(code)
				current.is_group = 1
				if not dry_run:
					_convert_to_group(current.name)
		return

	parent = None
	if not account.is_element_root:
		if account.parent_code in blocked:
			blocked.add(code)
			report.skipped.append({"code": code, "reason": "parent_not_available"})
			return
		parent_row = existing.get(account.parent_code)
		if not parent_row:
			# cannot happen with a well-formed catalogue: parents come first
			blocked.add(code)
			report.skipped.append({"code": code, "reason": "parent_missing"})
			return
		parent = parent_row.name

	report.created.append(code)
	if dry_run:
		existing[code] = frappe._dict(
			name=f"(new) {code}",
			account_name=account.name,
			account_number=code,
			is_group=1 if account.is_group else 0,
			root_type=account.root_type,
			simulated=True,
		)
		return
	doc = _insert_account(company, currency, code, account.name, parent, account.is_group)
	existing[code] = frappe._dict(
		name=doc.name,
		account_name=doc.account_name,
		account_number=code,
		is_group=doc.is_group,
		root_type=doc.root_type,
	)


def _set_company_defaults(company, existing, report, dry_run):
	"""Fill the company defaults an invoice needs, without overriding any that is already set."""
	report.defaults_set = {}
	report.defaults_kept = {}
	current = frappe.db.get_value("Company", company, list(COMPANY_DEFAULTS), as_dict=True) or {}
	if report.replaced_existing and dry_run:
		current = {}
	updates = {}
	for fieldname, code in COMPANY_DEFAULTS.items():
		if current.get(fieldname):
			report.defaults_kept[fieldname] = current[fieldname]
			continue
		row = existing.get(code)
		if row and not row.is_group:
			updates[fieldname] = row.name
			report.defaults_set[fieldname] = code
	if updates and not dry_run:
		frappe.db.set_value("Company", company, updates)
		frappe.clear_cache(doctype="Company")
	report.defaults_provisional = [name for name in PROVISIONAL_DEFAULTS if name in report.defaults_set]
	left = frappe.db.get_value("Company", company, list(DEFAULTS_LEFT_TO_THE_ACCOUNTANT), as_dict=True) or {}
	report.defaults_left_empty = [
		fieldname
		for fieldname in DEFAULTS_LEFT_TO_THE_ACCOUNTANT
		if not left.get(fieldname) or (report.replaced_existing and dry_run)
	]


def import_client_accounts(
	company: str, rows: list[dict], prefer_client_names: bool = False, dry_run: bool = False
) -> dict:
	"""Add the company's own accounts under the PCGE.

	``rows`` is a list of ``{"code": ..., "name": ...}``. Each account is placed
	under the existing account whose number is the longest prefix of its code.
	A bad row is rejected with its reason and the remaining rows are processed.

	When a code already exists with a different name nothing is overwritten
	unless ``prefer_client_names`` is set, in which case the account takes the
	company's name; either way the difference is listed in the report.
	"""
	if dry_run:
		return _import_client_accounts(company, rows, prefer_client_names, dry_run=True)
	with chart_lock():
		return _import_client_accounts(company, rows, prefer_client_names, dry_run=False)


def _import_client_accounts(company: str, rows: list[dict], prefer_client_names: bool, dry_run: bool) -> dict:
	_check_company(company)
	existing = _existing_accounts(company)
	missing_roots = [digit for digit in sorted(ELEMENTS) if digit not in existing]
	if missing_roots:
		frappe.throw(
			_("Apply the PCGE to {0} before importing the company's own accounts.").format(
				frappe.bold(company)
			),
			exc=PcgeApplyError,
		)

	report = _new_report(company, dry_run, unchanged=0, renamed=[], rejected=[])
	currency = frappe.get_cached_value("Company", company, "default_currency")

	prepared = []
	seen: dict[str, int] = {}
	for line, row in enumerate(rows, start=1):
		raw_code = (row or {}).get("code")
		name = " ".join(str((row or {}).get("name") or "").split())
		try:
			code = validate_client_code(raw_code)
		except PcgeError as error:
			report.rejected.append({"line": line, "code": str(raw_code or ""), "reason": error.code})
			continue
		if not name:
			report.rejected.append({"line": line, "code": code, "reason": "name_missing"})
			continue
		if code in seen:
			report.rejected.append(
				{"line": line, "code": code, "reason": "repeated_in_file", "first_line": seen[code]}
			)
			continue
		seen[code] = line
		prepared.append((code, name, line))

	codes_in_file = {code for code, _name, _line in prepared}
	blocked: set[str] = set()

	previous_nsm_flag = frappe.local.flags.ignore_update_nsm
	frappe.local.flags.ignore_update_nsm = True
	try:
		for code, name, line in sorted(prepared):
			_import_one(
				code,
				name,
				line,
				company,
				currency,
				existing,
				codes_in_file,
				blocked,
				report,
				prefer_client_names,
				dry_run,
			)
	finally:
		frappe.local.flags.ignore_update_nsm = previous_nsm_flag

	if not dry_run and (report.created or report.converted_to_group or report.renamed):
		rebuild_tree("Account")  # one argument: Frappe v16 no longer accepts the parent field
	return report


def _import_one(
	code,
	name,
	line,
	company,
	currency,
	existing,
	codes_in_file,
	blocked,
	report,
	prefer_client_names,
	dry_run,
):
	current = existing.get(code)
	if current:
		if _normalize(current.account_name) == _normalize(name):
			report.unchanged += 1
			return
		report.name_differences.append(
			{"line": line, "code": code, "company_name": name, "existing_name": current.account_name}
		)
		if prefer_client_names:
			report.renamed.append(code)
			if not dry_run:
				from erpnext.accounts.doctype.account.account import update_account_number

				new_name = update_account_number(current.name, name, code)
				current.name = new_name or current.name
			current.account_name = name
		return

	parent_code = next(
		(code[:length] for length in range(len(code) - 1, 0, -1) if code[:length] in existing), None
	)
	if not parent_code or parent_code in blocked:
		blocked.add(code)
		report.rejected.append({"line": line, "code": code, "reason": "parent_not_available"})
		return
	parent = existing[parent_code]

	if not parent.is_group:
		obstacle = _why_not_a_group(company, parent)
		if obstacle:
			blocked.add(code)
			report.conflicts.append(
				{
					"line": line,
					"code": code,
					"account": parent.name,
					"reason": obstacle[0],
					"detail": obstacle[1],
				}
			)
			return
		report.converted_to_group.append(parent_code)
		parent.is_group = 1
		if not dry_run:
			_convert_to_group(parent.name)

	is_group = any(other != code and other.startswith(code) for other in codes_in_file)
	report.created.append(code)
	if dry_run:
		existing[code] = frappe._dict(
			name=f"(new) {code}",
			account_name=name,
			account_number=code,
			is_group=1 if is_group else 0,
			root_type=root_type_for(code),
			simulated=True,
		)
		return
	doc = _insert_account(company, currency, code, name, parent.name, is_group)
	existing[code] = frappe._dict(
		name=doc.name,
		account_name=doc.account_name,
		account_number=code,
		is_group=doc.is_group,
		root_type=doc.root_type,
	)
