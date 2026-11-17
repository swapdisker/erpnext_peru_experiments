# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""The database itself refuses duplicate voucher numbers and identity documents."""

import frappe

from erpnext_peru.setup.constraints import CONSTRAINTS, ensure_constraint, ensure_constraints, find_duplicates
from erpnext_peru.tests.utils import (
	PeruTestCase,
	make_customer,
	make_ruc,
	make_sales_invoice,
	make_series,
	make_supplier,
)


class TestUniqueIndexes(PeruTestCase):
	def assertUniqueViolation(self, write):
		with self.assertRaises(Exception) as raised:
			write()
		self.assertTrue(frappe.db.is_unique_key_violation(raised.exception), raised.exception)

	def test_indexes_exist_after_install(self):
		self.assertEqual(set(ensure_constraints().values()), {"exists"})
		for doctype, name, columns in CONSTRAINTS:
			rows = frappe.db.sql(f"SHOW INDEX FROM `tab{doctype}` WHERE Key_name = %s", (name,), as_dict=True)
			self.assertEqual([row.Column_name for row in rows], list(columns))
			self.assertTrue(all(row.Non_unique == 0 for row in rows))

	def test_database_refuses_a_duplicate_identity_document(self):
		ruc = make_ruc(91000001)
		make_customer("_Test PE Unique 1", "6", ruc)
		second = make_customer("_Test PE Unique 2", "1", "91000001").name
		# Bypasses the hook, as a script or a bug would.
		self.assertUniqueViolation(
			lambda: frappe.db.set_value(
				"Customer", second, {"pe_identity_type": "6", "pe_identity_number": ruc}
			)
		)

	def test_same_document_as_customer_and_as_supplier_is_allowed(self):
		ruc = make_ruc(91000002)
		make_customer("_Test PE Unique 3", "6", ruc)
		make_supplier("_Test PE Unique 3", "6", ruc)

	def test_same_number_with_another_document_type_is_allowed(self):
		make_customer("_Test PE Unique 4", "1", "91000004")
		make_customer("_Test PE Unique 5", "4", "91000004")  # carnet de extranjería

	def test_parties_without_a_document_are_not_affected(self):
		for index in range(3):
			make_customer(f"_Test PE Unique Anonymous {index}")

	def test_database_refuses_a_duplicate_voucher_number(self):
		customer = make_customer("_Test PE Unique 6", "6", make_ruc(91000006)).name
		make_series("01", "F001")
		first = make_sales_invoice(customer)
		first.submit()
		second = make_sales_invoice(customer)
		second.submit()
		self.assertUniqueViolation(
			lambda: frappe.db.set_value(
				"Sales Invoice", second.name, "pe_voucher_number", first.pe_voucher_number
			)
		)

	def test_drafts_are_not_affected(self):
		customer = make_customer("_Test PE Unique 7", "6", make_ruc(91000007)).name
		make_series("01", "F001")
		drafts = [make_sales_invoice(customer) for _ in range(3)]
		self.assertEqual({d.pe_voucher_number for d in drafts}, {None})


class TestIndexCreation(PeruTestCase):
	"""What migrate does when the data already holds duplicates.

	ALTER TABLE commits, so these tests clean up after themselves explicitly
	and always put the index back.
	"""

	DOCTYPE = "Supplier"
	INDEX = "pe_unique_identity"
	COLUMNS = ("pe_identity_number", "pe_identity_type")
	NAMES = ("_Test PE Index A", "_Test PE Index B", "_Test PE Index C")

	def tearDown(self):
		frappe.db.rollback()
		self.delete_suppliers()
		frappe.db.delete("Error Log", {"method": ("like", "erpnext_peru: duplicates block%")})
		frappe.db.commit()
		ensure_constraint(self.DOCTYPE, self.INDEX, self.COLUMNS)
		super().tearDown()
		self.assertTrue(
			frappe.db.sql(f"SHOW INDEX FROM `tab{self.DOCTYPE}` WHERE Key_name = %s", (self.INDEX,))
		)

	def delete_suppliers(self):
		for name in self.NAMES:
			frappe.db.delete("Supplier", {"supplier_name": name})

	def drop_index(self):
		frappe.db.sql_ddl(f"ALTER TABLE `tab{self.DOCTYPE}` DROP INDEX `{self.INDEX}`")

	def test_duplicates_block_the_index_and_are_reported(self):
		self.drop_index()
		ruc = make_ruc(92000001)
		first = make_supplier(self.NAMES[0], "6", ruc).name
		second = make_supplier(self.NAMES[1], "1", "92000001").name
		frappe.db.set_value("Supplier", second, {"pe_identity_type": "6", "pe_identity_number": ruc})
		frappe.db.commit()

		self.assertEqual(
			find_duplicates(self.DOCTYPE, self.COLUMNS),
			[{"pe_identity_number": ruc, "pe_identity_type": "6", "count": 2, "names": f"{first}, {second}"}],
		)
		self.assertEqual(ensure_constraint(self.DOCTYPE, self.INDEX, self.COLUMNS), "duplicates")
		self.assertFalse(frappe.db.sql("SHOW INDEX FROM `tabSupplier` WHERE Key_name = %s", (self.INDEX,)))
		log = frappe.get_last_doc(
			"Error Log", filters={"method": ("like", "erpnext_peru: duplicates block%")}
		)
		self.assertIn(ruc, log.error)
		self.assertIn(second, log.error)

		# Once the duplicate is corrected, the next migrate creates the index.
		frappe.db.set_value("Supplier", second, "pe_identity_number", "92000001")
		self.assertEqual(ensure_constraint(self.DOCTYPE, self.INDEX, self.COLUMNS), "created")

	def test_empty_strings_count_as_empty(self):
		"""Rows written around the hooks may hold '' instead of NULL."""
		self.drop_index()
		for name in self.NAMES[:2]:
			supplier = make_supplier(name).name
			frappe.db.set_value("Supplier", supplier, {"pe_identity_type": "", "pe_identity_number": ""})
		frappe.db.commit()
		self.assertEqual(ensure_constraint(self.DOCTYPE, self.INDEX, self.COLUMNS), "created")
		self.assertEqual(
			frappe.get_all(
				"Supplier",
				filters={"supplier_name": ("in", self.NAMES[:2])},
				fields=["pe_identity_type", "pe_identity_number"],
			),
			[{"pe_identity_type": None, "pe_identity_number": None}] * 2,
		)
