# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Amount in Spanish words, as printed on Peruvian comprobantes.

Example: ``amount_in_words("1234.56")`` ->
``"SON: MIL DOSCIENTOS TREINTA Y CUATRO CON 56/100 SOLES"``.

Free of Frappe imports. A small own implementation is used on purpose: the
``num2words`` library (0.5.x) renders 21 000 as "veintiuno mil" instead of
"veintiún mil".
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_UNITS = (
	"cero",
	"uno",
	"dos",
	"tres",
	"cuatro",
	"cinco",
	"seis",
	"siete",
	"ocho",
	"nueve",
	"diez",
	"once",
	"doce",
	"trece",
	"catorce",
	"quince",
	"dieciséis",
	"diecisiete",
	"dieciocho",
	"diecinueve",
	"veinte",
	"veintiuno",
	"veintidós",
	"veintitrés",
	"veinticuatro",
	"veinticinco",
	"veintiséis",
	"veintisiete",
	"veintiocho",
	"veintinueve",
)
_TENS = {
	3: "treinta",
	4: "cuarenta",
	5: "cincuenta",
	6: "sesenta",
	7: "setenta",
	8: "ochenta",
	9: "noventa",
}
_HUNDREDS = {
	1: "ciento",
	2: "doscientos",
	3: "trescientos",
	4: "cuatrocientos",
	5: "quinientos",
	6: "seiscientos",
	7: "setecientos",
	8: "ochocientos",
	9: "novecientos",
}

# Exclusive upper bound: one "billón" (10**12). Far above any invoice total.
MAX_INTEGER = 10**12

CURRENCY_NAMES = {
	"PEN": "SOLES",
	"USD": "DÓLARES AMERICANOS",
	"EUR": "EUROS",
}


def _below_thousand(n: int) -> str:
	"""Words for 1..999."""
	if n < 30:
		return _UNITS[n]
	if n < 100:
		tens, unit = divmod(n, 10)
		return _TENS[tens] if unit == 0 else f"{_TENS[tens]} y {_UNITS[unit]}"
	if n == 100:
		return "cien"
	hundreds, rest = divmod(n, 100)
	return _HUNDREDS[hundreds] if rest == 0 else f"{_HUNDREDS[hundreds]} {_below_thousand(rest)}"


def _apocope(words: str) -> str:
	"""Form used before "mil" / "millones": uno -> un, veintiuno -> veintiún."""
	if words.endswith("veintiuno"):
		return words[: -len("veintiuno")] + "veintiún"
	if words.endswith("uno"):
		return words[: -len("uno")] + "un"
	return words


def number_to_words_es(n: int) -> str:
	"""Spanish cardinal for a non-negative integer below 10**12, lower case."""
	if isinstance(n, bool) or not isinstance(n, int):
		raise TypeError("number_to_words_es expects an int")
	if n < 0 or n >= MAX_INTEGER:
		raise ValueError("number out of range (0 <= n < 10**12)")
	if n == 0:
		return _UNITS[0]

	millions, rest = divmod(n, 1_000_000)
	thousands, units = divmod(rest, 1000)
	parts: list[str] = []

	if millions:
		if millions == 1:
			parts.append("un millón")
		else:
			# 'millions' itself can reach 999 999, so it may contain thousands.
			parts.append(f"{_apocope(number_to_words_es(millions))} millones")
	if thousands:
		parts.append("mil" if thousands == 1 else f"{_apocope(_below_thousand(thousands))} mil")
	if units:
		parts.append(_below_thousand(units))
	return " ".join(parts)


def amount_in_words(amount, currency: str = "PEN", prefix: str = "SON: ") -> str:
	"""Return e.g. ``SON: CIENTO DIECIOCHO CON 00/100 SOLES``.

	``amount`` may be a str, int, Decimal or float (floats are converted through
	``str`` to avoid binary artefacts) and is rounded half-up to two decimals.
	Negative amounts are rejected: printed documents always show positive totals.
	"""
	try:
		value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
	except (InvalidOperation, ValueError) as exc:
		raise ValueError(f"not a valid amount: {amount!r}") from exc
	if not value.is_finite():
		raise ValueError(f"not a valid amount: {amount!r}")
	value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	if value < 0:
		raise ValueError("amount must not be negative")

	integer = int(value)
	cents = int((value - integer) * 100)
	currency_code = (currency or "").strip().upper()
	currency_name = CURRENCY_NAMES.get(currency_code, currency_code)
	words = number_to_words_es(integer).upper()
	text = f"{words} CON {cents:02d}/100 {currency_name}".rstrip()
	return f"{prefix or ''}{text}"
