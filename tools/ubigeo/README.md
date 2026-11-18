# Where the Ubigeo data comes from

`erpnext_peru/data/ubigeo.csv` is generated. Do not edit it by hand. It holds the 1,893
districts of Peru (25 departments, 196 provinces) with INEI codes, the ones SUNAT's electronic
invoices use (`schemeAgencyName="PE:INEI"`), and the place names with their accents.

| File in `raw/` | What it is |
|---|---|
| `inei_ubigeo_2022_1891_distritos.xlsx` | INEI, "UBIGEO 2022_1891 distritos", the code list on the Plataforma Nacional de Datos Abiertos. Unchanged. |
| `inei_directorio_municipalidades_2026-11.txt` | The place-name columns of INEI's *Directorio Nacional de Municipalidades Provinciales y Distritales – Noviembre 2026*: `code\|department\|province\|district`. |
| `sunat_catalogo_13_2014.txt` | SUNAT's Catálogo 13 (Ubigeo) as printed in August 2014, `code\|name[\|footnote mark]`, used only as an independent check. |

`build_ubigeo.py` checks the three against each other, applies the corrections and writes the
CSV. Every difference between them is declared in the script; anything else stops the build.

```bash
python tools/ubigeo/build_ubigeo.py           # check the shipped CSV against the sources
python tools/ubigeo/build_ubigeo.py --write   # regenerate it
```

## The sources

**INEI code list, 2022.**
<https://www.datosabiertos.gob.pe/sites/default/files/UBIGEO%202022_1891%20distritos.xlsx>,
dataset "Ubigeos (Códigos de Ubicación Geográfica) – INEI", licence ODbL. 109,193 bytes,
SHA-256 `4270794025045dc2a994e16f9b6dd508c3e0019cb26dfab1d339d1ec57d7d77e`, checked by the
script. 1,891 districts, names in capitals without accents.

**INEI municipal directory, November 2026.**
<https://cdn.www.gob.pe/uploads/document/file/3905382/3364652-directorio-nacional-de-municipalidades-provinciales-y-distritales-noviembre-2026.xlsx>,
from the RENAMU 2026 page of INEI on gob.pe. Published 2026-11-06; 237,890 bytes, SHA-256
`9ebf248eb8950bcbe6a11e95f01af8998cef3d644d5ac32f539af45f1d0564bc`. It has 1,893 districts and
the names with accents. **The file is not in the repository**: it also lists each mayor's name,
telephone and e-mail. Only the code and the three place names were extracted.

How the directory was extracted (the script checks the result's SHA-256, which was computed on
the official file in a browser): rows whose first column is a six-digit code; columns A to D,
trimmed; the footnote marks at the end of four district names removed (" 1/" to " 4/"); the
department written as most rows of that department write it, because two rows have a capital
"Í" in the middle ("ApurÍmac" at 030612, "San MartÍn" at 221006); lines sorted by code.

**SUNAT Catálogo 13, 2014.** "Detalle de catálogos 2, 3, 4 y 13", PDF of 2014-08-06 linked from
SUNAT's page *05. Información de interés* (orientacion.sunat.gob.pe), SHA-256
`ac9f0a5639135202f66cf0d780f0e1e2537ca03354d03518db858ddcfa184154`. Extracted with
`pdftotext -layout`; the section is headed "CATALOGO No. 15" by mistake. 1,834 districts.

## What the script checks

- The directory has every 2022 code, and two more: Santa Rosa de Loreto (160405, Ley 32403,
  2025) and Sangani (120307, Ley 32729, 2026).
- Ignoring accents and capitals, its names equal the 2022 list except two declared renames
  (030602 "ANCO_HUALLO" was a typo; 100106 "QUISQUI (KICHKI)" is "QUISQUI" again).
- Corrections change only accents and capitals: "de" / "del" written "De" / "Del" in six names,
  and "Marañon" → "Marañón" in two provinces.
- Six-digit codes, no repeats, one name per department and per province, names in NFC without
  stray spaces; 25 / 196 / 1,893.
- Against SUNAT 2014: two codes moved to the province Putumayo (created in 2014), 61 districts
  created since, and ten districts and two provinces renamed, each one declared.

## When a district is created or renamed

INEI assigns the code; the RENAMU directory is updated a few times a year. Download the new
directory, extract it as described above into a new `raw/` file (and its SHA-256 into the
script), declare the new codes and renames, run with `--write`, then the tests. A migrate loads
the new CSV; codes that disappear are disabled, never deleted (see `setup/ubigeo.py`).
