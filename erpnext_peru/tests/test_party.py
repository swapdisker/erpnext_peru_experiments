# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Annexure A, module 2: Peru master data (RUC / DNI)."""

import frappe

from erpnext_peru.overrides.common import DuplicateIdentityError, IdentityDocumentError
from erpnext_peru.tests.utils import PeruTestCase, make_customer, make_ruc, make_supplier


class TestPartyIdentity(PeruTestCase):
	def test_md_uc_01_customer_with_valid_ruc(self):
		ruc = make_ruc(10000001)
		customer = make_customer("_Test PE RUC Customer", "6", ruc)
		customer.reload()
		self.assertEqual(customer.pe_identity_number, ruc)
		self.assertEqual(customer.tax_id, ruc)  # "RUC stored in Tax ID"

	def test_md_uc_02_individual_with_dni(self):
		customer = make_customer("_Test PE DNI Customer", "1", "01234567", customer_type="Individual")
		customer.reload()
		self.assertEqual(customer.pe_identity_number, "01234567")  # leading zero kept
		self.assertEqual(customer.tax_id, "01234567")

	def test_md_uc_03_foreign_supplier_with_passport(self):
		supplier = make_supplier("_Test PE Foreign Supplier", "7", "xk1234567")
		self.assertEqual(supplier.pe_identity_number, "XK1234567")
		other = make_supplier("_Test PE Foreign Supplier 2", "0", "12-3456789")
		self.assertEqual(other.pe_identity_number, "12-3456789")

	def test_md_cc_01_wrong_check_digit_is_blocked(self):
		ruc = make_ruc(10000002)
		wrong = ruc[:10] + str((int(ruc[10]) + 1) % 10)
		with self.assertRaises(IdentityDocumentError) as ctx:
			make_customer("_Test PE Bad RUC", "6", wrong)
		self.assertIn("check digit", str(ctx.exception))
		self.assertFalse(frappe.db.exists("Customer", "_Test PE Bad RUC"))

	def test_wrong_lengths_are_blocked(self):
		for identity_type, number in (
			("6", "2010004721"),
			("1", "1234567"),
			("1", "123456789"),
			("7", "A" * 13),
		):
			with self.subTest(number=number), self.assertRaises(IdentityDocumentError):
				make_customer(f"_Test PE Bad {number}", identity_type, number)

	def test_dni_is_not_accepted_as_ruc_and_viceversa(self):
		with self.assertRaises(IdentityDocumentError):
			make_customer("_Test PE Mixed 1", "6", "12345678")
		with self.assertRaises(IdentityDocumentError):
			make_customer("_Test PE Mixed 2", "1", make_ruc(10000003))

	def test_md_cc_02_same_ruc_as_customer_and_supplier_is_allowed(self):
		ruc = make_ruc(10000004)
		make_customer("_Test PE Both Roles", "6", ruc)
		supplier = make_supplier("_Test PE Both Roles", "6", ruc)
		self.assertEqual(supplier.pe_identity_number, ruc)

	def test_md_cc_03_duplicate_ruc_within_customers_is_blocked(self):
		ruc = make_ruc(10000005)
		first = make_customer("_Test PE Original", "6", ruc)
		with self.assertRaises(DuplicateIdentityError) as ctx:
			make_customer("_Test PE Copy", "6", ruc)
		self.assertIn(first.name, str(ctx.exception))  # points to the existing customer
		# spaces do not defeat the check
		with self.assertRaises(DuplicateIdentityError):
			make_customer("_Test PE Copy 2", "6", f" {ruc[:4]} {ruc[4:]} ")

	def test_duplicate_within_suppliers_is_blocked(self):
		ruc = make_ruc(10000006)
		make_supplier("_Test PE Supplier Original", "6", ruc)
		with self.assertRaises(DuplicateIdentityError):
			make_supplier("_Test PE Supplier Copy", "6", ruc)

	def test_same_number_under_different_document_types_is_not_a_duplicate(self):
		make_customer("_Test PE DNI 11112222", "1", "11112222")
		other = make_customer("_Test PE CE 11112222", "4", "11112222")
		self.assertEqual(other.pe_identity_type, "4")

	def test_saving_the_same_customer_again_is_not_a_duplicate(self):
		customer = make_customer("_Test PE Resave", "6", make_ruc(10000007))
		customer.customer_name = "_Test PE Resave Renamed"
		customer.save()

	def test_changing_to_an_existing_ruc_is_blocked(self):
		ruc = make_ruc(10000008)
		make_customer("_Test PE Holder", "6", ruc)
		other = make_customer("_Test PE Changer", "6", make_ruc(10000009))
		other.pe_identity_number = ruc
		with self.assertRaises(DuplicateIdentityError):
			other.save()

	def test_number_without_type_and_type_without_number(self):
		with self.assertRaises(IdentityDocumentError):
			make_customer("_Test PE No Type", None, "12345678")
		with self.assertRaises(IdentityDocumentError):
			make_customer("_Test PE No Number", "1", None)
		with self.assertRaises(IdentityDocumentError):
			make_customer("_Test PE Blank Number", "1", "   ")

	def test_party_without_identity_is_untouched(self):
		customer = make_customer("_Test PE Anonymous", tax_id="FREE-TEXT-1")
		self.assertIsNone(customer.pe_identity_type)
		self.assertIsNone(customer.pe_identity_number)
		self.assertEqual(customer.tax_id, "FREE-TEXT-1")

	def test_unknown_or_disabled_document_type(self):
		with self.assertRaises(frappe.LinkValidationError):  # Frappe's own link check comes first
			make_customer("_Test PE Unknown Type", "Z", "123")
		frappe.db.set_value("SUNAT Identity Document Type", "G", "enabled", 0)
		with self.assertRaises(IdentityDocumentError):
			make_customer("_Test PE Disabled Type", "G", "123")

	def test_removing_the_document_removes_the_tax_id_it_set(self):
		ruc = make_ruc(10000020)
		customer = make_customer("_Test PE Remove Doc", "6", ruc)
		self.assertEqual(customer.tax_id, ruc)
		customer.pe_identity_type = None
		customer.pe_identity_number = None
		customer.save()
		self.assertIsNone(customer.tax_id)

	def test_a_tax_id_entered_separately_is_kept(self):
		customer = make_customer("_Test PE Keep Tax ID", "1", "10000021")
		customer.pe_identity_type = None
		customer.pe_identity_number = None
		customer.tax_id = "OTHER-123"
		customer.save()
		self.assertEqual(customer.tax_id, "OTHER-123")

	def test_number_is_normalized(self):
		ruc = make_ruc(10000010)
		customer = make_customer("_Test PE Spaces", "6", f"  {ruc[:2]} {ruc[2:]}  ")
		self.assertEqual(customer.pe_identity_number, ruc)

	def test_md_cc_04_inactive_taxpayer_is_not_checked_online(self):
		# Phase 1 only validates the shape of the number; the SUNAT status lookup is Phase 2.
		customer = make_customer("_Test PE Old Taxpayer", "6", make_ruc(10000011))
		self.assertTrue(customer.name)
