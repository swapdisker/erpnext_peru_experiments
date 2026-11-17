# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Methods called from the Company form.

Applying the PCGE creates about 1,800 accounts, too long for a web request on
a slow server. It runs as a background job; the form asks for its state until
it has finished. The state lives in the cache, keyed by company.
"""

import time

import frappe
from frappe import _
from frappe.utils import cint, strip_html

from erpnext_peru.accounts.igv import setup_igv
from erpnext_peru.accounts.pcge import PcgeApplyError, apply_pcge

ALLOWED_ROLES = ("System Manager", "Accounts Manager")

JOB_TIMEOUT = 30 * 60  # seconds the worker may spend
JOB_STALE_AFTER = JOB_TIMEOUT + 5 * 60  # a job still "running" after this is taken for dead
STATE_EXPIRES_IN = 24 * 60 * 60

STATUS_NONE = "none"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
IN_PROGRESS = (STATUS_QUEUED, STATUS_RUNNING)


def _state_key(company: str) -> str:
	return f"erpnext_peru:pcge_job:{company}"


def _job_id(company: str) -> str:
	return f"erpnext_peru_pcge::{company}"


def _only_managers(company: str | None = None):
	"""Role check for every method here.

	Not ``frappe.only_for``: that one lets everybody through while tests run, so
	a test could never show that it works.
	"""
	if frappe.session.user != "Administrator" and not set(ALLOWED_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if company and frappe.db.exists("Company", company):
		# honours User Permissions that restrict a manager to some companies
		frappe.has_permission("Company", "write", company, throw=True)


def _read_state(company: str) -> dict | None:
	# expires=True: without it Frappe keeps the first answer for the rest of the
	# request, and a state written a moment later would not be seen.
	return frappe.cache.get_value(_state_key(company), expires=True)


def _set_state(company: str, **state):
	frappe.cache.set_value(_state_key(company), state, expires_in_sec=STATE_EXPIRES_IN)
	return state


def get_job_state(company: str) -> dict:
	state = _read_state(company) or {"status": STATUS_NONE}
	if state.get("status") in IN_PROGRESS and time.time() - state.get("started", 0) > JOB_STALE_AFTER:
		state = {
			"status": STATUS_FAILED,
			"error": _(
				"The job that applies the PCGE to {0} did not finish. Check the Error Log and run it again."
			).format(company),
		}
	return state


@frappe.whitelist()
def preview_pcge(company: str, replace_existing=0):
	"""What applying the PCGE would do. Changes nothing."""
	_only_managers(company)
	return apply_pcge(company, replace_existing=bool(cint(replace_existing)), dry_run=True)


@frappe.whitelist(methods=["POST"])
def apply_pcge_to_company(company: str, replace_existing=0):
	"""Queue the job that applies the PCGE. Returns the job state."""
	_only_managers(company)
	replace = bool(cint(replace_existing))

	# Fail in the request, with the message on screen, for whatever can be known
	# now: unknown or non-Peruvian company, replacing a chart that has entries.
	apply_pcge(company, replace_existing=replace, dry_run=True)

	if get_job_state(company).get("status") in IN_PROGRESS:
		frappe.throw(
			_("The PCGE is already being applied to {0}. Wait for it to finish.").format(
				frappe.bold(company)
			),
			exc=PcgeApplyError,
		)

	_set_state(
		company, status=STATUS_QUEUED, started=time.time(), replace_existing=replace, user=frappe.session.user
	)
	frappe.enqueue(
		"erpnext_peru.accounts.api.run_pcge_job",
		queue="long",
		timeout=JOB_TIMEOUT,
		job_id=_job_id(company),
		deduplicate=True,
		now=bool(frappe.flags.in_test),
		company=company,
		replace_existing=replace,
	)
	return get_job_state(company)


@frappe.whitelist()
def pcge_job_status(company: str):
	_only_managers(company)
	return get_job_state(company)


JOB_SAVEPOINT = "erpnext_peru_pcge_job"


def _undo_job():
	"""Undo everything the job wrote.

	Back to the savepoint, so that the transaction a test runs in survives.
	A deadlock or a "record has changed" error makes MariaDB roll back the
	whole transaction and forget the savepoint; then the transaction is
	rolled back as a whole, which leaves the same result: nothing written.
	"""
	try:
		frappe.db.rollback(save_point=JOB_SAVEPOINT)
	except Exception:
		frappe.db.rollback()


def run_pcge_job(company: str, replace_existing: bool = False):
	"""Background job. All or nothing: a failure leaves the chart as it was."""
	previous = _read_state(company) or {}
	_set_state(
		company,
		status=STATUS_RUNNING,
		started=previous.get("started") or time.time(),
		replace_existing=bool(replace_existing),
		user=previous.get("user"),
	)
	frappe.db.savepoint(JOB_SAVEPOINT)
	try:
		report = apply_pcge(company, replace_existing=bool(replace_existing), dry_run=False)
	except Exception as error:
		message = strip_html(str(error)).strip() or type(error).__name__
		try:
			_undo_job()
			frappe.log_error(title=f"erpnext_peru: applying the PCGE to {company} failed")
		finally:
			# Even if undoing failed (connection lost), the page must not wait forever.
			_set_state(company, status=STATUS_FAILED, error=message)
		return
	if not frappe.flags.in_test:
		frappe.db.commit()  # nosemgrep: the job is the unit of work
	_set_state(company, status=STATUS_DONE, report=dict(report))


@frappe.whitelist(methods=["POST"])
def setup_igv_for_company(company: str):
	_only_managers(company)
	return setup_igv(company)
