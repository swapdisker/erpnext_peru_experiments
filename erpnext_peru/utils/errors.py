# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Base of the errors raised by the pure modules (no Frappe imports here)."""


class CodedError(ValueError):
	"""``code`` is stable and machine-readable, so callers can translate the
	message; ``params`` carries the values to interpolate."""

	def __init__(self, code: str, message: str, **params):
		super().__init__(message)
		self.code = code
		self.params = params
