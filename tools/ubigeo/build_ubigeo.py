#!/usr/bin/env python3
# Copyright (c) 2026, erpnext_peru contributors
# License: GNU General Public License v3. See license.txt
"""Build erpnext_peru/data/ubigeo.csv from the official sources in raw/.

    python tools/ubigeo/build_ubigeo.py           # check the shipped CSV
    python tools/ubigeo/build_ubigeo.py --write   # regenerate it

Every difference between the sources must be declared below (new districts,
renames, corrections). Anything undeclared stops the build. See README.md.
Needs openpyxl (installed with Frappe).
"""

import argparse
import csv
import hashlib
import io
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUTPUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "erpnext_peru", "data", "ubigeo.csv")

INEI_2022 = os.path.join(RAW, "inei_ubigeo_2022_1891_distritos.xlsx")
INEI_2022_SHA256 = "4270794025045dc2a994e16f9b6dd508c3e0019cb26dfab1d339d1ec57d7d77e"
DIRECTORY = os.path.join(RAW, "inei_directorio_municipalidades_2026-11.txt")
# Computed in a browser over the official XLSX (README.md, "How the directory
# was extracted"), on the same lines as this file holds, without the final newline.
DIRECTORY_SHA256 = "de75d8249d9e9798da2ff4b3569848d8b1c8451d29026e3629c516cb42ab2e5f"
SUNAT_2014 = os.path.join(RAW, "sunat_catalogo_13_2014.txt")

# The directory (November 2026) against the code list (2022).
CREATED_SINCE_2022 = {
	"160405": "Santa Rosa de Loreto: Ley 32403, El Peruano 2025-07-03",
	"120307": "Sangani: Ley 32729, El Peruano 2026-07-15",
}
RENAMED_SINCE_2022 = {
	# code: (name in the 2022 code list, name in the 2026 directory)
	"030602": ("ANCO_HUALLO", "ANCO-HUALLO"),  # typo in the 2022 file
	"100106": ("QUISQUI (KICHKI)", "QUISQUI"),
}

# Corrections to the directory's spelling. Letters never change here, only
# accents and capitals; the build checks it. "de" / "del" inside a name is
# lowercase everywhere else in INEI's list.
CORRECTIONS = {
	("district", "110114"): ("Yauca Del Rosario", "Yauca del Rosario"),
	("district", "131001"): ("Santiago De Chuco", "Santiago de Chuco"),
	("district", "150120"): ("Magdalena Del Mar", "Magdalena del Mar"),
	("district", "150143"): ("Villa María Del Triunfo", "Villa María del Triunfo"),
	("province", "1310"): ("Santiago De Chuco", "Santiago de Chuco"),
	("province", "2110"): ("San Antonio De Putina", "San Antonio de Putina"),
	("province", "1007"): ("Marañon", "Marañón"),  # the river Marañón
	("province", "1607"): ("Datem del Marañon", "Datem del Marañón"),
}

# SUNAT's Catálogo 13 of August 2014 against the result: what changed since.
SUNAT_CODES_MOVED = {
	# 2014 code: current code. Province Putumayo (1608) was created from Maynas.
	"160109": "160801",
	"160114": "160803",
}
SUNAT_RENAMED = {  # 2014 name -> current name (accents and capitals ignored)
	"020109": ("PAMPAS", "PAMPAS GRANDE"),
	"030407": ("HUAYLLO", "IHUAYLLO"),
	"050707": ("SAN FRANCISCO DE RAVACAYCO", "SAN FRANCISCO DE RIVACAYCO"),
	"051010": ("HUAYA", "HUALLA"),
	"100106": ("QUISQUI", "QUISQUI"),  # unchanged: "(KICHKI)" was added in 2022 and dropped again
	"110301": ("NAZCA", "NASCA"),
	"131103": ("COMPIN", "MARMOT"),  # Compín is the capital de facto of Marmot
	"150712": ("LARAOS", "SAN PEDRO DE LARAOS"),
	"230110": ("CORONEL GREGORIO ALBARRACIN", "CORONEL GREGORIO ALBARRACIN LANCHIPA"),
	"250201": ("RAYMONDI", "RAIMONDI"),
}
SUNAT_PROVINCES_RENAMED = {"0701": ("PROV. CONST. DEL CALLAO", "CALLAO"), "1103": ("NAZCA", "NASCA")}
DISTRICTS_CREATED_SINCE_2014 = 61

EXPECTED = {"departments": 25, "provinces": 196, "districts": 1893}

PARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "E", "EN", "A", "AL"}


class BuildError(Exception):
	pass


def key(name: str) -> str:
	"""Upper case, no accents, single spaces: how INEI's code lists write names."""
	decomposed = unicodedata.normalize("NFD", name)
	plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
	return " ".join(plain.upper().split())


def sha256_file(path: str) -> str:
	with open(path, "rb") as handle:
		return hashlib.sha256(handle.read()).hexdigest()


def read_inei_2022() -> dict:
	import openpyxl

	if sha256_file(INEI_2022) != INEI_2022_SHA256:
		raise BuildError("raw/" + os.path.basename(INEI_2022) + " is not the published file")
	sheet = openpyxl.load_workbook(INEI_2022, read_only=True).worksheets[0]
	rows = {}
	for row in sheet.iter_rows(min_row=2, values_only=True):
		if not row[0]:
			continue  # the footnotes below the table
		code = str(row[0]).strip()
		if code in rows:
			raise BuildError(f"2022 code list: {code} repeated")
		rows[code] = tuple(key(str(value)) for value in row[1:4])
	return rows


def read_directory() -> dict:
	with open(DIRECTORY, encoding="utf-8") as handle:
		text = handle.read()
	if hashlib.sha256(text.rstrip("\n").encode()).hexdigest() != DIRECTORY_SHA256:
		raise BuildError("raw/" + os.path.basename(DIRECTORY) + " is not what was extracted from INEI's file")
	rows = {}
	for line in text.splitlines():
		code, department, province, district = line.split("|")
		rows[code] = (department, province, district)
	return rows


def read_sunat_2014() -> dict:
	with open(SUNAT_2014, encoding="utf-8") as handle:
		return {line.split("|")[0]: line.split("|")[1] for line in handle.read().splitlines()}


def check_directory_against_2022(directory: dict, inei: dict):
	new = sorted(set(directory) - set(inei))
	if new != sorted(CREATED_SINCE_2022):
		raise BuildError(f"districts not in the 2022 list: {new}, declared: {sorted(CREATED_SINCE_2022)}")
	gone = sorted(set(inei) - set(directory))
	if gone:
		raise BuildError(f"districts of 2022 missing from the directory: {gone}")
	for code in sorted(inei):
		old = inei[code]
		now = tuple(key(name) for name in directory[code])
		if code in RENAMED_SINCE_2022:
			before, after = RENAMED_SINCE_2022[code]
			if (old[2], now[2]) != (before, after):
				raise BuildError(f"{code}: declared rename {before} -> {after}, found {old[2]} -> {now[2]}")
			old = (old[0], old[1], after)
		if old != now:
			raise BuildError(f"{code}: 2022 list {old}, directory {now}")


def apply_corrections(directory: dict) -> dict:
	result = {code: list(names) for code, names in directory.items()}
	for (kind, code), (before, after) in CORRECTIONS.items():
		if key(before) != key(after):
			raise BuildError(f"correction of {code} changes letters, not only accents or capitals")
		index = 1 if kind == "province" else 2
		codes = [c for c in result if c.startswith(code)] if kind == "province" else [code]
		if not codes:
			raise BuildError(f"correction of {code}: no such {kind}")
		for c in codes:
			if result[c][index] != before:
				raise BuildError(f"correction of {code}: expected {before!r}, found {result[c][index]!r}")
			result[c][index] = after
	return {code: tuple(names) for code, names in result.items()}


def check_structure(rows: dict):
	departments, provinces = {}, {}
	for code, (department, province, district) in rows.items():
		if not re.fullmatch(r"[0-9]{6}", code):
			raise BuildError(f"code {code!r} must have six digits")
		for name in (department, province, district):
			if not name or name != " ".join(name.split()) or name != unicodedata.normalize("NFC", name):
				raise BuildError(f"{code}: badly formed name {name!r}")
		for table, prefix, name in ((departments, code[:2], department), (provinces, code[:4], province)):
			if table.setdefault(prefix, name) != name:
				raise BuildError(f"{prefix} has two names: {table[prefix]!r} and {name!r}")
	counts = {"departments": len(departments), "provinces": len(provinces), "districts": len(rows)}
	if counts != EXPECTED:
		raise BuildError(f"counts {counts}, expected {EXPECTED}")


def check_against_sunat_2014(rows: dict, sunat: dict):
	districts = {c: n for c, n in sunat.items() if len(c) == 6}
	provinces = {c: n for c, n in sunat.items() if len(c) == 4}
	gone = sorted(set(districts) - set(rows))
	if gone != sorted(SUNAT_CODES_MOVED):
		raise BuildError(f"2014 codes no longer in use: {gone}, declared: {sorted(SUNAT_CODES_MOVED)}")
	for old, new in SUNAT_CODES_MOVED.items():
		if key(districts[old]) != key(rows[new][2]):
			raise BuildError(f"{old} -> {new}: {districts[old]} is not {rows[new][2]}")
	created = len(set(rows) - set(districts))
	if created != DISTRICTS_CREATED_SINCE_2014:
		raise BuildError(f"{created} districts created since 2014, expected {DISTRICTS_CREATED_SINCE_2014}")
	for code in sorted(set(districts) & set(rows)):
		then, now = key(districts[code]), key(rows[code][2])
		before, after = SUNAT_RENAMED.get(code, (then, then))
		if (then, now) != (before, after):
			raise BuildError(f"{code}: SUNAT 2014 {then}, now {now}")
	for code, name in provinces.items():
		now = key(next(r[1] for c, r in rows.items() if c.startswith(code)))
		before, after = SUNAT_PROVINCES_RENAMED.get(code, (key(name), key(name)))
		if (key(name), now) != (before, after):
			raise BuildError(f"province {code}: SUNAT 2014 {name}, now {now}")


def build() -> str:
	inei = read_inei_2022()
	directory = read_directory()
	check_directory_against_2022(directory, inei)
	rows = apply_corrections(directory)
	check_structure(rows)
	check_against_sunat_2014(rows, read_sunat_2014())
	out = io.StringIO()
	writer = csv.writer(out, lineterminator="\n")
	writer.writerow(["code", "department", "province", "district"])
	for code in sorted(rows):
		writer.writerow([code, *rows[code]])
	return out.getvalue()


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--write", action="store_true", help="regenerate the shipped CSV")
	args = parser.parse_args()
	try:
		text = build()
	except BuildError as error:
		sys.exit(f"build failed: {error}")
	if args.write:
		with open(OUTPUT, "w", encoding="utf-8", newline="") as handle:
			handle.write(text)
		print(f"wrote {OUTPUT}")
		return
	with open(OUTPUT, encoding="utf-8") as handle:
		if handle.read() != text:
			sys.exit("data/ubigeo.csv differs from the sources: run with --write")
	print("data/ubigeo.csv matches the sources")


if __name__ == "__main__":
	main()
