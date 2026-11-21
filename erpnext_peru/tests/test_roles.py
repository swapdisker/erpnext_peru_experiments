# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""The daily work, done by the roles that do it rather than by Administrator.

The hooks read catalogues, series and the original invoice, and advance the
series counter, on behalf of users who cannot write those records themselves.
"""

import frappe
from frappe.desk.search import search_link

from erpnext_peru.tests.test_pcge_job import make_user
from erpnext_peru.tests.utils import (
	PeruTestCase,
	make_customer,
	make_purchase_invoice,
	make_return,
	make_ruc,
	make_sales_invoice,
	make_series,
	make_supplier,
)

SALES_USER = "_test_pe_sales_user@example.com"
ACCOUNTS_USER = "_test_pe_accounts_user@example.com"
PURCHASE_MASTER = "_test_pe_purchase_master@example.com"


class TestDailyRoles(PeruTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(SALES_USER, ["Sales User"])
		make_user(ACCOUNTS_USER, ["Accounts User"])
		make_user(PURCHASE_MASTER, ["Purchase Master Manager"])
		frappe.db.commit()  # nosemgrep: users created once

	def setUp(self):
		super().setUp()
		for comprobante_type, series in (("01", "F001"), ("03", "B001"), ("07", "FC01")):
			make_series(comprobante_type, series)

	def test_a_sales_user_registers_a_customer_with_a_ruc(self):
		frappe.set_user(SALES_USER)
		customer = make_customer("_Test PE Role Customer", "6", make_ruc(30000071))
		self.assertEqual(customer.tax_id, make_ruc(30000071))

	def test_a_purchase_master_registers_a_supplier_with_a_ruc(self):
		frappe.set_user(PURCHASE_MASTER)
		supplier = make_supplier("_Test PE Role Supplier", "6", make_ruc(30000072))
		self.assertEqual(supplier.tax_id, make_ruc(30000072))

	def test_an_accounts_user_issues_a_factura_and_its_credit_note(self):
		customer = make_customer("_Test PE Role Buyer", "6", make_ruc(30000073)).name
		frappe.set_user(ACCOUNTS_USER)
		invoice = make_sales_invoice(customer)
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "F001-00000001")
		note = make_return(invoice, pe_credit_note_reason="01")
		note.submit()
		self.assertEqual(note.pe_voucher_number, "FC01-00000001")
		self.assertEqual(note.pe_original_voucher_number, "F001-00000001")

	def test_an_accounts_user_registers_a_supplier_voucher(self):
		supplier = make_supplier("_Test PE Role Seller", "6", make_ruc(30000074)).name
		frappe.set_user(ACCOUNTS_USER)
		invoice = make_purchase_invoice(supplier, pe_comprobante_type="01", pe_series="F001", pe_number="9")
		invoice.submit()
		self.assertEqual(invoice.pe_voucher_number, "F001-00000009")

	def test_the_new_fields_can_be_filled_in_by_those_users(self):
		"""Link fields search their DocType with the user's own permissions."""
		searches = {
			ACCOUNTS_USER: (
				"SUNAT Comprobante Type",
				"SUNAT Credit Note Reason",
				"SUNAT Debit Note Reason",
				"SUNAT Identity Document Type",
				"Ubigeo",
			),
			SALES_USER: ("SUNAT Identity Document Type", "Ubigeo"),
			PURCHASE_MASTER: ("SUNAT Identity Document Type", "Ubigeo"),
		}
		for user, doctypes in searches.items():
			frappe.set_user(user)
			for doctype in doctypes:
				with self.subTest(user=user, doctype=doctype):
					self.assertTrue(search_link(doctype, ""), f"{user} finds nothing in {doctype}")
