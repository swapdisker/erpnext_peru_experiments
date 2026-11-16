# Handover notes — erpnext_peru v0.2.0 (prototype, second stage)

For the team that continues this work and for the accountant who reviews it.

## 1. What this stage covers

Against the Phase 1 proposal ("Step" numbers are the proposal's):

| Proposal item | State |
|---|---|
| Step 2 — custom app, licence, tests | Built. CI workflow written but **never run**. |
| Step 3 — PCGE 2019 chart of accounts, apply / merge, defaults | **Built and tested (stage 2).** Account types and defaults need the accountant, see 3. |
| Step 4 — identity documents with RUC/DNI validation and duplicate checks | Built and tested. |
| Step 4 — comprobante type and series-number on invoices, note reason and reference | Built and tested. |
| Step 4 — Ubigeo field and master | Field, master and CSV loader built. **District data not loaded.** |
| Step 4 — Boleta rule above S/ 700 | Built and tested. |
| Step 4 — IGV 18% and tax categories (gravado, exonerado, inafecto, exportación) | **Built and tested (stage 2).** |
| Step 4 — daily SUNAT exchange rate | **Not started.** |
| Step 5 — e-invoicing | **Not started.** |
| Step 6 — print format | Only the amount-in-words function. |
| CONCAR toolkit, SIRE, destination entries | **Not started.** |

Stage 1 only added identification data to documents. **Stage 2 decides where money is
posted**: which account receives the IGV, which accounts are the company's receivable, payable
and income defaults. Those choices are listed in section 3 and need an accountant before any
real use.

## 2. How it was verified

- **236 automated tests**, all passing on Frappe 15.126.1 / ERPNext 15.125.0 / MariaDB 10.11:
  pure tests (validators, PCGE catalogue, number formatting, translations) and tests that run
  against a real ERPNext site, including invoices posted to a company running on the PCGE.
- **Mutation check:** 59 deliberate bugs were injected one at a time (wrong check-digit
  weight, `>` changed to `>=` on the S/ 700 rule, row lock removed, IGV rate changed to 16%,
  the "company has ledger entries" guard removed...). Every one made at least one test fail.
- **Concurrency:** 8 database connections allocating 40 numbers in parallel produce exactly
  1..40; rolled-back allocations leave no gap; 4 invoices submitted in parallel get 4
  consecutive numbers.
- **RUC algorithm** checked against four published RUCs and an independently written
  reference over 20,000 random numbers.
- **Amount in words** cross-checked against the `num2words` library for 0–99,999 and 50,000
  random values up to 10^12 (after correcting that library's known error, see 4.3).

### Not verified

- **ERPNext's own test suite with this app installed.** It could not be started in the test
  environment: it stops while creating its own fixtures, identically on a site without this
  app. That standard ERPNext behaviour is unaffected rests on this app's own tests (companies
  outside Peru are left untouched). Run ERPNext's suite in CI before a release.
- **The user interface.** The test environment could not build ERPNext's front end, so no
  form was opened in a browser there. The new "Peru" menu on the Company form (JavaScript)
  was syntax-checked only and has never been clicked. Field placement, the `depends_on` visibility of the note
  fields and the link filters are declarative and untested visually.
- **ERPNext v16.** Only v15 was run.
- **The CI workflow** (`.github/workflows/ci.yml`).
- **Any real data.** All test data is synthetic.

## 3. Decisions the accountant must confirm

Each of these is a judgement written into the code. They are easy to change.

1. **Factura to a non-domiciled customer.** A Factura is accepted for identity type `6` (RUC)
   and also `0` (non-domiciled without RUC), intended for exports. Any other document type is
   blocked. *File: `overrides/sales_invoice.py`, `_validate_customer_identity`.*
2. **Boleta threshold.** Identity is required when the total in soles is *strictly greater*
   than 700.00 (700.00 itself passes). The total used is the grand total converted to soles.
   The exemption for non-domiciled buyers who cannot have a document is **not** implemented.
3. **Default comprobante type.** Empty type becomes Factura when the customer has a RUC and
   Boleta otherwise. A Boleta to a customer with RUC is allowed, with a warning.
4. **RUC prefixes.** 10, 15, 16, 17 and 20 are accepted.
5. **Purchase side is optional.** Type, series and number of the supplier's document are
   validated when entered but not required. The purchase register (SIRE RCE) will need them.
6. **Supplier credit notes** must be entered as ERPNext returns (type 07 ⇔ "Is Return").
7. **Identity number is copied to Tax ID** for every document type, not only RUC.
8. **Credit note reasons 02 and 03** are not restricted by modified document type.

### Stage 2 decisions (these affect postings)

9. **Root types.** Elements 1–3 are Asset, 4 Liability, 5 Equity, 6 Expense, 7 Income. The
   PCGE has no equivalent for ERPNext's five types in three cases, where a choice was made:
   element 8 → Expense, element 9 → Expense, element 0 → Asset. With 9 as Expense and 79 under
   Income, analytic entries (9x against 79) inflate both sides of the profit and loss report by
   the same amount. *File: `utils/pcge.py`, `ELEMENTS`.*
10. **Account types** are set on as few accounts as possible: Cash (101, 102), Bank (104,
    106), Receivable (121, 123, 131, 133), Payable (421, 423, 424, 431, 433, 434), Tax (4011),
    Cost of Goods Sold (69), Income Account (70). Receivable and Payable accounts require a
    customer or supplier on every entry. Inventory (20–28) and fixed assets (33, 39) have no
    type on purpose.
11. **Company defaults set:** receivable 1212, payable 4212, income 70121.
12. **Round-off account 7599 is provisional.** ERPNext will not submit any invoice without
    one. It only receives céntimos, but the account is the accountant's choice.
13. **Not set:** cash and bank defaults, default expense / cost of sales, exchange difference
    (ERPNext takes one account; the PCGE has 676 for losses and 776 for gains), all stock
    accounts.
14. **IGV on purchases is debited to 40111**, the same account credited on sales, so its
    balance is the IGV payable. Whether to use 1673 or the 40116/40117 split is open.
15. **Exempt, unaffected and export sales** use a template with a 0% line on 40111, so the
    document states its treatment and nothing is posted.
16. **Mixed invoices** (taxed and exempt items together) are not handled: one template applies
    to the whole document.

## 4. Findings about ERPNext that affect Peru

1. **Totals are rounded by default.** ERPNext posts the *rounded* total to the customer and
   books the difference to a round-off account. On a company created by the setup wizard, an
   invoice of S/ 1,250.50 produced a receivable of S/ 1,250.00 and S/ 0.50 in "Round Off"
   until "Disable Rounded Total" was set. Peruvian comprobantes are issued to the céntimo, so
   this setting (Global Defaults) must be on. The app does **not** enforce it.
2. **Foreign-currency invoices need a party account in that currency.** A USD invoice against
   the PEN receivable account is rejected by ERPNext v15 unless Accounts Settings allows
   multi-currency invoices against a single party account. Relevant to the chart of accounts
   design (12 / 42 in USD).
3. **`num2words` is wrong for Spanish thousands.** It writes "veintiuno mil" instead of
   "veintiún mil". Frappe's built-in money-in-words uses that library, so the print format
   must use `erpnext_peru.utils.amount_in_words` instead.
4. **"Amend" copies read-only fields in the browser.** An amended invoice arrives carrying the
   old voucher number. The server discards it on every save; there is a test for this.
5. **"Create → Credit Note" copies fields from the original.** Type and series are marked
   `no_copy` so a credit note does not inherit "01 / F001".

6. **ERPNext's built-in tax for Peru is 16%.** Every company created with country Peru gets
   a "Peru Tax" template at 16% on an account called VAT. The IGV setup disables it.
7. **The default tax template is only applied in the browser.** A Sales Invoice created by
   the API, an import or another app arrives with no tax lines and would be issued without
   IGV. Once a company has the IGV templates, this app blocks submitting a Sales Invoice
   with no tax line at all.
8. **Half-céntimo rounding.** New ERPNext sites use banker's rounding: the IGV of S/ 0.25
   (0.045) becomes 0.04, not 0.05; of S/ 1.25, 0.22, not 0.23. The setting is site-wide
   (System Settings → Rounding Method). The IGV setup warns about it but does not change it.
9. **Purchase invoices need a decision on inventory.** With "perpetual inventory" on (the
   default for a new company), ERPNext demands a "Stock Received But Not Billed" account on
   every purchase invoice. The tests run with it off, which matches booking purchases through
   60/61, but this is the accountant's design choice.
10. **An account that is a company default cannot become a group.** If the company wants
    sub-accounts under 1212 or 4212, the default has to point elsewhere first. The import
    reports this as a conflict and continues.
11. **ERPNext's chart importer leaves an item tax template behind**, which then blocks
    deleting the old tax account. Replacing the chart removes it first.
12. **Applying the PCGE takes about 25 seconds** on the test machine (1,774 accounts) and runs
    inside one web request. A slow server could time out; it would then need a background job.

## 5. Known gaps and risks

- **Cancellation is not restricted.** A submitted Factura can be cancelled in ERPNext. Under
  SUNAT rules that needs a comunicación de baja or a credit note. This belongs to the
  e-invoicing step; until then, cancelling is a procedural matter.
- **Catalogue 10 (debit note reasons)** ships codes 01–03, the ones found in an official
  SUNAT annex. Codes 10 and 11 (export / IVAP adjustments) appear in third-party sources only
  and were left out. Add them in the master if confirmed.
- **Comprobante types for purchases.** Catalogue 01 is loaded. The purchase register uses the
  wider "Tabla 10" (recibo por honorarios, DUA, non-domiciled documents...). Not loaded.
- **Ubigeo data** must come from the official INEI/SUNAT list.
- **Identity duplicates** are checked by the application, not by a database constraint. Two
  users saving the same new RUC in the same instant could both succeed.
- **Submissions in one series are serialized.** The row lock is held until the invoice
  finishes posting. Correct, but high-volume series queue behind each other.
- **Uninstalling** leaves the custom fields and their data in place.
- **Series of received vouchers** must have exactly four characters for types 01/03/07/08;
  three-digit series of old paper documents have to be entered with a leading zero.

## 2b. Stage 2: PCGE and IGV

### Sources

- **PCGE Modificado 2019**, Consejo Normativo de Contabilidad / MEF, approved by Resolución CNC
  N.° 002-2019-EF/30, mandatory since 1 January 2020. Taken from the MEF's own PDF. No later
  version was found on the MEF site.
- **IGV rate:** SUNAT's guidance page states 18% on taxed operations. Ley N.° 32387 changes how
  that 18% is split between IGV and IPM (2026: 15.5% + 2.5%; the proposal's "16% + 2%" is the
  split of earlier years). The total is unchanged, and both are booked together on 40111.
- **IGV affectation codes:** SUNAT catalogue 07 (Anexo E, R.S. 245-2017/SUNAT).

### The chart

- 1,764 catalogue accounts (elements 1 to 8) plus 10 element roots. Elements 9 (analytic
  costs) and 0 (memorandum accounts) have a root only: the MEF catalogue does not develop them.
- The MEF document contains misprints (repeated or misplaced codes). 13 codes and 5 names were
  corrected; each one is listed in `data/pcge_2019_notes.json` with the reason.
- Checked two ways: the tree is consistent (no repeated code, every account has its parent),
  and all 1,218 last-level codes match an independent copy of the plan except the corrected
  misprints. Account *names* were compared too; no transcription error was found, but names
  were not proof-read line by line against the PDF by a person.

### What the two actions do (Company form → "Peru" menu)

- **Apply PCGE 2019.** Adds the catalogue accounts the company lacks. Never deletes, renames
  or re-types an existing account; running it again creates nothing. With "delete the current
  chart first" it replaces ERPNext's standard chart, which is only allowed while the company
  has no ledger entries. A preview is shown before anything is written.
- **Set Up IGV.** Creates four tax categories, four sales templates (18%, and 0% for
  exonerado / inafecto / exportación), three purchase templates and the tax rules that link
  them. Disables the "Peru Tax" template ERPNext creates on its own.
- **`import_client_accounts`** (function only, no screen yet) places the company's own
  sub-accounts under the PCGE, with a dry run and a report of rejected rows and conflicts.

## 6. Where things are

```
erpnext_peru/
  utils/          pure Python, no Frappe: identity.py, voucher.py, amount_in_words.py, pcge.py
  accounts/       pcge.py (apply / merge), igv.py (templates), api.py (form actions)
  public/js/      company.js (the "Peru" menu on the Company form)
  overrides/      document hooks: party, company, address, sales_invoice, purchase_invoice
  setup/          custom_fields.py (all pe_* fields), install.py, ubigeo.py (CSV loader)
  data/           sunat_catalogues.json, pcge_2019.csv, pcge_2019_notes.json (with sources)
  erpnext_peru/doctype/   catalogue masters, Ubigeo, SUNAT Voucher Series
  translations/es.csv
  tests/
```

Annexure A scenarios covered by a test: CoA-UC-01..03, CoA-CC-01..04, MD-UC-01..03,
MD-CC-01..04, TX-UC-01..03, TX-CC-01..03. Test names carry the scenario ID.
