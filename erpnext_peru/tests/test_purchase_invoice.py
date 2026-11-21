# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Supplier comprobante fields on Purchase Invoices."""

import threading
import time
from unittest.mock import patch

import frappe
from frappe.utils import flt

from erpnext_peru.overrides import purchase_invoice
from erpnext_peru.overrides.common import ComprobanteError, DuplicateVoucherError
from erpnext_peru.tests.utils import (
	FOREIGN_COMPANY,
	PeruTestCase,
	make_purchase_invoice,
	make_return,
	make_ruc,
	make_supplier,
)


class TestPurchaseInvoice(PeruTestCase):
	def setUp(self):
		super().setUp()
		self.supplier = make_supplier("_Test PE PI Supplier", "6", make_ruc(70000001)).name
		self.other_supplier = make_supplier("_Test PE PI Supplier 2", "6", make_ruc(70000002)).name

	def test_factura_received(self):
		invoice = make_purchase_invoice(
			self.supplier, rate=250, pe_comprobante_type="01", pe_series="f001", pe_number="123"
		)
		self.assertEqual(invoice.pe_series, "F001")
		self.assertEqual(invoice.pe_number, "00000123")
		self.assertEqual(invoice.pe_voucher_number, "F001-00000123")
		self.assertEqual(invoice.bill_no, "F001-00000123")
		invoice.submit()
		self.assertEqual(invoice.docstatus, 1)
		entries = frappe.get_all(
			"GL Entry", {"voucher_no": invoice.name, "is_cancelled": 0}, ["account", "debit", "credit"]
		)
		self.assertEqual(flt(sum(e.debit for e in entries), 2), 250.00)
		self.assertEqual(flt(sum(e.credit for e in entries), 2), 250.00)

	def test_existing_bill_no_is_kept(self):
		invoice = make_purchase_invoice(
			self.supplier, bill_no="REF-1", pe_comprobante_type="01", pe_series="F001", pe_number="1"
		)
		self.assertEqual(invoice.bill_no, "REF-1")

	def test_bill_no_follows_a_corrected_number(self):
		invoice = make_purchase_invoice(
			self.supplier, rate=250, pe_comprobante_type="01", pe_series="F001", pe_number="123"
		)
		invoice.pe_number = "124"  # a typo corrected after the first save
		invoice.save()
		self.assertEqual(invoice.pe_voucher_number, "F001-00000124")
		self.assertEqual(invoice.bill_no, "F001-00000124")

	def test_bill_no_follows_a_removed_number(self):
		invoice = make_purchase_invoice(
			self.supplier, rate=250, pe_comprobante_type="01", pe_series="F001", pe_number="123"
		)
		invoice.update({"pe_comprobante_type": None, "pe_series": None, "pe_number": None})
		invoice.save()
		self.assertFalse(invoice.bill_no)

	def test_a_bill_no_typed_separately_survives_a_corrected_number(self):
		invoice = make_purchase_invoice(
			self.supplier, bill_no="REF-1", pe_comprobante_type="01", pe_series="F001", pe_number="1"
		)
		invoice.pe_number = "2"
		invoice.save()
		self.assertEqual(invoice.bill_no, "REF-1")

	def test_fields_are_optional(self):
		invoice = make_purchase_invoice(self.supplier)
		self.assertIsNone(invoice.pe_comprobante_type)
		self.assertIsNone(invoice.pe_voucher_number)
		invoice.submit()
		self.assertEqual(invoice.docstatus, 1)

	def test_number_without_type_is_blocked(self):
		with self.assertRaises(ComprobanteError):
			make_purchase_invoice(self.supplier, pe_series="F001", pe_number="1")

	def test_type_without_number_is_blocked(self):
		with self.assertRaises(ComprobanteError):
			make_purchase_invoice(self.supplier, pe_comprobante_type="01", pe_series="F001")

	def test_format_errors(self):
		cases = (
			("01", "F01", "1"),
			("01", "", "1"),
			("01", "F001", "123456789"),
			("03", "B001", "12A"),
			("01", "F001", "0"),
		)
		for comprobante_type, series, number in cases:
			with self.subTest(series=series, number=number), self.assertRaises(ComprobanteError):
				make_purchase_invoice(
					self.supplier, pe_comprobante_type=comprobante_type, pe_series=series, pe_number=number
				)

	def test_unknown_type(self):
		with self.assertRaises(frappe.ValidationError):
			make_purchase_invoice(self.supplier, pe_comprobante_type="99", pe_number="1")

	def test_other_document_types_are_loosely_checked(self):
		invoice = make_purchase_invoice(self.supplier, pe_comprobante_type="14", pe_number="s001-99887766")
		self.assertIsNone(invoice.pe_series)
		self.assertEqual(invoice.pe_voucher_number, "S001-99887766")

	def test_duplicate_supplier_document_is_blocked(self):
		first = make_purchase_invoice(
			self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="55"
		)
		with self.assertRaises(DuplicateVoucherError) as ctx:
			# same document typed differently
			make_purchase_invoice(
				self.supplier, pe_comprobante_type="01", pe_series="f001", pe_number="00000055"
			)
		self.assertIn(first.name, str(ctx.exception))
		first.submit()
		with self.assertRaises(DuplicateVoucherError):
			make_purchase_invoice(self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="55")

	def test_not_a_duplicate(self):
		make_purchase_invoice(self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="60")
		# other supplier, other type, other series, other number
		make_purchase_invoice(self.other_supplier, pe_comprobante_type="01", pe_series="F001", pe_number="60")
		make_purchase_invoice(self.supplier, pe_comprobante_type="03", pe_series="F001", pe_number="60")
		make_purchase_invoice(self.supplier, pe_comprobante_type="01", pe_series="F002", pe_number="60")
		make_purchase_invoice(self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="61")

	def test_cancelled_document_can_be_registered_again(self):
		first = make_purchase_invoice(
			self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="70"
		)
		first.submit()
		first.cancel()
		again = make_purchase_invoice(
			self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="70"
		)
		self.assertEqual(again.pe_voucher_number, "F001-00000070")

	def test_resaving_is_not_a_duplicate(self):
		invoice = make_purchase_invoice(
			self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="80"
		)
		invoice.remarks = "edited"
		invoice.save()

	def test_supplier_credit_note(self):
		original = make_purchase_invoice(
			self.supplier, rate=300, pe_comprobante_type="01", pe_series="F001", pe_number="90"
		)
		original.submit()
		note = make_return(original, pe_series="FC01", pe_number="4")
		self.assertEqual(note.pe_comprobante_type, "07")  # defaulted for a return
		self.assertEqual(note.pe_voucher_number, "FC01-00000004")
		self.assertEqual(note.pe_original_type, "01")
		self.assertEqual(note.pe_original_voucher_number, "F001-00000090")
		note.submit()
		self.assertEqual(note.docstatus, 1)

	def test_return_must_be_type_07_and_viceversa(self):
		original = make_purchase_invoice(
			self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number="91"
		)
		original.submit()
		with self.assertRaises(ComprobanteError):
			make_return(original, pe_comprobante_type="01", pe_series="F001", pe_number="92")
		with self.assertRaises(ComprobanteError):
			make_purchase_invoice(self.supplier, pe_comprobante_type="07", pe_series="FC01", pe_number="1")

	def test_note_needs_the_modified_voucher_to_submit(self):
		plain = make_purchase_invoice(self.supplier)  # registered without comprobante data
		plain.submit()
		note = make_return(plain, pe_series="FC01", pe_number="5")
		self.assertIsNone(note.pe_original_voucher_number)
		with self.assertRaises(ComprobanteError):
			note.submit()
		note.reload()
		note.pe_original_type = "01"
		note.pe_original_voucher_number = "f001-93"
		note.save()
		self.assertEqual(note.pe_original_voucher_number, "F001-00000093")
		note.submit()

	def test_supplier_debit_note(self):
		note = make_purchase_invoice(
			self.supplier,
			pe_comprobante_type="08",
			pe_series="FD01",
			pe_number="2",
			pe_original_type="01",
			pe_original_voucher_number="F001-94",
		)
		self.assertEqual(note.pe_original_voucher_number, "F001-00000094")
		note.submit()
		missing = make_purchase_invoice(
			self.supplier, pe_comprobante_type="08", pe_series="FD01", pe_number="3"
		)
		with self.assertRaises(ComprobanteError):
			missing.submit()

	def test_reference_fields_are_cleared_when_not_a_note(self):
		invoice = make_purchase_invoice(
			self.supplier,
			pe_comprobante_type="01",
			pe_series="F001",
			pe_number="95",
			pe_original_type="01",
			pe_original_voucher_number="F001-1",
		)
		self.assertIsNone(invoice.pe_original_type)
		self.assertIsNone(invoice.pe_original_voucher_number)

	def test_other_countries_are_untouched(self):
		invoice = make_purchase_invoice(
			self.supplier, company=FOREIGN_COMPANY, pe_comprobante_type="07", pe_series="???", pe_number="x y"
		)
		# type 07 without "is return", malformed series and number: nothing is checked
		self.assertEqual(invoice.pe_series, "???")
		self.assertEqual(invoice.pe_number, "x y")
		self.assertIsNone(invoice.pe_voucher_number)
		invoice.submit()
		self.assertEqual(invoice.docstatus, 1)


class TestConcurrentRegistration(PeruTestCase):
	"""Several connections register the same supplier document at once.

	These tests commit, so they use a supplier of their own and clean up after
	themselves.
	"""

	SUPPLIER = "_Test PE PI Concurrent"

	def setUp(self):
		super().setUp()
		self._cleanup()
		self.supplier = make_supplier(self.SUPPLIER, "6", make_ruc(70000099)).name
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()
		self._cleanup()
		super().tearDown()

	def _cleanup(self):
		for name in frappe.get_all("Purchase Invoice", {"supplier": self.SUPPLIER}, pluck="name"):
			frappe.db.delete("Purchase Invoice Item", {"parent": name})
			frappe.db.delete("Purchase Taxes and Charges", {"parent": name})
			frappe.db.delete("Purchase Invoice", {"name": name})
		frappe.db.delete("Supplier", {"name": self.SUPPLIER})
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
				frappe.db.sql("select 1")  # the transaction has already read something
				barrier.wait(timeout=30)
				results.append(target(index))
			except Exception as exc:
				frappe.db.rollback()
				errors.append(exc)
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=120)
		return results, errors

	def drafts(self, count):
		"""Named one at a time: Frappe's naming series is not what is tested here.

		(On MariaDB 11.8 Frappe itself refuses all but one of several documents of
		the same naming series created at the same instant.)
		"""
		names = [
			make_purchase_invoice(
				self.supplier, pe_comprobante_type="01", pe_series="F001", pe_number=str(900 + n)
			).name
			for n in range(count)
		]
		frappe.db.commit()
		return names

	def correct_at_once(self, drafts, numbers):
		"""Save each draft with its new number, all at the same time."""

		def correct(index):
			invoice = frappe.get_doc("Purchase Invoice", drafts[index])
			invoice.pe_number = numbers[index]
			invoice.save()
			frappe.db.commit()
			return invoice.pe_voucher_number

		# Each save pauses right after its check, so that they always overlap.
		sync_bill_no = purchase_invoice._sync_bill_no

		def slow_sync_bill_no(doc):
			time.sleep(0.5)
			sync_bill_no(doc)

		with patch.object(purchase_invoice, "_sync_bill_no", slow_sync_bill_no):
			return self._run_threads(correct, len(drafts))

	def test_the_same_document_is_booked_once(self):
		drafts = self.drafts(4)
		results, errors = self.correct_at_once(drafts, ["999"] * 4)
		self.assertEqual(results, ["F001-00000999"], errors)
		# each waited for the one before and then saw it
		self.assertEqual([type(error) for error in errors], [DuplicateVoucherError] * 3)
		frappe.db.rollback()
		stored = frappe.get_all(
			"Purchase Invoice", {"supplier": self.supplier, "pe_number": "00000999"}, pluck="name"
		)
		self.assertEqual(len(stored), 1)

	def test_different_documents_of_one_supplier_are_all_booked(self):
		"""The check locks only the rows of the same document: no deadlock between drafts."""
		drafts = self.drafts(4)
		results, errors = self.correct_at_once(drafts, [str(800 + n) for n in range(4)])
		self.assertEqual(errors, [])
		self.assertEqual(sorted(results), [f"F001-{800 + n:08d}" for n in range(4)])
