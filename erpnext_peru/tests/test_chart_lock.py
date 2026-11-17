# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""One change to a chart of accounts at a time per site (accounts/pcge.py: chart_lock)."""

import threading
from unittest.mock import patch

import frappe

from erpnext_peru.accounts import pcge
from erpnext_peru.accounts.pcge import PcgeApplyError, apply_pcge, import_client_accounts
from erpnext_peru.tests.utils import PCGE_COMPANY, PeruTestCase, ensure_pcge_company, make_customer


def lock_name():
	return f"{frappe.conf.db_name}:{pcge.CHART_LOCK}"


def lock_is_free():
	return frappe.db.sql("SELECT IS_FREE_LOCK(%s)", (lock_name(),))[0][0] == 1


class LockHolder:
	"""Holds the chart lock from another database connection, like a second job would."""

	def __init__(self):
		self.site = frappe.local.site
		self.name = lock_name()
		self.taken = threading.Event()
		self.release = threading.Event()
		self.thread = threading.Thread(target=self.run)

	def run(self):
		frappe.init(site=self.site)
		frappe.connect()
		try:
			frappe.db.sql("SELECT GET_LOCK(%s, 5)", (self.name,))
			self.taken.set()
			self.release.wait(timeout=60)
			frappe.db.sql("SELECT RELEASE_LOCK(%s)", (self.name,))
		finally:
			frappe.destroy()

	def __enter__(self):
		self.thread.start()
		assert self.taken.wait(timeout=30), "the other connection could not take the lock"
		return self

	def __exit__(self, *exc):
		self.release.set()
		self.thread.join(timeout=30)


class TestChartLock(PeruTestCase):
	ROWS = [{"code": "1041001", "name": "_Test lock bank"}]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_pcge_company()

	def test_applying_waits_for_the_lock_and_gives_up_with_a_message(self):
		with patch.object(pcge, "CHART_LOCK_WAIT", 1), LockHolder():
			with self.assertRaises(PcgeApplyError) as raised:
				apply_pcge(PCGE_COMPANY)
			self.assertIn("Another chart of accounts is being changed", str(raised.exception))
			with self.assertRaises(PcgeApplyError):
				import_client_accounts(PCGE_COMPANY, self.ROWS)
		# Free again: the same calls work.
		self.assertEqual(apply_pcge(PCGE_COMPANY).created, [])
		self.assertEqual(len(import_client_accounts(PCGE_COMPANY, self.ROWS).created), 1)

	def test_previews_do_not_need_the_lock(self):
		with patch.object(pcge, "CHART_LOCK_WAIT", 1), LockHolder():
			self.assertTrue(apply_pcge(PCGE_COMPANY, dry_run=True).dry_run)
			self.assertTrue(import_client_accounts(PCGE_COMPANY, self.ROWS, dry_run=True).dry_run)

	def test_lock_is_released_after_success_and_after_failure(self):
		apply_pcge(PCGE_COMPANY)
		self.assertTrue(lock_is_free())
		with (
			patch.object(pcge, "_apply_pcge", side_effect=ZeroDivisionError),
			self.assertRaises(ZeroDivisionError),
		):
			apply_pcge(PCGE_COMPANY)
		self.assertTrue(lock_is_free())

	def test_work_already_in_the_transaction_is_not_committed(self):
		"""The lock renews the snapshot only when nothing has been written yet."""
		customer = make_customer("_Test PE Lock Customer").name
		apply_pcge(PCGE_COMPANY)
		frappe.db.rollback()
		self.assertFalse(frappe.db.exists("Customer", customer))
