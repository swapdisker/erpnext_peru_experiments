# erpnext_peru — handover

Version 0.2.0, 17 November 2026. For the team that continues this work and for the accountant
who reviews it.

## 1. Read this first

- **This is a prototype.** It has never held real data and no accountant has reviewed it.
- **It was built from public sources only**: SUNAT and MEF publications and ERPNext itself. No
  client file, export, credential or portal was available. Everything that needs one of those
  is not started (section 12).
- **It decides where some money is posted**: the IGV account and three company defaults.
  Those choices are in section 6 and must be confirmed before real use.
- **Its screens are almost untested.** The logic is tested through code against a real ERPNext
  site; forms were barely opened in a browser (section 9).
- **Tested on ERPNext v15 and v16** by the automated tests; the screens only on v15.

What it does, in one paragraph: it validates Peruvian identity documents on customers and
suppliers; adds comprobante type, series and a gapless number to sales invoices and enforces
the Factura / Boleta rules on submission; records the supplier's document on purchase invoices;
loads the PCGE 2019 chart of accounts into a company; and sets up the IGV tax templates. The
`docs/FEATURES.md` (English) and `docs/FUNCIONALIDADES.md` (Spanish) describe each feature from
the user's side.

## 2. State against the Phase 1 proposal

"Step" numbers are the proposal's.

| Proposal item | State |
|---|---|
| Step 2 — custom app, GPL-3.0, tests | Built. CI on GitHub: unit and integration (ERPNext v15) jobs pass. The v16 job (Python 3.14, MariaDB 11.8) passes too. |
| Step 3 — PCGE 2019 chart, apply / merge, defaults | Built and tested. Account types and defaults await the accountant. |
| Step 3 — merge with the client's CONCAR / Odoo chart | Function built and tested with synthetic accounts. **No screen. Never run on the real chart.** |
| Step 4 — identity documents, RUC / DNI validation, duplicates | Built and tested. |
| Step 4 — comprobante type, series-number, note reason and reference | Built and tested. |
| Step 4 — Ubigeo | Built and tested. All 1,893 districts shipped (INEI, November 2026), loaded on migrate. |
| Step 4 — Boleta rule above S/ 700 | Built and tested. |
| Step 4 — IGV 18% and the four tax categories | Built and tested. |
| Step 4 — daily SUNAT exchange rate | Not started. |
| Step 4 — destination entries (6 → 9 / 79) | Not started. |
| Step 5 — e-invoicing (UBL, provider, CDR) | Not started. |
| Step 6 — print format | Only the amount-in-words function. |
| Step 7 — tests on v15 and v16, documentation | Tests pass on v15 and v16; the main screens were checked by hand on both (section 9). Feature descriptions in English and Spanish. |
| CONCAR toolkit, reconciliation, SIRE | Not started. |
| Annexure A scenarios with an automated test | CoA-UC-01..03, CoA-CC-01..04, MD-UC-01..03, MD-CC-01..04, TX-UC-01..03, TX-CC-01..03 (20 of 81). Test names carry the ID. |

## 3. How it is built, and why

### Principles

- **Nothing in ERPNext core is touched.** Behaviour is added with document hooks
  (`hooks.py` → `overrides/`), custom fields (all prefixed `pe_`, created on install and
  re-synchronized on every migrate) and the app's own DocTypes.
- **Rules live in pure Python.** `utils/` has no Frappe import: RUC check digit, series and
  number formats, amount in words, the PCGE catalogue. They are tested without a database and
  can be reused by importers. `overrides/` and `accounts/` are thin layers that call them and
  turn their error codes into translated messages (`overrides/common.py`).
- **Only Peruvian companies are affected.** Every invoice hook returns at once unless the
  company's country is Peru. Opening invoices (`is_opening = "Yes"`) are exempt as well, and
  so are the invoices ERPNext merges from POS Invoices when a shift is closed (section 8). The
  party hooks act only on parties that carry an identity document.
- **The database backs up the important checks.** Unique indexes refuse a second voucher
  with the same company, type and number, and a second customer (or supplier) with the same
  identity document, even if a future bug or a direct write gets past the hooks
  (`setup/constraints.py`).
- **Defaults on save, rules on submit.** `validate` fills defaults and rejects values that can
  never be right. The rules that make a comprobante issuable run in `before_submit`, as the
  proposal specifies.
- **Regulatory data is data.** Catalogues and the chart are files under `data/`, each naming
  its source. Catalogue masters are editable on the site; entries that exist are never
  overwritten on upgrade.

### Voucher numbering (the part to understand before changing anything)

A comprobante number must be unique and consecutive per company, type and series, including
under concurrent submissions and after failures.

- ERPNext's own document name (`ACC-SINV-…`) is assigned when a draft is created, so deleted
  drafts leave holes. It is **not** used as the comprobante number.
- **SUNAT Voucher Series** holds one counter per company + type + series.
- The number is allocated in `before_submit`, by locking that row (`SELECT … FOR UPDATE`),
  incrementing it and writing it on the invoice. This happens inside the transaction that
  submits the invoice: if anything fails afterwards the counter rolls back with it. No gaps.
- The lock is held until the invoice has finished posting. Submissions in one series are
  therefore serialized. That is deliberate.
- `validate` always clears the number on a document that is not yet submitted in the
  database. Reason: the browser's "Amend" copies read-only fields, so an amended invoice
  arrives carrying the old number.
- A cancelled voucher keeps its number; an amended one gets a new number; a document that has
  a number cannot be deleted; the counter cannot be set below a number already issued.
- Type and series are `no_copy`, so a credit note created from a Factura does not inherit
  "01 / F001".
- Backstop: a unique index on Sales Invoice (`pe_voucher_number`, `pe_comprobante_type`,
  `company`). Drafts hold NULL there, which a unique index allows any number of times.

### Identity documents

Customer and Supplier carry `pe_identity_type` (SUNAT catalogue 06) and `pe_identity_number`.
The number is normalized, validated, checked for duplicates within the same party type (and
by a unique index on (`pe_identity_number`, `pe_identity_type`)), and copied to ERPNext's Tax
ID; removing the document removes that copy, unless the Tax ID was changed separately. The invoice stores its own copy of the customer's document
(`pe_customer_identity_*`), refreshed until submission and frozen after it: the issued
comprobante must not change if the master is corrected later.

### PCGE

- `utils/pcge.py` reads the catalogue and adds what ERPNext needs: element roots, group flags,
  a root type per element, an account type by code prefix.
- `accounts/pcge.py: apply_pcge` creates what is missing, in parent-first order, with the tree
  index rebuilt once at the end. It never deletes, renames or re-types an existing account.
  With `replace_existing` it first removes the current chart through ERPNext's own importer
  code, which checks every link.
- `import_client_accounts` places the company's sub-accounts under the account whose number is
  the longest existing prefix of the code.
- Both have a dry run that goes through the same code path and returns the same report, so
  the preview cannot drift from the real run. There is a test for that.
- Both take a site-wide database lock (`chart_lock`, MariaDB `GET_LOCK`) when they write.
  Creating accounts ends with rebuilding the account tree of every company, as ERPNext's own
  chart creation does; two rebuilds at once can deadlock or, before MariaDB 11.6, leave the
  tree numbering inconsistent. A second run waits up to two minutes, then is refused with a
  message. If nothing has been written in the transaction yet, the lock also starts a fresh
  snapshot, so the run sees what the previous one committed.

**The button on the Company form** (`accounts/api.py`). The request does a dry run, so
that whatever can be known in advance is refused on screen, then queues `run_pcge_job` and
returns. The job works inside a savepoint: on any error it rolls back to it (or, when a
deadlock has already made MariaDB discard the savepoint, rolls back the whole transaction),
writes the Error Log and records the message, so a failed run leaves the chart as it was. The
"failed" state is recorded even if the rollback itself fails, so the page never waits for a
job that has died. One job per
company at a time. Two things here were found by tests and are easy to undo by accident:
the state is read with `expires=True`, because otherwise Frappe keeps the first answer for
the rest of the request and a state written a moment later is never seen; and the role check
is the module's own `_only_managers`, because `frappe.only_for` lets everybody through while
tests run. It also asks for write permission on the company, which honours User Permissions.

### IGV

One 18% row on account 40111 for taxed operations; a 0% row on the same account for exonerado,
inafecto and exportación, so every document states its treatment and nothing is posted. Each
sales template carries the SUNAT catalogue 07 code (`pe_igv_affectation_type`). Tax rules link
each tax category to its template.

## 4. Data and where it comes from

| Data | Source | In the repo |
|---|---|---|
| PCGE Modificado 2019, 1,764 accounts | MEF, Consejo Normativo de Contabilidad, Res. CNC 002-2019-EF/30, the MEF's PDF | `data/pcge_2019.csv`, generated from `tools/pcge/` |
| Catalogue 01 comprobante types (17) | SUNAT Anexo 8, Anexo E of R.S. 245-2017 | `data/sunat_catalogues.json` |
| Catalogue 06 identity documents (13) | Same annex for 0–D; codes E–H from the annexes of R.S. 000049-2026 | same |
| Catalogue 07 IGV affectation (18) | Anexo E of R.S. 245-2017 | same |
| Catalogue 09 credit note reasons (13) | Annex of R.S. 165-2021 | same |
| Catalogue 10 debit note reasons (3) | Anexo E of R.S. 245-2017 | same |
| IGV rate 18% | SUNAT guidance page; Ley 32387 for the IGV / IPM split | constant in `accounts/igv.py` |
| S/ 700 Boleta rule | Reglamento de Comprobantes de Pago, art. 8; SUNAT FAQ | constant in `overrides/sales_invoice.py` |
| RUC check digit | Modulus 11, weights 5 4 3 2 7 6 5 4 3 2 | `utils/identity.py` |
| Ubigeo, 1,893 districts | INEI: code list 2022 (datosabiertos.gob.pe) and RENAMU directory of November 2026, with accents; SUNAT Catálogo 13 of 2014 as a check | `data/ubigeo.csv`, generated from `tools/ubigeo/` |

**The PCGE file is generated, not hand-edited.** `tools/pcge/raw/` holds the catalogue exactly
as the MEF printed it, misprints included. `tools/pcge/build_catalogue.py` applies 13 code
corrections and 5 name corrections, each explicit, and writes the CSV. A test fails if the
shipped CSV is not what the script produces. See `tools/pcge/README.md` for how the
transcription was made and its limits.

**The Ubigeo file is generated the same way.** `tools/ubigeo/build_ubigeo.py` checks INEI's
2022 code list, INEI's directory of municipalities of November 2026 and SUNAT's 2014 catalogue
against each other; every difference (2 districts created since 2022, 2 renames, 61 districts
since 2014...) is declared in the script, and anything undeclared stops the build. Accents
come from the directory; 8 corrections change only accents and capitals. The directory is not
in the repository because it lists mayors' contact details: only its place names were
extracted, and the script checks them against a SHA-256 taken from INEI's file. Codes are
INEI's, not RENIEC's (Chorrillos is 150108, not 140108). See `tools/ubigeo/README.md`.

`setup/ubigeo.py` loads the file on every migrate: missing codes inserted, names set back to
the file's, codes the file no longer has disabled (never deleted). Only enabled codes can be
chosen on an address.

Not shipped, because no official source could be confirmed or reached:

- **Catalogue 10 codes 10 and 11** (export / IVAP adjustments): seen in third-party sources only.
- **"Tabla 10" document types for purchases** (recibo por honorarios, DUA, non-domiciled…):
  the purchase register needs them; only catalogue 01 is loaded.
- **Elements 9 and 0 of the PCGE**: the MEF catalogue does not develop them. Only their roots
  exist; the company's own accounts hang from them.

## 5. How it was verified

- **303 automated tests**, all passing on Frappe 15.126.1 / ERPNext 15.125.0 / MariaDB 10.11,
  on two sites, one of them a fresh install, and in CI on GitHub (v15 and v16).
- **Mutation check: 94 deliberate bugs**, injected one at a time: wrong check-digit weight,
  `>` changed to `>=` on the S/ 700 rule, row lock removed, IGV rate set to 16%, the "company
  has ledger entries" guard removed, and so on. Every one made at least one test fail. The
  list is `tools/mutation_check.py`. It was run in batches (35, 24, 8 for the background job, 2 for the refused counter lock, 18 for the review fixes of 17 November, 3 for the fixes from the screen check: the refusal to replace a chart with IGV set up, the apps-screen icon for website users, and clearing an obsolete field description on migrate, 8 for the Ubigeo loader and the address form). It runs on MariaDB 10.11, so it cannot check the two lines that switch the snapshot check; only the v16 CI job exercises those. The combined script
  was checked to match the current source and spot-checked on 3 mutants, not re-run end to end.
- **Background job:** besides the tests, "Apply PCGE" was run once through a real queue and
  worker on a site outside the test runner: the request returned "queued", a second request
  was refused, the worker created 1,774 accounts in about 30 seconds and the state read "done".
- **Concurrency:** 8 database connections allocating 40 numbers in parallel produce exactly
  1..40; rolled-back allocations leave no gap; 4 invoices submitted in parallel get 4
  consecutive numbers.
- **RUC algorithm:** four published RUCs and an independently written reference over 20,000
  random numbers.
- **Amount in words:** cross-checked against the `num2words` library for 0–99,999 and 50,000
  random values up to 10^12, after correcting that library's known error (section 7).
- **PCGE:** the tree is consistent, and all 1,218 last-level codes match an independent copy
  of the plan except the corrected misprints.
- **Ledger:** tests assert the exact entries. S/ 1,000 taxed sale → 1212 debit 1,180, 70121
  credit 1,000, 40111 credit 180. S/ 500 taxed purchase → 6011 debit 500, 40111 debit 90, 4212
  credit 590. SUNAT's own example (sell 1,000, buy 600) leaves 72 payable on 40111.

### Not verified

- **ERPNext v16 in CI and on the test machine** passes the suite (Python 3.14, MariaDB 11.8 in
  CI; Frappe 16.56.0, ERPNext 16.55.0, MariaDB 10.11 locally): 303 tests, 1 skipped, the one
  for the v15 sidebar. The screens were also checked on a v16 site (section 9).
- **ERPNext's own test suite with this app installed.** It could not be started on the test
  machine: it stops while creating its own fixtures, identically on a site without this app.
  That standard behaviour is unaffected rests on this app's tests that non-Peruvian companies
  are left untouched. Run ERPNext's suite in CI before a release.
- **PCGE account names**, line by line against the PDF, by a person.
- **Anything with real data.** All test data is synthetic.

## 6. Decisions awaiting the accountant

Each is a judgement written into the code and easy to change. The file is given.

### Comprobantes — `overrides/sales_invoice.py`, `overrides/purchase_invoice.py`

1. **Factura to a non-domiciled customer.** Accepted for identity type `6` (RUC) and `0`
   (non-domiciled without RUC), intended for exports. Any other type is blocked.
2. **Boleta threshold.** Identity is required when the total in soles, IGV included, is
   *strictly greater* than 700.00. The exemption for non-domiciled buyers who cannot have a
   document is not implemented. A credit or debit note on a Boleta follows the same rule,
   measured on the note's own amount (a credit note of S/ 800 needs the customer's document).
3. **Default type.** Empty type becomes Factura when the customer has a RUC, Boleta otherwise.
   A Boleta to a customer with RUC is allowed, with a warning.
4. **Purchase side is optional.** Type, series and number of the supplier's document are
   validated when entered but not required.
5. **Supplier credit notes** must be entered as ERPNext returns (type 07 ⇔ "Is Return").
6. **Credit note reasons 02 and 03** are not restricted by the type of the modified document.
7. **Series of received vouchers** must have exactly four characters for types 01/03/07/08.

### Identity — `utils/identity.py`, `overrides/party.py`

8. **RUC prefixes** 10, 15, 16, 17 and 20 are accepted.
9. **The identity number is copied to Tax ID** for every document type, not only RUC.

### Chart of accounts — `utils/pcge.py`, `accounts/pcge.py`

10. **Root types.** Elements 1–3 Asset, 4 Liability, 5 Equity, 6 Expense, 7 Income. Where
    ERPNext has no equivalent a choice was made: element 8 → Expense, 9 → Expense, 0 → Asset.
    With 9 as Expense and 79 under Income, analytic entries (9x against 79) inflate both sides
    of the profit and loss report by the same amount.
11. **Account types** are set on as few accounts as possible: Cash (101, 102), Bank (104,
    106), Receivable (121, 123, 131, 133), Payable (421, 423, 424, 431, 433, 434), Tax (4011),
    Cost of Goods Sold (69), Income Account (70). Receivable and Payable accounts require a
    customer or supplier on every entry, which matters for the CONCAR journal import.
    Inventory (20–28) and fixed assets (33, 39) have no type on purpose.
12. **Company defaults set:** receivable 1212, payable 4212, income 70121.
13. **Round-off account 7599 is provisional.** ERPNext will not submit any invoice without
    one. It only ever receives céntimos.
14. **Defaults left empty:** cash, bank, default expense / cost of sales, exchange difference
    (ERPNext takes one account; the PCGE has 676 for losses and 776 for gains), all stock
    accounts.

### IGV — `accounts/igv.py`

15. **Purchase IGV is debited to 40111**, the account credited on sales, so its balance is
    the IGV payable. Whether to use 1673, or the 40116 / 40117 split by destination, is open.
16. **Zero-rate templates** post nothing and exist to state the treatment.
17. **One template per document.** Invoices mixing taxed and exempt items are not handled.
18. **The reduced rate** for small restaurants, hotels and lodging is not set up.
19. **Prices including IGV are not provided for.** The 18% template adds IGV on top of the
    price ("On Net Total"). Prices shown to consumers must include taxes, so a user who types
    a shelf price of S/ 118 charges S/ 139.24. Decide whether retail sales need a second
    template with "Is this Tax included in Basic Rate?" set, or price lists net of IGV, and
    train users accordingly.

### Presentation of the chart

20. **Account names repeat.** 1,281 of the 1,764 PCGE accounts share their name with another
    account ("Costo" 172 times, "Revaluación" 121, "Terceros", "Relacionadas"...), as printed by
    the MEF. In account pickers only the number tells them apart. Decide whether to qualify the
    names (for example "Mercaderías - venta local - Terceros"); `apply_pcge` keeps existing
    names, so this is best decided before the PCGE is applied to a real company.

## 7. ERPNext behaviours that matter for Peru

Found while building. Some are settings to change, some are traps.

1. **Totals are rounded by default.** An invoice of S/ 1,250.50 posted S/ 1,250.00 to the
   customer and S/ 0.50 to "Round Off" until Global Defaults → "Disable Rounded Total" was
   set. The app does not enforce the setting.
2. **Half-céntimo rounding.** New sites use banker's rounding: the IGV of S/ 0.25 (0.045)
   becomes 0.04, of S/ 1.25, 0.22. System Settings → Rounding Method is site-wide. The IGV
   setup warns and changes nothing.
3. **ERPNext's built-in tax for Peru is 16%**, a "Peru Tax" template created with every
   Peruvian company. The IGV setup disables it.
4. **The default tax template is applied only in the browser.** A Sales Invoice created by
   the API, an import or another app has no tax lines. Once a company has the IGV templates,
   this app blocks submitting a Sales Invoice with no tax line.
5. **No invoice can be submitted without a round-off account**, even when nothing is rounded.
6. **Foreign-currency invoices need a party account in that currency**, or the Accounts
   Settings option for multi-currency invoices against one party account.
7. **Purchase invoices and perpetual inventory.** With it on (the default for a new company)
   every purchase invoice demands a "Stock Received But Not Billed" account. The tests run
   with it off, which matches booking purchases through 60 / 61. This is a design decision.
   Seen on screen: on a company with the PCGE applied, the first purchase invoice is refused
   until the accountant either turns perpetual inventory off or sets that account, and sets a
   default expense account (or one per item). The PCGE leaves both empty on purpose (decision 14).
8. **An account that is a company default cannot become a group.** Sub-accounts under 1212 or
   4212 need the default moved first. The import reports this as a conflict and continues.
9. **A typed ledger can become a group** only with ERPNext's `exclude_account_type_check`
   flag, which the app sets (bank account 1041 keeps its type when 104101 is added).
10. **ERPNext's chart importer leaves an item tax template behind**, which blocks deleting
    the old tax account. Replacing the chart removes it first.
11. **`num2words` is wrong for Spanish thousands** ("veintiuno mil"). Frappe's money-in-words
    uses it, so the print format must use `utils/amount_in_words.py`.
12. **"Amend" copies read-only fields in the browser** (see numbering, section 3).
13. **List filters prefill new records.** Filtering the Customer list by identity type and
    then pressing "Add" creates a customer with that type already set.
14. **`frappe.copy_doc` keeps the docstatus when tests are running.** Only relevant to tests.
15. **A migrate does not remove a custom-field property that was dropped from the definition.**
    The voucher number kept an old English description on upgraded sites. Clear a property by
    setting it to `""` (a test now compares every description on the site with the definition).

### Differences found on v16

The first v16 runs failed. Five causes, all fixed; all but the last two are in code that runs
in production:

- **MariaDB 11.6.2 and later refuse the lock on the voucher counter** when another submission
  of the same series committed after the transaction's first read (`innodb_snapshot_isolation`
  is ON by default; error 1020, "Record has changed since last read"). No number was ever
  duplicated or skipped, but of two overlapping submissions one failed. `allocate_next_number`
  now switches that check off on its own connection for the two statements that lock and
  advance the counter, and back on after: the counter is only ever read under the lock, so
  waiting for the latest value is the correct behaviour, and it is what older servers do. If
  the database still refuses (or reports a deadlock), the user is told to submit again and
  nothing is allocated. The three concurrency tests failed on MariaDB 11.8 before this and
  pass after it. **Review this with whoever runs the database**: the alternative is to set
  `innodb_snapshot_isolation = OFF` for the whole server and delete the switch. ERPNext's own
  locking reads are subject to the same check and are not touched by this app.

- **`rebuild_tree` takes one argument on v16.** `apply_pcge` passed the parent field as well
  and stopped after creating the accounts.
- **A filter `("not in", ("", None))` matches nothing on v16.** The lookup of the accounts a
  company already has returned an empty list, so every account looked missing. It is now
  `("is", "set")`, which means the same on both versions. Avoid `None` inside `in` / `not in`.
- **`frappe.desk.desktop.get_workspace_sidebar_items` is gone**, with the v15 sidebar. The v16
  home page is an apps screen built from the `add_to_apps_screen` hook; without it there was no
  way to the Peru workspace except its address. The hook adds a **Peru** icon for desk users
  (`setup/apps_screen.py`). Frappe builds the workspace's sidebar by itself, from the module.
- **`/app/...` addresses redirect to `/desk/...`.** Nothing in the app depends on either.
- **`erpnext.setup.utils.before_tests` is gone.** A fresh v16 test site was never taken through
  the setup wizard, and creating a company failed ("Could not find Warehouse Type: Transit").
  The app's own `tests/utils.py: prepare_site` now does it on both versions.

## 8. Known gaps and risks

- **Cancellation is not restricted.** A submitted Factura can be cancelled in ERPNext. Under
  SUNAT rules that takes a comunicación de baja or a credit note. It belongs with e-invoicing.
- **Point of sale has no comprobantes.** Closing a POS shift merges its sales into one Sales
  Invoice per customer, usually the walk-in customer, and the returns into credit notes
  without a reason. That invoice is not a comprobante (each sale at the counter needs its
  own), so the app leaves it alone: it gets no type and no number. Before this was handled,
  closing a shift above S/ 700 failed. Issuing a Boleta per POS sale, or the SUNAT daily
  summary, is still to be designed. A merged invoice is recognised only when every item comes
  from a submitted POS Invoice, so setting `is_consolidated` through the API does not bypass
  the rules.
- **Unique indexes are created on migrate, unless the data already has duplicates.** Then the
  index is skipped, the duplicates are listed in the migrate output and the Error Log, and the
  next migrate tries again; the application's check still guards new records. On a large
  Sales Invoice table the first migrate spends time building the index.
- **The chart lock does not cover single accounts created by hand.** ERPNext locks those
  itself; the remaining risk is a person creating an account during an "Apply PCGE".
- **Applying the PCGE needs a background worker.** It runs as a job on the `long` queue
  (about 30 seconds for 1,774 accounts on the test machine) while the form asks for its state
  every 3 seconds. With no worker running the state stays "queued"; after 35 minutes it is
  reported as failed and a new request is accepted. The state lives in the Redis cache for 24
  hours: `bench clear-cache` during a run loses the message, not the job.
- **Replacing a chart deletes accounts.** It is refused when the company has ledger entries,
  and every deletion passes ERPNext's link checks, but it is the one destructive action here.
- **Uninstalling** leaves the custom fields and their data.
- **No roles or permissions of its own.** The form actions require System Manager or Accounts
  Manager; the catalogue masters are readable by everyone. The proposal's Migration User /
  Migration Approver roles do not exist yet.
- **The repository is marked "do not use"** in its README, at the owner's request.

## 9. State of the screens

Checked by hand on two Frappe Cloud sites, Spanish interface, with made-up data: ERPNext v15
(17 November) and ERPNext v16 (a fresh site, same day, after the fixes below). On both:

- **Company:** a RUC with a wrong check digit is refused with the Spanish message; a valid one
  saves. The **Perú** menu has "Aplicar PCGE 2019" and "Configurar IGV".
- **Apply PCGE**, replacing ERPNext's standard chart on a new company: preview, confirmation,
  then the background job; 1,774 accounts. Defaults to confirm are named by their labels.
- **Configure IGV:** 18 records, with the rounding-method warning. Afterwards, replacing the
  chart is refused with a message that says why and what to do.
- **Voucher series** F001, B001 and FC01 created from the form; the list reads correctly.
- **Customers and suppliers** with RUC, from the quick-entry pop-up and the full form; the
  identity fields show and the number is copied to Tax ID.
- **Factura:** type defaulted from the RUC, IGV template applied, number assigned on submit
  (F001-00000001). Ledger: 1212 debit 1,180; 40111 credit 180; 70121 credit 1,000.
- **Credit note** made with "Create → Return": reason, type and number of the modified voucher
  filled in, numbered FC01-00000001, ledger the exact reverse.
- **Boleta of S/ 1,180 to a customer without a document:** saved as draft, refused on submit
  ("Se requiere la identidad del cliente").
- **Purchase invoice** from a supplier with RUC: number padded to 00000123 and copied to the
  supplier invoice number; ledger 6011 debit 500, 40111 debit 90, 4212 credit 590. On a company
  just given the PCGE, ERPNext first refused it twice (section 7, point 7).
- **Address:** the Ubigeo field shows; the district list was not loaded at the time (it is now, see section 4).
- No JavaScript errors in the browser console.
- **v16 only:** the Peru icon on the apps screen opens the workspace, with its shortcuts and cards.

Found on screen and fixed: the voucher series showed as a second "Secuencia" next to ERPNext's
naming series; drafts showed "Número 0"; catalogue lists showed the code and "enabled" twice;
the PCGE report named defaults by field name; replacing the chart after IGV failed half way
with an ERPNext error; v16 had no way to the workspace; an obsolete English description stayed
under the voucher number.

Not seen: the print view (there is no print format), debit notes, foreign-currency invoices,
point of sale, and anything on a phone-sized screen.

## 10. Working on it

### Set up

```bash
bench get-app <repository-url>              # ERPNext v15 bench
bench new-site test.localhost               # a site used ONLY for tests
bench --site test.localhost install-app erpnext erpnext_peru
bench --site test.localhost set-config allow_tests true
```

### Run the tests

```bash
bench --site test.localhost run-tests --app erpnext_peru                                   # all (about 2 minutes)
bench --site test.localhost run-tests --app erpnext_peru --module erpnext_peru.tests.test_igv
```

The pure tests need no site:

```bash
python -m unittest erpnext_peru.tests.test_identity erpnext_peru.tests.test_voucher \
    erpnext_peru.tests.test_amount_in_words erpnext_peru.tests.test_pcge_data \
    erpnext_peru.tests.test_pcge_provenance erpnext_peru.tests.test_translations
```

Things to know:

- **The first run is slower.** It runs ERPNext's setup wizard (the `before_tests` hook
  delegates to ERPNext's) and creates three companies that stay on the site: `_Test Peru SAC`
  (standard chart), `_Test Foreign Inc` (not Peru) and `_Test PCGE SAC` (PCGE and IGV applied).
- **Tests roll back; fixtures and the concurrency tests commit.** The concurrency tests open
  several database connections, use their own series (`FZ9…`) and clean up after themselves.
- **Never run the tests on a site with real data.**
- **Mutation check:** `python tools/mutation_check.py --bench <bench> --site <test site>`.
  It edits source files while it runs and restores them. When a test is added for a new
  rule, add a mutant for it.
- **Lint:** `ruff check .` and `ruff format .` (settings in `pyproject.toml`, tabs).
- **Translations:** every message and label must have a row in `translations/es.csv`;
  `test_translations.py` fails otherwise, and also on stale rows.
- **Regenerating the PCGE:** `python tools/pcge/build_catalogue.py --write`.
- **Updating Ubigeo** (new districts): `tools/ubigeo/README.md`, then
  `python tools/ubigeo/build_ubigeo.py --write` (needs openpyxl, e.g. the bench's Python).

### Conventions

- Custom fields are declared in `setup/custom_fields.py` and nowhere else; `pe_` prefix.
- A new rule goes in `utils/` if it can be stated without the database, raising a subclass
  of `utils/errors.CodedError` with its own code; the hook translates the code into a message.
- Messages are written in English in the code and translated in `es.csv`.
- A rule that can block a user needs a test for the allowed side and the blocked side.

### Deploying on Frappe Cloud

Bench → Apps → the app's menu → "Fetch Latest Updates", then "Update Available", select only
this app and the sites. **Check the site's Jobs afterwards.** When a commit changes no DocType
file, Frappe Cloud runs "Update Site Pull" instead of "Update Site Migrate", so `after_migrate`
does not run and changes to `setup/custom_fields.py`, the catalogues or the unique indexes do
not reach the database. Seen on 17 November with the description fix. Run Site → Actions →
"Migrate Site" (in-place) in that case. Bumping "modified" on a DocType JSON in the same commit
also forces a migrate.

## 11. Where the remaining work plugs in

**E-invoicing.**
- Start from `Sales Invoice.pe_voucher_number`, `pe_comprobante_type`, `pe_series`,
  `pe_number`, `pe_customer_identity_type / _number`, `pe_credit_note_reason`,
  `pe_debit_note_reason`, `pe_original_type`, `pe_original_voucher_number`.
- The IGV treatment is on the tax template (`pe_igv_affectation_type`). UBL needs it per
  line; a line-level field or item tax templates will be needed for mixed invoices.
- Send after submission (an `on_submit` hook or a queue), never inside `before_submit`: the
  series row is locked there.
- Add status fields and block cancellation of accepted vouchers (section 8).
- `Address.pe_ubigeo` exists for the issuer and customer address.

**Print format.** `utils/amount_in_words.amount_in_words(total, currency)`. The QR needs the
hash from the signed XML.

**SIRE.**
- Sales register: the sales fields above plus the tax rows.
- Purchase register: `Purchase Invoice.pe_comprobante_type`, `pe_series`, `pe_number`,
  `pe_voucher_number`, `pe_original_*`. They must become mandatory, and "Tabla 10" loaded.

**CONCAR import.**
- Parties: reuse `utils/identity.py` and the duplicate rule in `overrides/party.py`. Creating
  the documents through `frappe.get_doc(...).insert()` runs the same validation.
- Chart: `accounts/pcge.import_client_accounts(company, rows, dry_run=True)` already returns
  the per-row report the proposal describes (created, rejected with reason, conflicts).
- Journals: lines on Receivable / Payable accounts need a party (decision 11).
- The proposal's import batch, mapping profile, error log, reversal and duplicate-file block
  do not exist yet.

**Destination entries.** Element 9 exists as a root only; the company's 9x accounts arrive
through `import_client_accounts`. See decision 10 for the effect on the profit and loss report.

**Exchange rate.** A scheduled job writing ERPNext's Currency Exchange; nothing exists.

## 12. Suggested order

1. **Click through the screens** on a v15 site, starting with the "Perú" menu. Half a day,
   and it removes the largest unknown.
2. **Decide on v16.** All CI jobs are green. For v16 the desk entry and a click-through are
   missing (section 5, "Not verified"), and the counter lock on MariaDB 11.8 deserves a review
   (section 7, "Differences found on v16").
3. **Accountant session on section 6.** Decisions 10–15 and 19 shape everything that posts;
   decision 20 should be settled before the PCGE is applied to a real company.
4. **Decide inventory** (finding 7) and the site settings (findings 1 and 2).
5. **Load the client's real chart** with `import_client_accounts` in dry-run mode. It will
   show how well the PCGE mapping fits before anything is committed.
6. **Load "Tabla 10"** from an official file. (Ubigeo is done.)
7. **CONCAR import engine**, parties first. Needs real export files.
8. **E-invoicing**, including comprobantes at the point of sale (section 8). Needs the OSE /
   PSE provider chosen and sandbox credentials.
9. **SIRE.** Needs a real proposal from the client's SUNAT portal to compare against.
10. **Destination entries**, after the accountant's mapping.
11. **v16**, once the above is stable on v15.

Blocked on the client: 5, 7, 8, 9, 10. Blocked on the accountant: 3, 4, 10.

## 13. File map

```
README.md                       short overview and links
docs/FEATURES.md                what the app does, for users (English)
docs/FUNCIONALIDADES.md         the same in Spanish
docs/HANDOVER.md                this document
tools/
  pcge/raw/                     the MEF catalogue as printed
  pcge/build_catalogue.py       raw transcription -> data/pcge_2019.csv
  ubigeo/raw/                   INEI 2022 code list, place names of INEI's 2026 directory,
                                SUNAT Catálogo 13 (2014)
  ubigeo/build_ubigeo.py        checks the three against each other -> data/ubigeo.csv
  mutation_check.py             the 94 deliberate bugs
erpnext_peru/
  hooks.py                      document hooks, form script, install / migrate / test hooks
  utils/                        pure Python, no Frappe
    identity.py                 RUC, DNI and other identity documents
    voucher.py                  series and numbers, issued and received
    amount_in_words.py          "SON: ... CON 00/100 SOLES"
    pcge.py                     the catalogue, element roots, root and account types
    errors.py                   CodedError, base of the errors above
  overrides/                    document hooks
    common.py                   error classes, message translation, is_peru_company / _invoice
    party.py                    Customer and Supplier identity
    company.py                  RUC of a Peruvian company
    address.py                  Ubigeo
    sales_invoice.py            comprobante rules and numbering on submit
    purchase_invoice.py         supplier document, duplicates
  accounts/
    pcge.py                     apply_pcge, import_client_accounts, chart_lock
    igv.py                      setup_igv
    api.py                      methods the Company form calls; the PCGE background job
  public/js/company.js          the "Perú" menu on the Company form
  setup/
    custom_fields.py            every pe_* field
    install.py                  creates fields, loads catalogues, indexes (install and migrate)
    constraints.py              the unique indexes
    ubigeo.py                   loads data/ubigeo.csv on migrate
  data/                         sunat_catalogues.json, pcge_2019.csv, pcge_2019_notes.json,
                                ubigeo.csv
  erpnext_peru/workspace/peru/  the "Peru" entry in the sidebar
  erpnext_peru/doctype/         SUNAT Comprobante Type, Identity Document Type, Credit Note
                                Reason, Debit Note Reason, IGV Affectation Type, Voucher
                                Series; Ubigeo
  translations/es.csv
  tests/                        utils.py holds the fixtures
```

## 14. History

| Version | Commit subject | Content |
|---|---|---|
| 0.1.0 | `erpnext_peru v0.1.0: prototype, first stage` | Identity documents, comprobante fields and numbering, catalogues 01 / 06 / 09 / 10, Ubigeo, amount in words. |
| — | `Show identity document fields in the … quick entry dialog` | Fix found on the first site test. |
| — | `README: mark the repository as a local experiment…` | Warning banner. |
| 0.2.0 | `Add PCGE 2019 chart of accounts and IGV tax templates` | PCGE, IGV, catalogue 07, the "Perú" menu, the tax-line rule on sales invoices. |
| 0.2.0 | this commit | Handover rewritten; PCGE transcription, build script and mutation list added to the repository. |
| 0.2.0 | `Add a Peru workspace to the sidebar` | Sidebar entry with shortcuts and cards. |
| — | `CI: let the MariaDB client connect without TLS` | First green integration run. |
| 0.2.0 | `Apply the PCGE as a background job; add a v16 CI job` | Job, state and polling; own role check; experimental v16 matrix entry. |
| 0.2.0 | `Make the app and its tests run on ERPNext v16` | Three v16 incompatibilities and the test-site preparation. |
| 0.2.0 | `Voucher counter: wait for the row lock on MariaDB 11.6+` | Counter lock under snapshot isolation; "submit again" message; v16 CI job required. |
| 0.2.0 | `Code review fixes: POS shifts, unique indexes, chart lock` | POS merged invoices exempt; database unique indexes; site-wide chart lock; robust job undo; notes on Boletas; Tax ID, Ubigeo warning and error-class fixes; CI lint. |
| 0.2.0 | `Fixes from the on-screen check; Peru icon on the v16 apps screen` | Labels, hidden draft number, list columns, chart-replace refusal, v16 apps-screen icon. |
| 0.2.0 | `Clear the obsolete voucher-number description; screen check on v16` | Description cleared on migrate; handover section 9 rewritten from the v15 and v16 checks. |
| 0.2.0 | `Handover: Frappe Cloud may deploy without a migrate` | Deployment note. |
| 0.2.0 | `Ship the Ubigeo list: 1,893 districts from INEI, with accents` | `tools/ubigeo/`, `data/ubigeo.csv`, load on migrate, enabled flag, address filter. |
| 0.2.0 | `Address form: fill City from the Ubigeo when it is chosen` | Found on screen: City is mandatory in the form, so the save-time fill came too late. |
