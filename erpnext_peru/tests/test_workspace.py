# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""The "Peru" workspace and its icon on the apps screen (the home page)."""

import json
import os

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


class TestAppsScreen(PeruTestCase):
	def peru_apps(self):
		from frappe.apps import get_apps

		return [app for app in get_apps() if app["name"] == "erpnext_peru"]

	def test_icon_on_the_apps_screen(self):
		[app] = self.peru_apps()
		self.assertEqual(app["route"], "/app/peru")
		self.assertEqual(app["title"], frappe._("Peru"))
		logo = app["logo"]
		self.assertTrue(logo.startswith("/assets/erpnext_peru/"))
		path = frappe.get_app_path("erpnext_peru", "public", logo.removeprefix("/assets/erpnext_peru/"))
		self.assertTrue(os.path.isfile(path), path)

	def test_website_users_do_not_see_it(self):
		from erpnext_peru.setup.apps_screen import has_app_permission

		self.assertTrue(has_app_permission())  # Administrator
		email = "_test_pe_website_user@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Web",
					"user_type": "Website User",
					"send_welcome_email": 0,
				}
			).insert()
		frappe.set_user(email)
		self.assertFalse(has_app_permission())
