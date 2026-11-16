# Handover notes — erpnext_peru v0.1.0 (prototype, first stage)

For the team that continues this work and for the accountant who reviews it.

## 1. What this stage covers

Against the Phase 1 proposal ("Step" numbers are the proposal's):

| Proposal item | State |
|---|---|
| Step 2 — custom app, licence, tests | Built. CI workflow written but **never run**. |
| Step 3 — PCGE chart of accounts | **Not started.** |
| Step 4 — identity documents with RUC/DNI validation and duplicate checks | Built and tested. |
| Step 4 — comprobante type and series-number on invoices, note reason and reference | Built and tested. |
| Step 4 — Ubigeo field and master | Field, master and CSV loader built. **District data not loaded.** |
| Step 4 — Boleta rule above S/ 700 | Built and tested. |
| Step 4 — IGV tax templates | **Not started** (posts to the ledger). |
| Step 4 — daily SUNAT exchange rate | **Not started.** |
| Step 5 — e-invoicing | **Not started.** |
| Step 6 — print format | Only the amount-in-words function. |
| CONCAR toolkit, SIRE, destination entries | **Not started.** |

Nothing in this stage creates or changes a ledger entry. The hooks add identification data
to documents and block submissions that break a rule.

## 2. How it was verified

- **180 automated tests**, all passing on Frappe 15.126.1 / ERPNext 15.125.0 / MariaDB 10.11:
  52 pure tests (validators, number formatting, translations) and 128 that run against a real
  ERPNext site.
- **Mutation check:** 35 deliberate bugs were injected one at a time (wrong check-digit weight,
  `>` changed to `>=` on the S/ 700 rule, row lock removed, duplicate check removed...). Every
  one made at least one test fail.
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
  form was opened in a browser. Field placement, the `depends_on` visibility of the note
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

## 6. Where things are

```
erpnext_peru/
  utils/          pure Python, no Frappe: identity.py, voucher.py, amount_in_words.py
  overrides/      document hooks: party, company, address, sales_invoice, purchase_invoice
  setup/          custom_fields.py (all pe_* fields), install.py, ubigeo.py (CSV loader)
  data/           sunat_catalogues.json (with sources)
  erpnext_peru/doctype/   catalogue masters, Ubigeo, SUNAT Voucher Series
  translations/es.csv
  tests/
```

Annexure A scenarios covered by a test: MD-UC-01..03, MD-CC-01..04, TX-UC-03, TX-CC-01..03,
and the comprobante-field part of TX-UC-01. Test names carry the scenario ID.
