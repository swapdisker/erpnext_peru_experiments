# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Annexure A, module 3 (comprobante fields and rules) on Sales Invoices."""

import frappe
from frappe.utils import flt

from erpnext_peru.overrides.common import ComprobanteError, IdentityDocumentError
from erpnext_peru.tests.utils import (
	FOREIGN_COMPANY,
	PERU_COMPANY,
	PeruTestCase,
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

	def test_debit_note_must_be_type_08(self):
		with self.assertRaises(ComprobanteError):
			self.make_debit_note(pe_comprobante_type="01", pe_debit_note_reason="01")


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
