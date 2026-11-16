# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt

from erpnext_peru.overrides.common import PERU, throw_identity_error
from erpnext_peru.utils.identity import IdentityError, validate_ruc


def validate(doc, method=None):
	"""A Peruvian company's Tax ID, when filled in, must be a valid RUC."""
	if doc.country != PERU or not (doc.tax_id or "").strip():
		return
	try:
		doc.tax_id = validate_ruc(doc.tax_id)
	except IdentityError as error:
		throw_identity_error(error)
