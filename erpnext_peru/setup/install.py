# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erpnext_peru.setup.constraints import ensure_constraints
from erpnext_peru.setup.custom_fields import CUSTOM_FIELDS
from erpnext_peru.setup.ubigeo import load_ubigeo

CATALOGUE_DOCTYPES = {
	"comprobante_types": "SUNAT Comprobante Type",
	"identity_document_types": "SUNAT Identity Document Type",
	"credit_note_reasons": "SUNAT Credit Note Reason",
	"debit_note_reasons": "SUNAT Debit Note Reason",
	"igv_affectation_types": "SUNAT IGV Affectation Type",
}


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	"""Idempotent: safe to run on every migrate."""
	create_custom_fields(CUSTOM_FIELDS, update=True)
	load_catalogues()
	load_ubigeo()
	ensure_constraints()  # needs the columns the custom fields create


def read_catalogues() -> dict:
	path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sunat_catalogues.json")
	with open(path, encoding="utf-8") as handle:
		return json.load(handle)


def load_catalogues():
	"""Insert the SUNAT catalogue entries that are missing.

	Existing entries are left alone so that local corrections (a description,
	a disabled code) survive upgrades.
	"""
	data = read_catalogues()
	for key, doctype in CATALOGUE_DOCTYPES.items():
		for row in data[key]:
			if frappe.db.exists(doctype, row["code"]):
				continue
			doc = frappe.new_doc(doctype)
			doc.update(row)
			doc.enabled = 1
			doc.insert(ignore_permissions=True)
