# Where the PCGE data comes from

`erpnext_peru/data/pcge_2019.csv` is generated. Do not edit it by hand.

| File | What it is |
|---|---|
| `raw/raw_*.txt` | The "Catálogo de cuentas" (Capítulo II) of the PCGE Modificado 2019, **exactly as printed** by the MEF, misprints included. One `CODE\|NAME` per line, in document order. Elements 1 to 8. |
| `build_catalogue.py` | Applies the corrections (each one explicit, each one asserted against the printed text), validates the tree and writes the CSV and the corrections list. |

Source: <https://www.mef.gob.pe/contenidos/conta_publ/pcge/PCGE_2019.pdf> (Consejo Normativo de
Contabilidad, Resolución CNC N.° 002-2019-EF/30), retrieved on 2026-11-16.

```bash
python tools/pcge/build_catalogue.py           # check the shipped files against the transcription
python tools/pcge/build_catalogue.py --write   # regenerate them
```

## How the transcription was made, and its limits

The PDF text was read element by element and written down as printed. The reader reported the
misprints it saw (repeated and misplaced codes); those became the corrections in the script.

Checks made afterwards:

- structure: no repeated code, every account has its parent, document order equals numeric order;
- every last-level code (1,218 of them) was compared with an independent copy of the plan:
  all match, except the corrected misprints;
- account names were compared with the same copy: the differences found were all on the other
  side (wording variants, untranslated fragments).

What was **not** done: a person proof-reading every name against the PDF. To correct a name, fix
it in `raw/` if the transcription is wrong, or add it to `NAME_FIXES` if the MEF text is wrong,
then run the script with `--write`.

## To update to a future version of the plan

Replace the `raw/` files with the new catalogue as printed, adjust `CODE_FIXES` / `NAME_FIXES`,
run with `--write`, and run the tests: `test_pcge_data.py` pins the size and shape of the
catalogue and will show what changed.
