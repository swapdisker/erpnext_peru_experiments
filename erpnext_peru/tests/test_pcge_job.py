# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Applying the PCGE as a background job (the Company form's "Apply PCGE 2019")."""

import time
from unittest.mock import patch

import frappe

from erpnext_peru.accounts import api
from erpnext_peru.accounts.pcge import PcgeApplyError, apply_pcge
from erpnext_peru.tests.utils import (
	FOREIGN_COMPANY,
	PCGE_COMPANY,
	PERU_COMPANY,
	PeruTestCase,
	ensure_pcge_company,
	make_customer,
	make_ruc,
	make_sales_invoice,
	make_series,
	pcge_account,
)


def make_user(email: str, roles: list[str]) -> str:
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert()
		user.add_roles(*roles)
	return email


class TestPcgeJob(PeruTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_pcge_company()

	def setUp(self):
		super().setUp()
		self.clear_states()

	def tearDown(self):
		frappe.set_user("Administrator")
		self.clear_states()
		super().tearDown()

	def clear_states(self):
		for company in (PCGE_COMPANY, PERU_COMPANY, FOREIGN_COMPANY):
			frappe.cache.delete_value(api._state_key(company))

	def test_no_job_yet(self):
		self.assertEqual(api.pcge_job_status(PCGE_COMPANY), {"status": "none"})

	def test_job_applies_the_pcge_and_reports(self):
		frappe.delete_doc("Account", pcge_account("1675"))
		api.run_pcge_job(PCGE_COMPANY)
		state = api.pcge_job_status(PCGE_COMPANY)
		self.assertEqual(state["status"], "done")
		self.assertEqual(state["report"]["created"], ["1675"])
		self.assertEqual(state["report"]["existing"], 1773)
		self.assertEqual(state["report"]["conflicts"], [])
		self.assertTrue(pcge_account("1675"))

	def test_request_queues_the_job(self):
		"""Under test the queue runs the job at once, so the state is already final."""
		frappe.delete_doc("Account", pcge_account("1675"))
		with patch.object(api.frappe, "enqueue", wraps=frappe.enqueue) as enqueue:
			state = api.apply_pcge_to_company(PCGE_COMPANY)
		kwargs = enqueue.call_args.kwargs
		self.assertEqual(enqueue.call_args.args, ("erpnext_peru.accounts.api.run_pcge_job",))
		self.assertEqual(kwargs["queue"], "long")
		self.assertTrue(kwargs["deduplicate"])
		self.assertEqual(kwargs["job_id"], f"erpnext_peru_pcge::{PCGE_COMPANY}")
		self.assertEqual((kwargs["company"], kwargs["replace_existing"]), (PCGE_COMPANY, False))
		self.assertEqual(state["status"], "done")
		self.assertEqual(state["report"]["created"], ["1675"])

	def test_failed_job_changes_nothing_and_says_why(self):
		customer = make_customer("_Test PE Job Customer", "6", make_ruc(81000001)).name
		before = frappe.db.count("Account", {"company": PCGE_COMPANY})

		def half_done_then_fail(company, replace_existing=False, dry_run=False):
			frappe.delete_doc("Account", pcge_account("1675"))  # work already written...
			raise frappe.ValidationError("<b>something</b> went wrong half way")  # ...when it breaks

		with patch.object(api, "apply_pcge", half_done_then_fail):
			api.run_pcge_job(PCGE_COMPANY)

		state = api.pcge_job_status(PCGE_COMPANY)
		self.assertEqual(state["status"], "failed")
		self.assertEqual(state["error"], "something went wrong half way")
		self.assertNotIn("report", state)
		self.assertEqual(frappe.db.count("Account", {"company": PCGE_COMPANY}), before)
		self.assertTrue(pcge_account("1675"))
		self.assertTrue(frappe.db.exists("Customer", customer))  # work done before the job is kept
		self.assertTrue(
			frappe.db.exists(
				"Error Log", {"method": ("like", f"%applying the PCGE to {PCGE_COMPANY} failed%")}
			)
		)

	def test_job_cut_short_by_a_deadlock_changes_nothing(self):
		"""MariaDB then rolls back the whole transaction and forgets the savepoint."""
		before = frappe.db.count("Account", {"company": PCGE_COMPANY})

		def deadlock(company, replace_existing=False, dry_run=False):
			frappe.delete_doc("Account", pcge_account("1675"))
			frappe.db.sql(f"RELEASE SAVEPOINT {api.JOB_SAVEPOINT}")  # as the server would
			raise frappe.QueryDeadlockError("Deadlock found when trying to get lock")

		with patch.object(api, "apply_pcge", deadlock):
			api.run_pcge_job(PCGE_COMPANY)

		state = api.pcge_job_status(PCGE_COMPANY)
		self.assertEqual(state["status"], "failed")
		self.assertIn("Deadlock", state["error"])
		self.assertEqual(frappe.db.count("Account", {"company": PCGE_COMPANY}), before)

	def test_state_is_failed_even_when_undoing_fails(self):
		def broken(company, replace_existing=False, dry_run=False):
			raise frappe.ValidationError("first problem")

		with patch.object(api, "apply_pcge", broken):
			with patch.object(api, "_undo_job", side_effect=ConnectionError("lost")):
				with self.assertRaises(ConnectionError):
					api.run_pcge_job(PCGE_COMPANY)
		state = api.pcge_job_status(PCGE_COMPANY)
		self.assertEqual((state["status"], state["error"]), ("failed", "first problem"))

	def test_second_request_while_one_is_in_progress_is_refused(self):
		for status in ("queued", "running"):
			api._set_state(PCGE_COMPANY, status=status, started=time.time())
			with self.subTest(status=status):
				with patch.object(api.frappe, "enqueue") as enqueue:
					with self.assertRaises(PcgeApplyError):
						api.apply_pcge_to_company(PCGE_COMPANY)
				enqueue.assert_not_called()
				self.assertEqual(api.pcge_job_status(PCGE_COMPANY)["status"], status)

	def test_a_job_that_died_does_not_block_forever(self):
		api._set_state(PCGE_COMPANY, status="running", started=time.time() - api.JOB_STALE_AFTER - 1)
		state = api.pcge_job_status(PCGE_COMPANY)
		self.assertEqual(state["status"], "failed")
		self.assertIn("did not finish", state["error"])
		self.assertEqual(api.apply_pcge_to_company(PCGE_COMPANY)["status"], "done")
		# just inside the limit it still counts as running
		api._set_state(PCGE_COMPANY, status="running", started=time.time() - api.JOB_STALE_AFTER + 60)
		self.assertEqual(api.pcge_job_status(PCGE_COMPANY)["status"], "running")

	def test_problems_known_in_advance_are_reported_in_the_request(self):
		with patch.object(api.frappe, "enqueue") as enqueue:
			with self.assertRaises(PcgeApplyError):
				api.apply_pcge_to_company(FOREIGN_COMPANY)
			with self.assertRaises(PcgeApplyError):
				api.apply_pcge_to_company("No such company")
			customer = make_customer("_Test PE Job Customer 2", "6", make_ruc(81000002)).name
			make_series("01", "F001")
			make_sales_invoice(customer).submit()
			with self.assertRaises(PcgeApplyError):
				api.apply_pcge_to_company(PERU_COMPANY, replace_existing=1)
		enqueue.assert_not_called()
		for company in (FOREIGN_COMPANY, PERU_COMPANY):
			self.assertEqual(api.get_job_state(company), {"status": "none"})

	def test_preview_runs_in_the_request_and_writes_nothing(self):
		before = frappe.db.count("Account", {"company": PERU_COMPANY})
		report = api.preview_pcge(PERU_COMPANY, replace_existing="0")
		self.assertTrue(report.dry_run)
		self.assertEqual(len(report.created), 1774)
		self.assertEqual(frappe.db.count("Account", {"company": PERU_COMPANY}), before)
		self.assertEqual(api.get_job_state(PERU_COMPANY), {"status": "none"})

	def test_only_managers_may_use_the_actions(self):
		actions = (
			api.preview_pcge,
			api.apply_pcge_to_company,
			api.pcge_job_status,
			api.setup_igv_for_company,
		)
		for user in ("Guest", make_user("_test_pe_clerk@example.com", ["Accounts User", "Sales User"])):
			frappe.set_user(user)
			for action in actions:
				with self.subTest(user=user, action=action.__name__):
					with patch.object(api.frappe, "enqueue") as enqueue:
						with self.assertRaises(frappe.PermissionError):
							action(PCGE_COMPANY)
					enqueue.assert_not_called()
		frappe.set_user("Administrator")
		self.assertEqual(api.get_job_state(PCGE_COMPANY), {"status": "none"})

	def test_accounts_manager_may_use_the_actions(self):
		frappe.set_user(make_user("_test_pe_manager@example.com", ["Accounts Manager"]))
		self.assertEqual(api.pcge_job_status(PCGE_COMPANY), {"status": "none"})
		self.assertEqual(api.preview_pcge(PCGE_COMPANY).created, [])
		self.assertEqual(api.apply_pcge_to_company(PCGE_COMPANY)["status"], "done")

	def test_manager_restricted_to_another_company_is_refused(self):
		user = make_user("_test_pe_manager_2@example.com", ["Accounts Manager"])
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Company", "for_value": PERU_COMPANY}
		).insert()
		frappe.set_user(user)
		for action in (
			api.preview_pcge,
			api.apply_pcge_to_company,
			api.pcge_job_status,
			api.setup_igv_for_company,
		):
			with self.subTest(action=action.__name__), self.assertRaises(frappe.PermissionError):
				action(PCGE_COMPANY)
		self.assertEqual(api.pcge_job_status(PERU_COMPANY), {"status": "none"})

	def test_states_of_different_companies_are_independent(self):
		api._set_state(PERU_COMPANY, status="running", started=time.time())
		self.assertEqual(api.pcge_job_status(PCGE_COMPANY), {"status": "none"})
		self.assertEqual(apply_pcge(PCGE_COMPANY, dry_run=True).created, [])
