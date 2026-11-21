# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Annexure A, module 3 (comprobante fields and rules) on Sales Invoices."""

from unittest.mock import patch

import frappe
from frappe.utils import flt

from erpnext_peru.overrides.common import ComprobanteError, IdentityDocumentError
from erpnext_peru.tests.utils import (
	FOREIGN_COMPANY,
	PERU_COMPANY,
	PeruTestCase,
	_ensure_company,
	make_customer,
	make_return,
	make_ruc,
	make_sales_invoice,
	make_series,
)


class SalesInvoiceCase(PeruTestCase):
	def setUp(self):
		super().setUp()
		self.ruc_customer = make_customer("_Test PE SI RUC", "6", make_ruc(30000001)).name
		self.dni_customer = make_customer("_Test PE SI DNI", "1", "40000001").name
		self.anonymous = make_customer("_Test PE SI Anonymous").name
		make_series("01", "F001")
		make_series("03", "B001")

	def gl_entries(self, invoice):
		return frappe.get_all(
			"GL Entry",
			filters={"voucher_no": invoice.name, "is_cancelled": 0},
			fields=["account", "debit", "credit"],
			order_by="account",
		)


class TestDefaultsAndNumbering(SalesInvoiceCase):
	def test_tx_uc_01_factura_to_ruc_customer(self):
		invoice = make_sales_invoice(self.ruc_customer, rate=1000)
		self.assertEqual(invoice.pe_comprobante_type, "01")  # defaulted from the RUC
		self.assertEqual(invoice.pe_series, "F001")  # the only enabled series
		self.assertFalse(invoice.pe_number)
		self.assertIsNone(invoice.pe_voucher_number)  # nothing assigned while draft

		invoice.submit()
		invoice.reload()
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.pe_number, 1)
		self.assertEqual(invoice.pe_voucher_number, "F001-00000001")
		self.assertEqual(invoice.pe_customer_identity_type, "6")
		self.assertEqual(invoice.pe_customer_identity_number, make_ruc(30000001))

	def test_accounting_is_not_altered_by_the_localization(self):
		"""The hooks only add identification data: amounts and ledger stay ERPNext's."""
		invoice = make_sales_invoice(self.ruc_customer, rate=1234.56, qty=3)
		invoice.submit()
		self.assertEqual(flt(invoice.grand_total, 2), 3703.68)
		entries = self.gl_entries(invoice)
		self.assertEqual(len(entries), 2)
		self.assertEqual(flt(sum(e.debit for e in entries), 2), 3703.68)
		self.assertEqual(flt(sum(e.credit for e in entries), 2), 3703.68)
		by_account = {e.account: e for e in entries}
		self.assertEqual(flt(by_account["Debtors - _TPE"].debit, 2), 3703.68)
		self.assertEqual(flt(by_account["Sales - _TPE"].credit, 2), 3703.68)

	def test_boleta_default_for_customer_without_ruc(self):
		invoice = make_sales_invoice(self.dni_customer)
		self.assertEqual(invoice.pe_comprobante_type, "03")
		self.assertEqual(invoice.pe_series, "B001")
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "B001-00000001")

	def test_numbers_are_consecutive_and_independent_per_series(self):
		numbers = []
		for _ in range(3):
			invoice = make_sales_invoice(self.ruc_customer)
			invoice.submit()
			numbers.append(invoice.pe_voucher_number)
		self.assertEqual(numbers, ["F001-00000001", "F001-00000002", "F001-00000003"])

		boleta = make_sales_invoice(self.dni_customer)
		boleta.submit()
		self.assertEqual(boleta.pe_voucher_number, "B001-00000001")

		make_series("01", "F002")
		other = make_sales_invoice(self.ruc_customer, pe_series="F002")
		other.submit()
		self.assertEqual(other.pe_voucher_number, "F002-00000001")

		again = make_sales_invoice(self.ruc_customer, pe_series="F001")
		again.submit()
		self.assertEqual(again.pe_voucher_number, "F001-00000004")
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", "01-F001-" + PERU_COMPANY, "current_number"), 4
		)

	def test_numbering_continues_from_a_previous_system(self):
		make_series("01", "F010", current_number=1534)
		invoice = make_sales_invoice(self.ruc_customer, pe_series="F010")
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "F010-00001535")

	def test_number_typed_by_a_user_is_ignored(self):
		invoice = make_sales_invoice(self.ruc_customer, pe_number=999, pe_voucher_number="F001-00000999")
		self.assertFalse(invoice.pe_number)
		self.assertIsNone(invoice.pe_voucher_number)
		invoice.pe_number = 500
		invoice.pe_voucher_number = "F001-00000500"
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "F001-00000001")

	def test_submitting_directly_without_saving_a_draft(self):
		invoice = make_sales_invoice(self.ruc_customer)
		copy = frappe.copy_doc(invoice)
		copy.pe_number = 77  # as an amended copy made by the browser would carry
		copy.pe_voucher_number = "F001-00000077"
		copy.submit()  # insert + submit in one step
		self.assertEqual(copy.pe_voucher_number, "F001-00000001")

	def test_failed_submission_does_not_consume_a_number(self):
		invoice = make_sales_invoice(self.ruc_customer)
		frappe.db.savepoint("before_failed_submit")
		from erpnext.accounts.doctype.sales_invoice import sales_invoice as module

		original = module.SalesInvoice.on_submit

		def boom(self_):
			# by now before_submit has run and the counter has been advanced
			self.assertEqual(self_.pe_voucher_number, "F001-00000001")
			raise frappe.ValidationError("simulated failure after the number was allocated")

		module.SalesInvoice.on_submit = boom
		try:
			with self.assertRaises(frappe.ValidationError):
				invoice.submit()
		finally:
			module.SalesInvoice.on_submit = original
		# what a web request does after an exception
		frappe.db.rollback(save_point="before_failed_submit")
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", "01-F001-" + PERU_COMPANY, "current_number"), 0
		)
		retry = frappe.get_doc("Sales Invoice", invoice.name)
		retry.submit()
		self.assertEqual(retry.pe_voucher_number, "F001-00000001")

	def test_cancelled_voucher_keeps_its_number_and_amendment_gets_a_new_one(self):
		first = make_sales_invoice(self.ruc_customer)
		first.submit()
		first.cancel()
		first.reload()
		self.assertEqual(first.docstatus, 2)
		self.assertEqual(first.pe_voucher_number, "F001-00000001")  # still on record

		amended = frappe.copy_doc(first)
		amended.docstatus = 0  # copy_doc keeps the docstatus when running tests
		amended.amended_from = first.name
		# the browser keeps type and series on an amended form
		amended.pe_comprobante_type = first.pe_comprobante_type
		amended.pe_series = first.pe_series
		# the browser copies read-only fields into the amended form
		amended.pe_number = first.pe_number
		amended.pe_voucher_number = first.pe_voucher_number
		amended.insert()
		self.assertIsNone(amended.pe_voucher_number)
		amended.submit()
		self.assertEqual(amended.pe_voucher_number, "F001-00000002")

	def test_issued_voucher_cannot_be_deleted(self):
		invoice = make_sales_invoice(self.ruc_customer)
		invoice.submit()
		invoice.cancel()
		with self.assertRaises(ComprobanteError):
			frappe.delete_doc("Sales Invoice", invoice.name, force=True)
		self.assertTrue(frappe.db.exists("Sales Invoice", invoice.name))

	def test_draft_can_be_deleted(self):
		invoice = make_sales_invoice(self.ruc_customer)
		frappe.delete_doc("Sales Invoice", invoice.name)
		self.assertFalse(frappe.db.exists("Sales Invoice", invoice.name))

	def test_voucher_fields_cannot_be_changed_after_submit(self):
		invoice = make_sales_invoice(self.ruc_customer)
		invoice.submit()
		for field, value in (
			("pe_voucher_number", "F001-00000009"),
			("pe_number", 9),
			("pe_series", "F002"),
			("pe_comprobante_type", "03"),
		):
			doc = frappe.get_doc("Sales Invoice", invoice.name)
			doc.set(field, value)
			with self.subTest(field=field), self.assertRaises(frappe.UpdateAfterSubmitError):
				doc.save()

	def test_validate_never_touches_an_issued_voucher(self):
		"""Even if other code runs the validate hook on a submitted invoice."""
		from erpnext_peru.overrides import sales_invoice as hooks

		invoice = make_sales_invoice(self.ruc_customer)
		invoice.submit()
		for docstatus_action in ("submitted", "cancelled"):
			if docstatus_action == "cancelled":
				invoice.cancel()
			doc = frappe.get_doc("Sales Invoice", invoice.name)
			frappe.db.set_value("Customer", self.ruc_customer, "pe_identity_number", make_ruc(30000077))
			hooks.validate(doc)
			with self.subTest(state=docstatus_action):
				self.assertEqual(doc.pe_number, 1)
				self.assertEqual(doc.pe_voucher_number, "F001-00000001")
				self.assertEqual(doc.pe_customer_identity_number, make_ruc(30000001))

	def test_type_follows_a_change_of_customer(self):
		invoice = make_sales_invoice(self.dni_customer)
		self.assertEqual((invoice.pe_comprobante_type, invoice.pe_series), ("03", "B001"))
		invoice.customer = self.ruc_customer
		invoice.save()
		self.assertEqual((invoice.pe_comprobante_type, invoice.pe_series), ("01", "F001"))
		invoice.customer = self.anonymous
		invoice.save()
		self.assertEqual((invoice.pe_comprobante_type, invoice.pe_series), ("03", "B001"))

	def test_type_follows_a_customer_changed_just_before_submission(self):
		"""The point of sale saves the draft at checkout and lets the cashier edit the cart."""
		invoice = make_sales_invoice(self.ruc_customer)
		invoice.customer = self.dni_customer
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "B001-00000001")

	def test_a_type_chosen_by_hand_is_kept_when_the_customer_changes(self):
		other_ruc = make_customer("_Test PE SI RUC 2", "6", make_ruc(30000002)).name
		invoice = make_sales_invoice(self.ruc_customer, pe_comprobante_type="03")
		invoice.customer = other_ruc
		invoice.save()
		self.assertEqual(invoice.pe_comprobante_type, "03")

	def test_a_type_changed_with_the_customer_is_kept(self):
		invoice = make_sales_invoice(self.ruc_customer, pe_comprobante_type="03")
		invoice.update({"customer": self.dni_customer, "pe_comprobante_type": "01", "pe_series": "F001"})
		invoice.save()
		self.assertEqual(invoice.pe_comprobante_type, "01")  # the user's choice, refused on submit
		with self.assertRaises(ComprobanteError):
			invoice.submit()

	def test_boleta_to_a_ruc_customer_warns(self):
		frappe.clear_messages()
		make_sales_invoice(self.ruc_customer)  # Factura: no warning
		self.assertNotIn("Boleta", " ".join(str(m) for m in frappe.get_message_log()))
		make_sales_invoice(self.ruc_customer, pe_comprobante_type="03")
		self.assertIn("Boleta", " ".join(str(m) for m in frappe.get_message_log()))


class TestSeriesRules(SalesInvoiceCase):
	def test_series_is_required_when_several_exist(self):
		make_series("01", "F002")
		invoice = make_sales_invoice(self.ruc_customer)
		self.assertIsNone(invoice.pe_series)  # ambiguous: nothing is guessed
		with self.assertRaises(ComprobanteError) as ctx:
			invoice.submit()
		self.assertIn("F001", str(ctx.exception))
		self.assertIn("F002", str(ctx.exception))

	def test_no_series_registered(self):
		frappe.delete_doc("SUNAT Voucher Series", "03-B001-" + PERU_COMPANY)
		invoice = make_sales_invoice(self.dni_customer)
		with self.assertRaises(ComprobanteError):
			invoice.submit()

	def test_unregistered_series_is_blocked(self):
		invoice = make_sales_invoice(self.ruc_customer, pe_series="F999")
		with self.assertRaises(frappe.ValidationError) as ctx:
			invoice.submit()
		self.assertIn("F999", str(ctx.exception))

	def test_disabled_series_is_blocked(self):
		frappe.db.set_value("SUNAT Voucher Series", "01-F001-" + PERU_COMPANY, "enabled", 0)
		invoice = make_sales_invoice(self.ruc_customer, pe_series="F001")
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()

	def test_series_letter_must_match_the_type(self):
		with self.assertRaises(ComprobanteError):
			make_sales_invoice(self.ruc_customer, pe_comprobante_type="01", pe_series="B001")
		with self.assertRaises(ComprobanteError):
			make_sales_invoice(self.dni_customer, pe_comprobante_type="03", pe_series="F001")

	def test_malformed_series(self):
		for series in ("F01", "0001", "F0001", "E001"):
			with self.subTest(series=series), self.assertRaises(ComprobanteError):
				make_sales_invoice(self.ruc_customer, pe_series=series)

	def test_series_is_normalized(self):
		invoice = make_sales_invoice(self.ruc_customer, pe_series=" f001 ")
		self.assertEqual(invoice.pe_series, "F001")

	def test_series_follows_a_change_of_type(self):
		invoice = make_sales_invoice(self.ruc_customer, pe_comprobante_type="03")
		self.assertEqual(invoice.pe_series, "B001")
		invoice.pe_comprobante_type = "01"
		invoice.save()
		self.assertEqual(invoice.pe_series, "F001")

	def test_after_a_change_of_type_several_series_are_not_guessed(self):
		make_series("01", "F002")
		invoice = make_sales_invoice(self.ruc_customer, pe_comprobante_type="03")
		invoice.pe_comprobante_type = "01"
		invoice.save()
		self.assertIsNone(invoice.pe_series)

	def test_a_series_typed_with_the_new_type_is_still_checked(self):
		make_series("03", "B002")
		invoice = make_sales_invoice(self.ruc_customer, pe_comprobante_type="03")
		invoice.update({"pe_comprobante_type": "01", "pe_series": "B002"})
		with self.assertRaises(ComprobanteError):
			invoice.save()

	def test_a_wrong_series_without_a_change_of_type_is_still_refused(self):
		invoice = make_sales_invoice(self.ruc_customer)
		invoice.pe_series = "B001"
		with self.assertRaises(ComprobanteError):
			invoice.save()

	def test_series_of_another_company_is_not_used(self):
		frappe.delete_doc("SUNAT Voucher Series", "01-F001-" + PERU_COMPANY)
		invoice = make_sales_invoice(self.ruc_customer)
		self.assertIsNone(invoice.pe_series)


class TestCustomerIdentityRules(SalesInvoiceCase):
	def test_tx_cc_02_factura_to_dni_customer_is_blocked(self):
		invoice = make_sales_invoice(self.dni_customer, pe_comprobante_type="01")
		with self.assertRaises(ComprobanteError) as ctx:
			invoice.submit()
		self.assertIn("RUC", str(ctx.exception))
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, "docstatus"), 0)

	def test_factura_to_anonymous_customer_is_blocked(self):
		invoice = make_sales_invoice(self.anonymous, pe_comprobante_type="01")
		with self.assertRaises(ComprobanteError):
			invoice.submit()

	def test_factura_to_non_domiciled_customer_is_allowed(self):
		foreign = make_customer("_Test PE SI Foreign", "0", "US-998877").name
		invoice = make_sales_invoice(foreign, pe_comprobante_type="01")
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "F001-00000001")

	def test_boleta_to_ruc_customer_is_allowed(self):
		invoice = make_sales_invoice(self.ruc_customer, pe_comprobante_type="03")
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "B001-00000001")

	def test_boleta_up_to_700_without_identity(self):
		for rate in (0.10, 699.99, 700):
			with self.subTest(rate=rate):
				invoice = make_sales_invoice(self.anonymous, rate=rate)
				self.assertEqual(invoice.pe_comprobante_type, "03")
				invoice.submit()
				self.assertEqual(invoice.docstatus, 1)

	def test_tx_cc_01_boleta_above_700_without_identity_is_blocked(self):
		for rate in (700.01, 701, 5000):
			with self.subTest(rate=rate):
				invoice = make_sales_invoice(self.anonymous, rate=rate)
				with self.assertRaises(ComprobanteError) as ctx:
					invoice.submit()
				self.assertIn("700", str(ctx.exception))
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", "03-B001-" + PERU_COMPANY, "current_number"), 0
		)

	def test_boleta_above_700_with_identity(self):
		invoice = make_sales_invoice(self.dni_customer, rate=5000)
		invoice.submit()
		self.assertEqual(invoice.pe_customer_identity_type, "1")
		self.assertEqual(invoice.pe_customer_identity_number, "40000001")

	def test_boleta_threshold_uses_the_total_of_the_document(self):
		# 2 x 350.01 = 700.02
		invoice = make_sales_invoice(self.anonymous, rate=350.01, qty=2)
		with self.assertRaises(ComprobanteError):
			invoice.submit()
		ok = make_sales_invoice(self.anonymous, rate=350, qty=2)
		ok.submit()

	def test_boleta_threshold_in_foreign_currency_is_measured_in_soles(self):
		# USD 190 x 3.70 = S/ 703.00 -> above ; USD 189 x 3.70 = S/ 699.30 -> below
		above = make_sales_invoice(self.anonymous, rate=190, currency="USD", conversion_rate=3.70)
		self.assertEqual(flt(above.base_grand_total, 2), 703.00)
		with self.assertRaises(ComprobanteError):
			above.submit()
		below = make_sales_invoice(self.anonymous, rate=189, currency="USD", conversion_rate=3.70)
		self.assertEqual(flt(below.base_grand_total, 2), 699.30)
		below.submit()

	def test_identity_snapshot_follows_the_customer_until_submission(self):
		invoice = make_sales_invoice(self.anonymous, rate=900)
		self.assertIsNone(invoice.pe_customer_identity_type)
		customer = frappe.get_doc("Customer", self.anonymous)
		customer.pe_identity_type = "1"
		customer.pe_identity_number = "40000099"
		customer.save()
		invoice.reload()
		invoice.submit()
		self.assertEqual(invoice.pe_customer_identity_number, "40000099")

		# later corrections of the master do not rewrite the issued voucher
		customer.reload()
		customer.pe_identity_number = "40000098"
		customer.save()
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", invoice.name, "pe_customer_identity_number"), "40000099"
		)

	def test_company_without_ruc_cannot_issue(self):
		frappe.db.set_value("Company", PERU_COMPANY, "tax_id", None)
		frappe.clear_cache(doctype="Company")
		invoice = make_sales_invoice(self.ruc_customer)
		with self.assertRaises(ComprobanteError):
			invoice.submit()

	def test_company_with_invalid_ruc_cannot_issue(self):
		frappe.db.set_value("Company", PERU_COMPANY, "tax_id", "20123456780")
		frappe.clear_cache(doctype="Company")
		invoice = make_sales_invoice(self.ruc_customer)
		with self.assertRaises(IdentityDocumentError):
			invoice.submit()


class TestTypeRules(SalesInvoiceCase):
	def test_only_issuable_types(self):
		for comprobante_type in ("09", "12", "14"):
			with self.subTest(comprobante_type=comprobante_type), self.assertRaises(ComprobanteError):
				make_sales_invoice(self.ruc_customer, pe_comprobante_type=comprobante_type)

	def test_unknown_type(self):
		with self.assertRaises(frappe.ValidationError):
			make_sales_invoice(self.ruc_customer, pe_comprobante_type="99")

	def test_disabled_type(self):
		frappe.db.set_value("SUNAT Comprobante Type", "03", "enabled", 0)
		with self.assertRaises(ComprobanteError):
			make_sales_invoice(self.dni_customer)

	def test_plain_invoice_cannot_be_a_note(self):
		for comprobante_type in ("07", "08"):
			with self.subTest(comprobante_type=comprobante_type), self.assertRaises(ComprobanteError):
				make_sales_invoice(self.ruc_customer, pe_comprobante_type=comprobante_type)

	def test_note_fields_are_cleared_on_plain_invoices(self):
		invoice = make_sales_invoice(
			self.ruc_customer,
			pe_credit_note_reason="01",
			pe_debit_note_reason="01",
			pe_original_type="01",
			pe_original_voucher_number="F001-00000001",
		)
		for field in (
			"pe_credit_note_reason",
			"pe_debit_note_reason",
			"pe_original_type",
			"pe_original_voucher_number",
		):
			self.assertIsNone(invoice.get(field), field)


class TestCreditNotes(SalesInvoiceCase):
	def setUp(self):
		super().setUp()
		make_series("07", "FC01")
		make_series("07", "BC01")
		self.factura = make_sales_invoice(self.ruc_customer, rate=500)
		self.factura.submit()

	def test_tx_uc_03_credit_note_references_the_original_factura(self):
		note = make_return(self.factura, pe_credit_note_reason="06")
		self.assertEqual(note.pe_comprobante_type, "07")
		self.assertEqual(note.pe_original_type, "01")
		self.assertEqual(note.pe_original_voucher_number, "F001-00000001")
		self.assertEqual(note.pe_series, "FC01")  # the F series, not the B one
		note.submit()
		note.reload()
		self.assertEqual(note.pe_voucher_number, "FC01-00000001")
		self.assertEqual(note.pe_credit_note_reason, "06")
		self.assertEqual(flt(note.grand_total, 2), -500.00)
		# numbering of facturas is untouched
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", "01-F001-" + PERU_COMPANY, "current_number"), 1
		)

	def test_credit_note_requires_a_reason(self):
		note = make_return(self.factura)
		with self.assertRaises(ComprobanteError) as ctx:
			note.submit()
		self.assertIn("09", str(ctx.exception))

	def test_credit_note_reason_must_exist(self):
		with self.assertRaises(frappe.ValidationError):
			make_return(self.factura, pe_credit_note_reason="99")

	def test_credit_note_must_be_type_07(self):
		with self.assertRaises(ComprobanteError):
			make_return(self.factura, pe_comprobante_type="01", pe_credit_note_reason="01")

	def test_the_linked_invoice_overrides_a_typed_reference(self):
		note = make_return(
			self.factura,
			pe_credit_note_reason="01",
			pe_original_type="03",
			pe_original_voucher_number="B001-00000042",
		)
		self.assertEqual(note.pe_original_type, "01")
		self.assertEqual(note.pe_original_voucher_number, "F001-00000001")

	def test_credit_note_series_must_match_the_original(self):
		with self.assertRaises(ComprobanteError):
			make_return(self.factura, pe_credit_note_reason="01", pe_series="BC01")

	def test_credit_note_on_a_large_boleta_counts_its_amount(self):
		"""Credit notes have negative totals: S/ -800 is above the S/ 700 threshold."""
		boleta = make_sales_invoice(self.dni_customer, rate=800)
		boleta.submit()
		frappe.db.set_value(
			"Customer", self.dni_customer, {"pe_identity_type": None, "pe_identity_number": None}
		)
		note = make_return(boleta, pe_credit_note_reason="07")
		with self.assertRaises(ComprobanteError):
			note.submit()

	def test_credit_note_on_a_boleta_uses_the_b_series(self):
		boleta = make_sales_invoice(self.dni_customer, rate=100)
		boleta.submit()
		note = make_return(boleta, pe_credit_note_reason="07")
		self.assertEqual(note.pe_original_type, "03")
		self.assertEqual(note.pe_series, "BC01")
		note.submit()
		self.assertEqual(note.pe_voucher_number, "BC01-00000001")

	def test_debit_reason_is_cleared_on_a_credit_note(self):
		note = make_return(self.factura, pe_credit_note_reason="01", pe_debit_note_reason="02")
		self.assertIsNone(note.pe_debit_note_reason)

	def test_credit_note_for_a_voucher_issued_before_this_system(self):
		"""No linked invoice: the user types the modified voucher."""
		note = make_sales_invoice(
			self.ruc_customer,
			qty=-1,
			is_return=1,
			pe_credit_note_reason="01",
			pe_original_type="01",
			pe_original_voucher_number="f001-77",
		)
		self.assertEqual(note.pe_comprobante_type, "07")
		self.assertEqual(note.pe_original_voucher_number, "F001-00000077")
		self.assertEqual(note.pe_series, "FC01")
		note.submit()
		self.assertEqual(note.pe_voucher_number, "FC01-00000001")

	def test_series_follows_a_corrected_modified_type(self):
		note = make_sales_invoice(
			self.dni_customer,
			qty=-1,
			is_return=1,
			pe_credit_note_reason="01",
			pe_original_type="01",
			pe_original_voucher_number="F001-77",
		)
		self.assertEqual(note.pe_series, "FC01")
		note.update({"pe_original_type": "03", "pe_original_voucher_number": "B001-77"})
		note.save()
		self.assertEqual(note.pe_series, "BC01")

	def test_note_may_modify_a_paper_voucher(self):
		note = make_sales_invoice(
			self.ruc_customer,
			qty=-1,
			is_return=1,
			pe_credit_note_reason="01",
			pe_original_type="01",
			pe_original_voucher_number="0001-123",
		)
		note.submit()
		self.assertEqual(note.pe_original_voucher_number, "0001-00000123")

	def test_credit_note_without_reference_is_blocked(self):
		note = make_sales_invoice(self.ruc_customer, qty=-1, is_return=1, pe_credit_note_reason="01")
		with self.assertRaises(ComprobanteError):
			note.submit()
		with self.assertRaises(ComprobanteError):
			make_sales_invoice(
				self.ruc_customer,
				qty=-1,
				is_return=1,
				pe_credit_note_reason="01",
				pe_original_type="01",
				pe_original_voucher_number="garbage",
			)

	def test_note_can_only_modify_factura_or_boleta(self):
		with self.assertRaises(ComprobanteError):
			make_sales_invoice(
				self.ruc_customer,
				qty=-1,
				is_return=1,
				pe_credit_note_reason="01",
				pe_original_type="07",
				pe_original_voucher_number="FC01-1",
			)

	def test_credit_note_on_a_factura_requires_the_ruc(self):
		note = make_sales_invoice(
			self.dni_customer,
			qty=-1,
			is_return=1,
			pe_credit_note_reason="01",
			pe_original_type="01",
			pe_original_voucher_number="F001-5",
		)
		with self.assertRaises(ComprobanteError):
			note.submit()


class TestDebitNotes(SalesInvoiceCase):
	def setUp(self):
		super().setUp()
		make_series("08", "FD01")
		self.factura = make_sales_invoice(self.ruc_customer, rate=500)
		self.factura.submit()

	def make_debit_note(self, **kwargs):
		values = {"is_debit_note": 1, "return_against": self.factura.name, "rate": 50}
		values.update(kwargs)
		return make_sales_invoice(self.ruc_customer, **values)

	def test_debit_note(self):
		note = self.make_debit_note(pe_debit_note_reason="01")
		self.assertEqual(note.pe_comprobante_type, "08")
		self.assertEqual(note.pe_original_type, "01")
		self.assertEqual(note.pe_original_voucher_number, "F001-00000001")
		self.assertEqual(note.pe_series, "FD01")
		note.submit()
		self.assertEqual(note.pe_voucher_number, "FD01-00000001")

	def test_debit_note_requires_a_reason(self):
		note = self.make_debit_note()
		with self.assertRaises(ComprobanteError) as ctx:
			note.submit()
		self.assertIn("10", str(ctx.exception))

	def test_credit_reason_is_cleared_on_a_debit_note(self):
		note = self.make_debit_note(pe_debit_note_reason="02", pe_credit_note_reason="06")
		self.assertIsNone(note.pe_credit_note_reason)

	def test_note_on_a_boleta_above_700_must_identify_the_customer(self):
		"""A note follows the rules of the voucher it modifies, Boleta included."""
		make_series("08", "BD01")
		boleta = make_sales_invoice(self.anonymous, rate=600)
		boleta.submit()
		values = {"is_debit_note": 1, "return_against": boleta.name, "pe_debit_note_reason": "02"}
		small = make_sales_invoice(self.anonymous, rate=700, **values)
		small.submit()  # exactly S/ 700.00: allowed
		large = make_sales_invoice(self.anonymous, rate=700.01, **values)
		self.assertEqual(large.pe_original_type, "03")
		with self.assertRaises(ComprobanteError) as raised:
			large.submit()
		self.assertIn("700.00", str(raised.exception))

	def test_debit_note_must_be_type_08(self):
		with self.assertRaises(ComprobanteError):
			self.make_debit_note(pe_comprobante_type="01", pe_debit_note_reason="01")

	def test_a_debit_note_modifies_only_an_invoice_of_its_own_customer(self):
		"""ERPNext checks "Return Against" for returns only, not for debit notes."""
		other = make_sales_invoice(make_customer("_Test PE SI RUC 3", "6", make_ruc(30000003)).name)
		other.submit()
		with self.assertRaisesRegex(ComprobanteError, "same customer"):
			self.make_debit_note(return_against=other.name, pe_debit_note_reason="02")

	def test_a_debit_note_modifies_only_an_invoice_of_its_own_company(self):
		foreign = make_sales_invoice(self.ruc_customer, company=FOREIGN_COMPANY)
		foreign.submit()
		with self.assertRaisesRegex(ComprobanteError, "same company"):
			self.make_debit_note(return_against=foreign.name, pe_debit_note_reason="02")

	def test_a_debit_note_modifies_only_an_issued_invoice(self):
		draft = make_sales_invoice(self.ruc_customer)
		with self.assertRaisesRegex(ComprobanteError, "not submitted"):
			self.make_debit_note(return_against=draft.name, pe_debit_note_reason="02")


class TestScope(SalesInvoiceCase):
	def test_other_countries_are_untouched(self):
		customer = make_customer("_Test PE Foreign Co Customer").name
		invoice = make_sales_invoice(
			customer,
			rate=5000,
			company=FOREIGN_COMPANY,
			pe_comprobante_type="09",
			pe_series="zzz",
			pe_number=5,
			pe_voucher_number="anything",
		)
		# nothing is validated, defaulted or cleared
		self.assertEqual(invoice.pe_comprobante_type, "09")
		self.assertEqual(invoice.pe_series, "zzz")
		self.assertEqual(invoice.pe_voucher_number, "anything")
		plain = make_sales_invoice(customer, rate=5000, company=FOREIGN_COMPANY)
		plain.submit()
		self.assertEqual(plain.docstatus, 1)
		self.assertIsNone(plain.pe_comprobante_type)
		self.assertIsNone(plain.pe_voucher_number)

	def test_opening_invoices_are_exempt(self):
		invoice = make_sales_invoice(self.anonymous, rate=9000, is_opening="Yes")
		invoice.items[0].income_account = frappe.db.get_value(
			"Account", {"company": PERU_COMPANY, "account_name": "Temporary Opening"}, "name"
		)
		invoice.save()
		self.assertIsNone(invoice.pe_comprobante_type)
		invoice.submit()
		self.assertEqual(invoice.docstatus, 1)
		self.assertIsNone(invoice.pe_voucher_number)
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", "03-B001-" + PERU_COMPANY, "current_number"), 0
		)


class TestMergedPosInvoices(SalesInvoiceCase):
	"""Closing a POS shift merges its sales into one Sales Invoice (is_consolidated)."""

	def submitted_pos_invoice(self, name):
		"""A submitted POS Invoice record. Only its existence and status matter here."""
		doc = frappe.get_doc(
			{
				"doctype": "POS Invoice",
				"company": PERU_COMPANY,
				"customer": self.anonymous,
				"posting_date": frappe.utils.today(),
				"docstatus": 1,
			}
		)
		doc.name = name
		doc.db_insert()
		return name

	def build(self, pos_invoices, rate=50, qty=30):
		"""A draft shaped like the one ERPNext's POS Invoice Merge Log creates."""
		template = make_sales_invoice(self.anonymous, rate=rate, qty=qty)
		invoice = frappe.copy_doc(template, ignore_no_copy=False)
		template.delete()
		invoice.is_consolidated = 1
		invoice.flags.is_consolidated = True
		row = invoice.items[0].as_dict(no_default_fields=True)
		invoice.items = []
		for name in pos_invoices:
			invoice.append("items", {**row, "pos_invoice": name})
		return invoice

	def test_merged_invoice_of_a_shift_is_not_a_comprobante(self):
		"""S/ 3,000 to the walk-in customer: as a Boleta it would be refused."""
		pos = [self.submitted_pos_invoice("_TEST-PE-POS-1"), self.submitted_pos_invoice("_TEST-PE-POS-2")]
		invoice = self.build(pos)
		invoice.insert()
		invoice.submit()
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(flt(invoice.base_grand_total), 3000)
		self.assertIsNone(invoice.pe_comprobante_type)
		self.assertIsNone(invoice.pe_voucher_number)
		self.assertEqual(
			frappe.db.get_value("SUNAT Voucher Series", "03-B001-" + PERU_COMPANY, "current_number"), 0
		)

	def test_the_flag_alone_does_not_exempt_an_invoice(self):
		"""An API client could set is_consolidated: the rules still apply then.

		(A POS Invoice that does not exist is already refused by link validation.)
		"""
		pos = self.submitted_pos_invoice("_TEST-PE-POS-3")
		cases = {
			"no POS Invoice on the items": [None],
			"one item without a POS Invoice": [pos, None],
		}
		for label, names in cases.items():
			with self.subTest(label):
				invoice = self.build(names)
				invoice.insert()
				self.assertEqual(invoice.pe_comprobante_type, "03")
				with self.assertRaises(ComprobanteError):
					invoice.submit()  # anonymous Boleta above S/ 700

	def test_draft_pos_invoice_does_not_exempt(self):
		submitted = self.submitted_pos_invoice("_TEST-PE-POS-4")
		draft = self.submitted_pos_invoice("_TEST-PE-POS-5")
		frappe.db.set_value("POS Invoice", draft, "docstatus", 0)
		for names in ([draft], [submitted, draft]):
			with self.subTest(names=names):
				invoice = self.build(names)
				invoice.insert()
				self.assertEqual(invoice.pe_comprobante_type, "03")


class TestPosReturns(SalesInvoiceCase):
	"""A return made at the point of sale: its screen has no field for the reason."""

	def setUp(self):
		super().setUp()
		make_series("07", "BC01")
		self.boleta = make_sales_invoice(self.dni_customer, rate=100, qty=3)
		self.boleta.submit()

	def pos_return(self, qty=None, reason=None, is_pos=1):
		"""A draft return as the point of sale saves it (validate only)."""
		from erpnext_peru.overrides import sales_invoice

		note = make_return(self.boleta, pe_credit_note_reason="07")  # a valid draft first
		note.pe_credit_note_reason = reason
		note.is_pos = is_pos
		if qty is not None:
			self.set_qty(note, qty)
		sales_invoice.validate(note)
		return note

	def set_qty(self, note, qty):
		note.items[0].qty = note.items[0].stock_qty = -qty

	def submit(self, note):
		"""The app's submission hook, with the number allocation stubbed out."""
		from erpnext_peru.overrides import sales_invoice

		with patch.object(sales_invoice, "allocate_next_number", return_value=1):
			sales_invoice.before_submit(note)
		return note

	def test_returning_everything_is_a_total_return(self):
		self.assertEqual(self.submit(self.pos_return()).pe_credit_note_reason, "06")

	def test_returning_part_is_a_return_by_item(self):
		self.assertEqual(self.submit(self.pos_return(qty=1)).pe_credit_note_reason, "07")

	def test_the_reason_is_not_set_on_save(self):
		self.assertIsNone(self.pos_return().pe_credit_note_reason)

	def test_the_cart_as_submitted_decides(self):
		"""The cashier goes to the payment (the draft is saved), edits the cart, then pays."""
		from erpnext_peru.overrides import sales_invoice

		note = self.pos_return()  # saved with all 3 units
		self.set_qty(note, 1)
		sales_invoice.validate(note)  # saved again with 1 unit
		self.assertEqual(self.submit(note).pe_credit_note_reason, "07")

	def test_a_reason_chosen_by_the_user_is_kept(self):
		self.assertEqual(self.submit(self.pos_return(reason="01")).pe_credit_note_reason, "01")

	def test_returns_outside_the_point_of_sale_still_need_a_reason(self):
		note = self.pos_return(is_pos=0)
		with self.assertRaisesRegex(ComprobanteError, "reason of the credit note"):
			self.submit(note)

	def test_without_the_original_sale_it_is_a_return_by_item(self):
		from erpnext_peru.overrides.sales_invoice import _pos_return_reason

		note = frappe._dict(return_against=None, items=[])
		self.assertEqual(_pos_return_reason(note), "07")


class TestTotalInSoles(SalesInvoiceCase):
	"""The S/ 700 limit is in soles, whatever currency the company keeps its books in."""

	def total(self, company_currency="PEN", rate=None, **values):
		from erpnext_peru.overrides import sales_invoice

		doc = frappe._dict(company=PERU_COMPANY, posting_date="2026-11-18", **values)
		with (
			patch.object(sales_invoice, "_company_currency", return_value=company_currency),
			patch("erpnext.setup.utils.get_exchange_rate", return_value=rate) as get_rate,
		):
			total = sales_invoice._total_in_soles(doc)
		return total, get_rate

	def test_an_invoice_in_soles(self):
		total, get_rate = self.total(currency="PEN", grand_total=-118, base_grand_total=-31.89)
		self.assertEqual(total, 118)
		get_rate.assert_not_called()

	def test_a_company_in_soles(self):
		total, get_rate = self.total(currency="USD", grand_total=200, base_grand_total=740)
		self.assertEqual(total, 740)
		get_rate.assert_not_called()

	def test_a_company_in_dollars_converts_to_soles(self):
		total, get_rate = self.total(
			company_currency="USD", rate=3.7, currency="USD", grand_total=200, base_grand_total=200
		)
		self.assertEqual(total, 740)
		self.assertEqual(get_rate.call_args.args[:2], ("USD", "PEN"))

	def test_without_an_exchange_rate_the_boleta_is_refused(self):
		with self.assertRaisesRegex(ComprobanteError, "exchange rate"):
			self.total(company_currency="USD", rate=0, currency="USD", grand_total=200)


class TestAutoRepeat(SalesInvoiceCase):
	"""Auto Repeat copies an invoice without its series and can submit the copy at once."""

	def setUp(self):
		super().setUp()
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		# Customize Form > Sales Invoice > Allow Auto Repeat, as a company would do.
		make_property_setter("Sales Invoice", None, "allow_auto_repeat", 1, "Check", for_doctype=True)
		frappe.clear_cache(doctype="Sales Invoice")
		self.addCleanup(frappe.clear_cache, doctype="Sales Invoice")
		make_series("01", "F002")

	def repeat(self, invoice):
		schedule = frappe.get_doc(
			{
				"doctype": "Auto Repeat",
				"reference_doctype": "Sales Invoice",
				"reference_document": invoice.name,
				"frequency": "Monthly",
				"start_date": frappe.utils.today(),
				"submit_on_creation": 1,
			}
		).insert()
		return schedule.make_new_document()

	def test_the_repeated_invoice_keeps_the_series_of_the_original(self):
		original = make_sales_invoice(self.ruc_customer, pe_series="F002")
		original.submit()
		repeated = self.repeat(original)
		self.assertEqual(repeated.docstatus, 1)
		self.assertEqual(repeated.pe_voucher_number, "F002-00000002")

	def test_a_series_that_no_longer_fits_is_not_taken(self):
		original = make_sales_invoice(self.ruc_customer, pe_series="F002")
		original.submit()
		frappe.db.set_value("SUNAT Voucher Series", {"series": "F002"}, "enabled", 0)
		make_series("01", "F003")  # F001 and F003 left: a person has to choose
		with self.assertRaisesRegex(ComprobanteError, "Select the series"):
			self.repeat(original)


class TestTransactionDeletion(SalesInvoiceCase):
	"""ERPNext's "Delete Company Transactions" would wipe issued comprobantes."""

	def check(self, company):
		from erpnext_peru.overrides.transaction_deletion import before_submit

		before_submit(frappe._dict(company=company))

	def test_refused_once_a_comprobante_was_issued(self):
		frappe.db.sql(
			"update `tabSales Invoice` set pe_voucher_number = null where company = %s", PERU_COMPANY
		)
		self.check(PERU_COMPANY)  # nothing issued: allowed
		make_sales_invoice(self.dni_customer, rate=100).submit()
		with self.assertRaisesRegex(ComprobanteError, "cannot be deleted"):
			self.check(PERU_COMPANY)

	def test_other_countries_are_not_concerned(self):
		self.check(FOREIGN_COMPANY)

	def test_a_company_moved_out_of_peru_keeps_its_comprobantes(self):
		make_sales_invoice(self.dni_customer, rate=100).submit()
		frappe.db.set_value("Company", PERU_COMPANY, "country", "United States")
		frappe.clear_cache(doctype="Company")
		self.addCleanup(frappe.clear_cache, doctype="Company")
		with self.assertRaisesRegex(ComprobanteError, "cannot be deleted"):
			self.check(PERU_COMPANY)

	def test_the_tool_calls_it(self):
		hooks = frappe.get_hooks("doc_events", app_name="erpnext_peru")
		for event in ("before_submit", "before_update_after_submit"):
			self.assertEqual(
				hooks["Transaction Deletion Record"][event],
				["erpnext_peru.overrides.transaction_deletion.before_submit"],
			)


DELETION_COMPANY = "_Test PE Deletion SAC"


class TestTransactionDeletionTool(SalesInvoiceCase):
	"""ERPNext's own tool, on a company of its own: it deletes everything the company has.

	The deletion runs in the test's transaction and is rolled back with it.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_company(DELETION_COMPANY, "_TPD", "Peru", "PEN", make_ruc(60000009))
		frappe.db.commit()  # nosemgrep: fixture created once

	def deletion(self):
		record = frappe.get_doc(
			{
				"doctype": "Transaction Deletion Record",
				"company": DELETION_COMPANY,
				"process_in_single_transaction": 1,
			}
		).insert()
		record.generate_to_delete_list()
		record.reload()
		self.addCleanup(record._clear_deletion_cache)
		return record

	def to_delete(self, record):
		return [row.doctype_name for row in record.doctypes_to_delete]

	def test_series_are_kept(self):
		"""Its last number may continue a previous system's numbering before any voucher is issued here."""
		make_series("03", "B001", company=DELETION_COMPANY, current_number=1500)
		record = self.deletion()
		self.assertIn("Sales Invoice", self.to_delete(record))
		self.assertNotIn("SUNAT Voucher Series", self.to_delete(record))
		record.submit()
		self.assertEqual(record.reload().status, "Completed")
		self.assertEqual(
			frappe.db.get_value(
				"SUNAT Voucher Series", {"company": DELETION_COMPANY, "series": "B001"}, "current_number"
			),
			1500,
		)

	def test_series_added_to_the_list_by_hand_are_refused(self):
		record = self.deletion()
		record.append(
			"doctypes_to_delete", {"doctype_name": "SUNAT Voucher Series", "company_field": "company"}
		)
		record.save()
		with self.assertRaisesRegex(ComprobanteError, "keeps its last number"):
			record.submit()

	def test_a_retry_after_comprobantes_were_issued_is_refused(self):
		record = self.deletion()
		record.submit()
		record.db_set("status", "Failed")  # as if a step had failed
		make_series("03", "B001", company=DELETION_COMPANY)
		invoice = make_sales_invoice(self.dni_customer, rate=50, company=DELETION_COMPANY)
		invoice.submit()
		with self.assertRaisesRegex(ComprobanteError, "cannot be deleted"):
			record.start_deletion_tasks()
		self.assertTrue(frappe.db.exists("Sales Invoice", invoice.name))


class TestModifiedTypeField(PeruTestCase):
	def test_a_note_offers_only_factura_and_boleta(self):
		from erpnext_peru.setup.custom_fields import CUSTOM_FIELDS

		expected = [["SUNAT Comprobante Type", "name", "in", ["01", "03"]]]
		definition = next(f for f in CUSTOM_FIELDS["Sales Invoice"] if f["fieldname"] == "pe_original_type")
		field = frappe.get_meta("Sales Invoice").get_field("pe_original_type")
		for link_filters in (definition["link_filters"], field.link_filters):
			self.assertEqual(frappe.parse_json(link_filters), expected)
