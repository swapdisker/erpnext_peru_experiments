#!/usr/bin/env python3
# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Rebuild ``erpnext_peru/data/pcge_2019.csv`` from the transcription of the MEF document.

``raw/*.txt`` holds the "Catálogo de cuentas" of the PCGE Modificado 2019 exactly
as printed, misprints included, one ``CODE|NAME`` per line in document order.
This script applies the corrections listed below, each one explicit and
asserted against the printed text, checks that the result is a well-formed
tree, and writes (or checks) the data files the app ships.

    python tools/pcge/build_catalogue.py           # compare with the shipped files
    python tools/pcge/build_catalogue.py --write   # regenerate them

Needs nothing but the Python standard library.
"""

from __future__ import annotations

import collections
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "raw")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "erpnext_peru", "data")
CSV_PATH = os.path.join(DATA_DIR, "pcge_2019.csv")
NOTES_PATH = os.path.join(DATA_DIR, "pcge_2019_notes.json")

RAW_FILES = ("raw_1.txt", "raw_2.txt", "raw_3a.txt", "raw_3b.txt", "raw_45.txt", "raw_6.txt", "raw_78.txt")

# (code as printed, name as printed, which occurrence of that pair, corrected code, reason)
CODE_FIXES = (
	("27233", "Costo de financiación", 1, "27243", "printed twice; this one sits under 2724"),
	("30221", "Costo", 0, "30111", "printed under 3011 with the codes of 3022"),
	("30224", "Valor razonable", 0, "30114", "printed under 3011 with the codes of 3022"),
	("33404", "Planta productora en producción - Valor razonable", 0, "36404", "sits under 3640"),
	("38472", "Herramientas - Revaluación", 0, "36472", "sits under 3647"),
	("38473", "Unidades de reemplazo - costo", 0, "36473", "sits under 3647"),
	("38474", "Unidades de reemplazo - Revaluación", 0, "36474", "sits under 3647"),
	("38352", "Revaluación", 0, "39352", "sits under 3935"),
	("63432", "Operativo", 0, "63422", "sits under 6342"),
	("683351", "Costo", 0, "683151", "sits under 68315"),
	(
		"6882",
		"Desvalorización de propiedad de inversión",
		0,
		"6881",
		"printed twice; its sub-accounts are 68812 and 68813",
	),
	("70111", "Terceros", 1, "70121", "printed twice; this one sits under 7012"),
	("70112", "Relacionadas", 1, "70122", "printed twice; this one sits under 7012"),
)
# code (after the code fixes) -> (name as printed, corrected name)
NAME_FIXES = {
	"1051": ("Otro equivalentes de efectivo", "Otros equivalentes de efectivo"),
	"3325": ("Mejoras en locales arrendados.", "Mejoras en locales arrendados"),
	"441": ("Accionistas ( socios, partícipes)", "Accionistas (socios, partícipes)"),
	"6452": ("intereses - fraccionamiento", "Intereses - fraccionamiento"),
	"36473": ("Unidades de reemplazo - costo", "Unidades de reemplazo - Costo"),
}


def read_raw() -> list[list[str]]:
	rows = []
	for filename in RAW_FILES:
		with open(os.path.join(RAW_DIR, filename), encoding="utf-8") as handle:
			for number, line in enumerate(handle, start=1):
				line = line.rstrip("\n")
				assert line.count("|") == 1, (filename, number, line)
				code, name = line.split("|")
				assert code.isascii() and code.isdigit() and name and name == name.strip(), (filename, number)
				rows.append([code, name])
	return rows


def build() -> tuple[list[list[str]], list[dict]]:
	"""Return (rows, corrections). Raises AssertionError if anything is inconsistent."""
	rows = read_raw()
	corrections: list[dict] = []

	for printed, name, occurrence, fixed, reason in CODE_FIXES:
		hits = [row for row in rows if row[0] == printed and row[1] == name]
		assert len(hits) > occurrence, ("correction does not match the printed text", printed, name)
		hits[occurrence][0] = fixed
		corrections.append({"printed_code": printed, "name": name, "corrected_code": fixed, "reason": reason})

	for code, (old, new) in NAME_FIXES.items():
		hits = [row for row in rows if row[0] == code]
		assert len(hits) == 1 and hits[0][1] == old, ("correction does not match the printed text", code)
		hits[0][1] = new
		corrections.append(
			{"code": code, "printed_name": old, "corrected_name": new, "reason": "typographical"}
		)

	for row in rows:
		if len(row[0]) == 2:
			row[1] = row[1].capitalize()  # two-digit headings are printed in capitals

	codes = [row[0] for row in rows]
	repeated = [code for code, count in collections.Counter(codes).items() if count > 1]
	assert not repeated, ("repeated codes", repeated)
	known = set(codes)
	for code in codes:
		assert len(code) == 2 or code[:-1] in known, ("account without parent", code)
	assert codes == sorted(codes), "after the corrections, document order must be numeric order"
	for code, name in rows:
		assert "  " not in name, (code, name)
	return rows, corrections


def render_csv(rows) -> str:
	buffer = io.StringIO()
	writer = csv.writer(buffer, lineterminator="\n")
	writer.writerow(["code", "name"])
	writer.writerows(rows)
	return buffer.getvalue()


def main(argv: list[str]) -> int:
	rows, corrections = build()
	text = render_csv(rows)
	levels = dict(sorted(collections.Counter(len(row[0]) for row in rows).items()))
	print(f"{len(rows)} accounts, by code length: {levels}; {len(corrections)} corrections")

	with open(NOTES_PATH, encoding="utf-8") as handle:
		notes = json.load(handle)

	if "--write" in argv:
		with open(CSV_PATH, "w", encoding="utf-8", newline="") as handle:
			handle.write(text)
		notes["corrections"] = corrections
		with open(NOTES_PATH, "w", encoding="utf-8") as handle:
			json.dump(notes, handle, ensure_ascii=False, indent=1)
		print("data files written")
		return 0

	with open(CSV_PATH, encoding="utf-8", newline="") as handle:
		shipped = handle.read()
	problems = []
	if shipped != text:
		problems.append("pcge_2019.csv differs from what the transcription produces")
	if notes.get("corrections") != corrections:
		problems.append("pcge_2019_notes.json lists other corrections than this script applies")
	for problem in problems:
		print("MISMATCH:", problem)
	if not problems:
		print("shipped data files match the transcription")
	return 1 if problems else 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
