# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Methods called from the Company form."""

import frappe
from frappe.utils import cint

from erpnext_peru.accounts.igv import setup_igv
from erpnext_peru.accounts.pcge import apply_pcge

ALLOWED_ROLES = ("System Manager", "Accounts Manager")


@frappe.whitelist()
def preview_pcge(company: str, replace_existing=0):
	"""What applying the PCGE would do. Changes nothing."""
	frappe.only_for(ALLOWED_ROLES)
	return apply_pcge(company, replace_existing=bool(cint(replace_existing)), dry_run=True)


@frappe.whitelist(methods=["POST"])
def apply_pcge_to_company(company: str, replace_existing=0):
	frappe.only_for(ALLOWED_ROLES)
	return apply_pcge(company, replace_existing=bool(cint(replace_existing)), dry_run=False)


@frappe.whitelist(methods=["POST"])
def setup_igv_for_company(company: str):
	frappe.only_for(ALLOWED_ROLES)
	return setup_igv(company)
