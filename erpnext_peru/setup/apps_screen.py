# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""The "Peru" icon on the apps screen (Frappe v15 /apps, v16 home)."""

import frappe


def has_app_permission() -> bool:
	"""Desk users see the icon; website users (customers, suppliers) do not."""
	if frappe.session.user == "Administrator":
		return True
	return frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"
