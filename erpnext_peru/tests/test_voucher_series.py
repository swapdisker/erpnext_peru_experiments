# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Series master and the gapless, duplicate-free numbering under concurrency."""

import threading
import time

import frappe

from erpnext_peru.erpnext_peru.doctype.sunat_voucher_series.sunat_voucher_series import (
	allocate_next_number,
	get_enabled_series,
)
from erpnext_peru.overrides.common import ComprobanteError
from erpnext_peru.tests.utils import (
	FOREIGN_COMPANY,
	PERU_COMPANY,
	PeruTestCase,
	make_customer,
	make_ruc,
	make_sales_invoice,
	make_series,
)


class TestVoucherSeries(PeruTestCase):
	def test_name_and_normalization(self):
		series = make_series("01", " f001 ")
		self.assertEqual(series.series, "F001")
		self.assertEqual(series.name, f"01-F001-{PERU_COMPANY}")

	def test_same_series_code_for_different_types(self):
		make_series("01", "F001")
		note_series = make_series("07", "F001")  # own correlative per type
		self.assertEqual(note_series.name, f"07-F001-{PERU_COMPANY}")

	def test_duplicate_series_is_blocked(self):
		make_series("01", "F001")
		with self.assertRaises(frappe.DuplicateEntryError):
			make_series("01", "f001")

	def test_validation(self):
		with self.assertRaises(ComprobanteError):
			make_series("01", "B001")
		with self.assertRaises(ComprobanteError):
			make_series("03", "F001")
		with self.assertRaises(ComprobanteError):
			make_series("01", "F01")
		with self.assertRaises(frappe.ValidationError):
			make_series("09", "T001")  # not issued from Sales Invoices
		with self.assertRaises(frappe.ValidationError):
			make_series("01", "F001", company=FOREIGN_COMPANY)
		with self.assertRaises(frappe.ValidationError):
			make_series("01", "F001", current_number=-1)
		with self.assertRaises(frappe.ValidationError):
			make_series("01", "F001", current_number=100000000)

	def test_counter_cannot_go_below_issued_numbers(self):
		customer = make_customer("_Test PE VS Customer", "6", make_ruc(50000001)).name
		series = make_series("01", "F001", current_number=10)
		invoice = make_sales_invoice(customer)
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "F001-00000011")

		series.reload()
		series.current_number = 5
		with self.assertRaises(frappe.ValidationError) as ctx:
			series.save()
		self.assertIn("F001-00000011", str(ctx.exception))

		# cancelled vouchers still hold their number
		invoice.cancel()
		series.reload()
		series.current_number = 10
		with self.assertRaises(frappe.ValidationError):
			series.save()

		series.reload()
		series.current_number = 20  # skipping ahead is allowed
		series.save()
		later = make_sales_invoice(customer)
		later.submit()
		self.assertEqual(later.pe_voucher_number, "F001-00000021")

	def test_key_fields_are_fixed_after_creation(self):
		series = make_series("01", "F001")
		series.series = "F002"
		with self.assertRaises(frappe.CannotChangeConstantError):
			series.save()

	def test_used_series_cannot_be_deleted(self):
		customer = make_customer("_Test PE VS Customer 2", "6", make_ruc(50000002)).name
		series = make_series("01", "F001")
		unused = make_series("01", "F002")
		invoice = make_sales_invoice(customer, pe_series="F001")
		invoice.submit()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("SUNAT Voucher Series", series.name)
		frappe.delete_doc("SUNAT Voucher Series", unused.name)

	def test_last_number(self):
		make_series("01", "F001", current_number=99999998)
		self.assertEqual(allocate_next_number(PERU_COMPANY, "01", "F001"), 99999999)
		with self.assertRaises(frappe.ValidationError):
			allocate_next_number(PERU_COMPANY, "01", "F001")

	def test_allocation_refuses_a_number_that_already_exists(self):
		"""Defence in depth if the counter is ever reset behind the application's back."""
		customer = make_customer("_Test PE VS Customer 3", "6", make_ruc(50000003)).name
		series = make_series("01", "F001")
		invoice = make_sales_invoice(customer)
		invoice.submit()
		frappe.db.set_value("SUNAT Voucher Series", series.name, "current_number", 0)
		again = make_sales_invoice(customer)
		with self.assertRaises(frappe.ValidationError) as ctx:
			again.submit()
		self.assertIn("F001-00000001", str(ctx.exception))

	def test_enabled_series_lookup(self):
		make_series("07", "FC01")
		make_series("07", "BC01")
		make_series("07", "FC02", enabled=0)
		self.assertEqual(get_enabled_series(PERU_COMPANY, "07"), ["BC01", "FC01"])
		self.assertEqual(get_enabled_series(PERU_COMPANY, "07", "F"), ["FC01"])
		self.assertEqual(get_enabled_series(PERU_COMPANY, "07", "B"), ["BC01"])
		self.assertEqual(get_enabled_series(PERU_COMPANY, "01"), [])


class TestConcurrentNumbering(PeruTestCase):
	"""Several database connections allocate numbers at the same time.

	These tests commit, so they use their own series and clean up after
	themselves.
	"""

	SERIES = "FZ9"

	def setUp(self):
		super().setUp()
		self.series_code = self.SERIES + "1"
		self._cleanup()
		make_series("01", self.series_code)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()
		self._cleanup()
		super().tearDown()

	def _cleanup(self):
		names = frappe.get_all(
			"Sales Invoice", {"company": PERU_COMPANY, "pe_series": ("like", self.SERIES + "%")}, pluck="name"
		)
		for name in names:
			for doctype in ("GL Entry", "Payment Ledger Entry"):
				frappe.db.delete(doctype, {"voucher_no": name})
			frappe.db.delete("Sales Invoice Item", {"parent": name})
			frappe.db.delete("Sales Invoice", {"name": name})
		frappe.db.delete("SUNAT Voucher Series", {"series": ("like", self.SERIES + "%")})
		frappe.db.delete("Customer", {"customer_name": "_Test PE Concurrent"})
		frappe.db.commit()

	def _run_threads(self, target, count):
		site = frappe.local.site
		results, errors = [], []
		barrier = threading.Barrier(count)

		def worker(index):
			frappe.init(site=site)
			frappe.connect()
			try:
				frappe.set_user("Administrator")
				barrier.wait(timeout=30)
				results.append(target(index))
			except Exception as exc:
				frappe.db.rollback()
				errors.append(repr(exc))
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=120)
		return results, errors

	def test_parallel_allocations_never_collide(self):
		workers, rounds = 8, 5

		def allocate(index):
			allocated = []
			for _ in range(rounds):
				number = allocate_next_number(PERU_COMPANY, "01", self.series_code)
				time.sleep(0.01)  # hold the row lock for a moment
				frappe.db.commit()
				allocated.append(number)
			return allocated

		results, errors = self._run_threads(allocate, workers)
		self.assertEqual(errors, [])
		numbers = sorted(n for chunk in results for n in chunk)
		self.assertEqual(numbers, list(range(1, workers * rounds + 1)))  # no gaps, no duplicates
		frappe.db.rollback()
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", {"series": self.series_code}, "current_number"),
			workers * rounds,
		)

	def test_rolled_back_allocations_leave_no_gap(self):
		workers = 6

		def allocate(index):
			number = allocate_next_number(PERU_COMPANY, "01", self.series_code)
			time.sleep(0.02)
			if index % 2:
				frappe.db.rollback()  # e.g. the invoice failed later in the request
				return None
			frappe.db.commit()
			return number

		results, errors = self._run_threads(allocate, workers)
		self.assertEqual(errors, [])
		committed = sorted(n for n in results if n is not None)
		self.assertEqual(committed, [1, 2, 3])
		frappe.db.rollback()
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", {"series": self.series_code}, "current_number"), 3
		)

	def test_parallel_invoice_submissions(self):
		workers = 4
		customer = make_customer("_Test PE Concurrent", "6", make_ruc(50000009)).name
		drafts = [make_sales_invoice(customer, pe_series=self.series_code).name for _ in range(workers)]
		frappe.db.commit()

		def submit(index):
			invoice = frappe.get_doc("Sales Invoice", drafts[index])
			invoice.submit()
			frappe.db.commit()
			return invoice.pe_voucher_number

		results, errors = self._run_threads(submit, workers)
		self.assertEqual(errors, [])
		expected = [f"{self.series_code}-{n:08d}" for n in range(1, workers + 1)]
		self.assertEqual(sorted(results), expected)
		frappe.db.rollback()
		stored = frappe.get_all(
			"Sales Invoice", {"name": ("in", drafts), "docstatus": 1}, pluck="pe_voucher_number"
		)
		self.assertEqual(sorted(stored), expected)
