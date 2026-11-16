# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""The "Peru" entry in the sidebar."""

import json

import frappe

from erpnext_peru.tests.utils import PeruTestCase


class TestWorkspace(PeruTestCase):
	def setUp(self):
		super().setUp()
		self.workspace = frappe.get_doc("Workspace", "Peru")

	def test_workspace_is_public_and_visible(self):
		self.assertEqual(self.workspace.public, 1)
		self.assertEqual(self.workspace.is_hidden, 0)
		self.assertEqual(self.workspace.module, "ERPNext Peru")
		self.assertFalse(self.workspace.for_user)

	def test_it_is_listed_in_the_sidebar(self):
		from frappe.desk.desktop import get_workspace_sidebar_items

		pages = get_workspace_sidebar_items()["pages"]
		self.assertIn("Peru", [page["name"] for page in pages])

	def test_every_link_points_to_an_existing_doctype(self):
		targets = [row.link_to for row in self.workspace.links if row.type == "Link"]
		targets += [row.link_to for row in self.workspace.shortcuts]
		self.assertGreaterEqual(len(targets), 20)
		for target in targets:
			with self.subTest(target=target):
				self.assertTrue(frappe.db.exists("DocType", target))

	def test_the_apps_own_masters_are_reachable(self):
		targets = {row.link_to for row in self.workspace.links if row.type == "Link"}
		own = set(frappe.get_all("DocType", {"module": "ERPNext Peru", "istable": 0}, pluck="name"))
		self.assertEqual(own - targets, set())

	def test_layout_refers_only_to_blocks_that_exist(self):
		shortcuts = {row.label for row in self.workspace.shortcuts}
		cards = {row.label for row in self.workspace.links if row.type == "Card Break"}
		for block in json.loads(self.workspace.content):
			data = block["data"]
			if block["type"] == "shortcut":
				self.assertIn(data["shortcut_name"], shortcuts)
			elif block["type"] == "card":
				self.assertIn(data["card_name"], cards)
		used_cards = {
			b["data"]["card_name"] for b in json.loads(self.workspace.content) if b["type"] == "card"
		}
		self.assertEqual(used_cards, cards)

	def test_card_link_counts(self):
		count, expected = 0, None
		for row in [*self.workspace.links, None]:
			if row is None or row.type == "Card Break":
				if expected is not None:
					self.assertEqual(count, expected)
				if row is not None:
					expected, count = row.link_count, 0
			else:
				count += 1
