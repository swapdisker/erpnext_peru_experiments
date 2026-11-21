# erpnext_peru — features

Version 0.2.0. *[Versión en español](FUNCIONALIDADES.md).*

This describes what the app does from the user's side. It is a prototype: read
[HANDOVER.md](HANDOVER.md) for what has and has not been verified, and for the accounting
choices that still need an accountant.

## Contents

1. [Where it applies](#1-where-it-applies)
2. [The Peru icon and workspace](#2-the-peru-icon-and-workspace)
3. [Identity documents of customers and suppliers](#3-identity-documents-of-customers-and-suppliers)
4. [Company RUC](#4-company-ruc)
5. [Addresses and Ubigeo](#5-addresses-and-ubigeo)
6. [Sales invoices: comprobantes de pago](#6-sales-invoices-comprobantes-de-pago)
7. [Voucher series and numbering](#7-voucher-series-and-numbering)
8. [Purchase invoices: the supplier's document](#8-purchase-invoices-the-suppliers-document)
9. [Chart of accounts: PCGE 2019](#9-chart-of-accounts-pcge-2019)
10. [IGV](#10-igv)
11. [SUNAT catalogues](#11-sunat-catalogues)
12. [Amount in words](#12-amount-in-words)
13. [First-time setup](#first-time-setup)
14. [What is not included](#14-what-is-not-included)

## 1. Where it applies

- The invoice rules apply only to companies whose **country is Peru**. Companies of other
  countries on the same site are left untouched.
- **Opening invoices** ("Is Opening Entry" = Yes) are exempt from the invoice rules.
- **Point of sale.** Each sale at the counter is a Sales Invoice (the default in ERPNext v16's
  POS Settings), so it is a comprobante like any other: it gets a type, series and number on
  submission, and the S/ 700 rule applies. A return made at the counter is a credit note whose
  reason is filled in for you when the return is submitted, from the cart as it is at that
  moment: `06` (total return) when every item of the sale comes back in full, `07` (return by
  item) otherwise. A reason chosen by hand is kept. If POS Settings are switched to POS Invoices, the
  invoice ERPNext builds when the shift is closed is exempt instead: it gets no type or number.
- The identity document rules apply to any customer or supplier that has an identity document
  filled in. A party without one is left untouched.
- The interface is available in English and Spanish.

## 2. The Peru icon and workspace

A **Peru** icon on the apps screen (the home page), shown to desk users only. It opens the
workspace; the sidebar beside it is built by Frappe.

A **Peru** workspace with:

- shortcuts to SUNAT Voucher Series, Company, Customer, Supplier, Sales Invoice and Purchase
  Invoice;
- a **Setup** card: company, voucher series, chart of accounts, tax templates, tax categories;
- a **Documents** card: invoices, customers, suppliers, addresses;
- a **SUNAT Catalogues** card: the five catalogues and Ubigeo.

## 3. Identity documents of customers and suppliers

Two fields on Customer and Supplier, also shown in the "new customer / supplier" pop-up:

| Field | Content |
|---|---|
| Identity Document Type | A code of SUNAT catalogue 06: `6` RUC, `1` DNI, `4` carnet de extranjería, `7` passport, `0` non-domiciled without RUC, and others |
| Identity Document Number | The number, without spaces |

What happens on save:

- **RUC:** must have 11 digits, start with 10, 15, 16, 17 or 20, and have a correct check digit
  (modulus 11). A mistyped digit is caught.
- **DNI:** must have exactly 8 digits. Leading zeros are kept.
- **Carnet de extranjería and passport:** letters and digits only, up to 12 characters.
- **Other types:** up to 15 characters.
- Spaces are removed and letters are upper-cased.
- A type without a number, or a number without a type, is rejected.
- **Duplicates:** the same document cannot be registered twice among customers, nor twice
  among suppliers. The message links to the existing record. The same RUC may exist once as a
  customer and once as a supplier. The database refuses duplicates as well.
- The number is copied to ERPNext's **Tax ID** field. Removing the document also removes that
  copy, unless the Tax ID was changed separately.

Not checked: whether the taxpayer exists or is active with SUNAT.

## 4. Company RUC

For a company whose country is Peru, the **Tax ID** field, when filled in, must be a valid RUC.
It may be left empty while the company is being set up, but a company without a valid RUC
cannot submit sales invoices.

## 5. Addresses and Ubigeo

- Addresses have a **Ubigeo** field (the six-digit district code).
- When a Ubigeo is chosen, the city, county and state are filled from it if they are empty.
  What the user typed is never overwritten.
- An address in Peru saved without Ubigeo shows a warning and is saved anyway.
- **All 1,893 districts are included** (25 departments, 196 provinces), with INEI's codes,
  the ones electronic invoices use, and their names with accents. Sources: INEI's code list
  and its directory of municipalities of November 2026, cross-checked with SUNAT's Catálogo 13.
  The list is loaded on install and on every update.
- In the Ubigeo field you can type the district, province or department, with or without
  accents: "jesus maria" finds 150113, Jesús María, Lima, Lima.
- Codes INEI no longer lists are **disabled**, not deleted: addresses that use them keep them
  and show a warning when saved; new addresses cannot choose them.
- The list is reference data. Edits made by hand are undone by the next update.

## 6. Sales invoices: comprobantes de pago

### Fields

A section **Comprobante de pago (SUNAT)** on the Sales Invoice:

| Field | Content |
|---|---|
| Comprobante Type | `01` Factura, `03` Boleta de venta, `07` Nota de crédito, `08` Nota de débito |
| Series | Four characters, for example `F001` |
| Number | Assigned on submission; read-only |
| Voucher Number | Series and number together, for example `F001-00000123`; read-only, searchable |
| Customer Identity Document Type / Number | Copied from the customer; read-only |
| Credit Note Reason | SUNAT catalogue 09; shown on returns |
| Debit Note Reason | SUNAT catalogue 10; shown on debit notes |
| Modified Comprobante Type / Voucher Number | The comprobante a note modifies |

### What is filled in for you

- **Type:** left empty, it becomes Factura when the customer has a RUC and Boleta otherwise. A
  return becomes a Nota de crédito and a debit note a Nota de débito. A type filled in this way
  is set again when what decided it changes, such as the draft's customer: a Boleta saved for
  a customer without RUC becomes a Factura when the customer is changed to one with RUC. A
  type chosen by hand is kept.
- **Series:** left empty, it is filled in when the company has exactly one enabled series for
  that type. With several, you choose. When the type of a saved draft changes, or the
  modified comprobante type of a note, a series left over from before that does not fit any
  more is chosen again the same way.
- **Modified comprobante:** on a note created from an invoice issued in this system, the type
  and number of that invoice are filled in and cannot be overridden by hand.
- **Customer document:** copied from the customer on every save until submission. After
  submission it no longer changes, even if the customer record is corrected.

A Boleta for a customer who has a RUC is allowed, with a warning.

### Rules checked on save

- The type must be one of 01, 03, 07, 08 and must fit the document: a return is 07, a debit
  note is 08, a plain invoice is 01 or 03.
- The series must have four letters or digits and start with `F` for a Factura and `B` for a
  Boleta. A note's series starts with the letter of the comprobante it modifies.
- A note can only modify a Factura or a Boleta; the Modified Comprobante Type field offers only
  those two.

### Rules checked on submission

The invoice is not submitted, and no number is used, unless:

1. the company has a valid RUC;
2. once the IGV templates exist, the invoice has at least one tax line (the 18% one, or one
   of the 0% ones for exempt, unaffected or export sales);
3. for a **Factura**, the customer is identified with a RUC (or with type `0`, non-domiciled,
   intended for exports);
4. for a **Boleta de venta** whose total in soles, IGV included, is **more than S/ 700.00**,
   the customer has an identity document (S/ 700.00 exactly is allowed without one); the same
   applies to a credit or debit note that modifies a Boleta, measured on the note's amount;
5. for a **credit or debit note**, a reason is selected and the modified comprobante is
   indicated (its type and its number, for example `F001-00000123`);
6. the series is registered and enabled in SUNAT Voucher Series.

For an invoice in another currency, the S/ 700 threshold is measured on the amount converted
to soles. This also holds for a company that keeps its books in another currency: the total is
converted with the exchange rate of the posting date, and the Boleta is refused if no rate to
PEN is registered in Currency Exchange.

### After submission

- The comprobante fields cannot be changed.
- A cancelled invoice keeps its number. Amending it creates a new invoice with a new number.
- An invoice that has a voucher number cannot be deleted. Once a company has issued
  any comprobante, the **Delete Transactions** button of the Company form is refused with a
  message: it would delete the issued invoices. This holds whatever the company's country is
  now, and also for a "Retry" of a deletion that failed earlier. The voucher series are never
  deleted with the transactions: each keeps its last number issued.

Cancellation itself is not restricted: see [section 14](#14-what-is-not-included).

## 7. Voucher series and numbering

**SUNAT Voucher Series** registers each series a company issues:

| Field | Content |
|---|---|
| Company | A Peruvian company |
| Comprobante Type | 01, 03, 07 or 08 |
| Series | Four characters. The same code may be used for different types; each has its own numbering |
| Last Number Issued | The next voucher gets this number plus one |
| Enabled | A disabled series cannot be used |

- To continue the numbering of a previous system, set **Last Number Issued** once.
- It cannot be set below a number that has already been issued, including cancelled vouchers.
- Company, type and series cannot be changed after creation.
- Each series can be registered only once per company and type, so it has a single counter.
- A series that has been used cannot be deleted; disable it instead.
- Numbers go from 1 to 99,999,999 and are shown with eight digits.

How numbers behave:

- They are assigned at the moment of submission, never typed.
- They are consecutive per company, type and series, also when several users submit at once.
- An invoice that fails to submit does not consume a number.

## 8. Purchase invoices: the supplier's document

A section **Comprobante de pago (SUNAT)** on the Purchase Invoice:

| Field | Content |
|---|---|
| Comprobante Type | The type printed on the supplier's document (SUNAT catalogue 01) |
| Series / Number | As printed on the document |
| Voucher Number | Series and number together; read-only, searchable |
| Modified Comprobante Type / Voucher Number | For credit and debit notes |

These fields are optional at this stage. When filled in:

- for Facturas, Boletas and their notes, the series must have four characters and the number
  up to eight digits; `F001` / `123` is stored as `F001-00000123`;
- other document types (public service receipts and so on) are checked loosely: up to 20
  letters, digits or hyphens;
- a number without a type is rejected;
- **duplicates:** the same document of the same supplier cannot be registered twice in a
  company, however it is typed, not even by two users at the same moment. A cancelled
  document can be registered again;
- a purchase return must be type 07, and a type 07 document must be entered as a return;
- a credit or debit note needs the modified comprobante to be submitted; it is filled in
  automatically when the note is created from an invoice that has it;
- ERPNext's **Supplier Invoice No** is filled with the voucher number if it is empty, and
  follows the voucher number when that is corrected or removed. A Supplier Invoice No typed
  separately is kept.

## 9. Chart of accounts: PCGE 2019

The app carries the catalogue of the **Plan Contable General Empresarial Modificado 2019**
published by the MEF: 1,764 accounts in elements 1 to 8, down to five digits (six in accounts
682 and 683). Elements 9 and 0 have a root only, because the catalogue does not develop them.

### Apply PCGE 2019

On the Company form, menu **Peru → Apply PCGE 2019**. It asks one question, shows a preview,
and writes only after you confirm.

| Option | What it does |
|---|---|
| Unticked (default) | Adds the PCGE accounts the company does not have. Nothing existing is deleted, renamed or changed. Running it again creates nothing. |
| "Delete the current chart of accounts first" | Removes the company's current chart, then creates the PCGE. Only possible while the company has **no ledger entries**. Use it on a new company to replace ERPNext's standard chart. |

The preview and the final report list:

- how many accounts are created and how many already existed;
- **name differences:** accounts the company already has under the same code with another
  name. The company's name is kept;
- **conflicts**, where nothing is overwritten and a person must decide, for example an account
  the PCGE divides into sub-accounts but the company already posts to directly;
- the company defaults that were set, kept, or left empty.

Each account gets a number, its PCGE name, its place in the tree and a root type (assets,
liabilities, equity, income, expense). Account types are set only where ERPNext needs them:
cash, bank, receivable, payable, tax, cost of sales, income.

Company defaults set if empty: receivable `1212`, payable `4212`, income `70121`, and round-off
`7599` (provisional). Cash, bank, cost of sales, exchange difference and stock accounts are left
for the accountant.

Applying runs in the background and takes about half a minute; the page waits and then shows the result. If it fails, nothing is changed and the reason is shown. It needs a background worker, which every standard installation has. Only one chart of accounts is changed at a time on a site: if another company's chart is being changed, the second run waits up to two minutes and is then refused with a message.

### The company's own sub-accounts

For developers: `erpnext_peru.accounts.pcge.import_client_accounts(company, rows, dry_run=True)`
adds accounts such as `104101 BCP Soles` under the right PCGE account. It rejects bad rows with
a reason and continues, reports conflicts, and has a dry run. The accounts below a rejected
row are rejected too, instead of being placed under a higher account. There is no screen for
it yet.

## 10. IGV

On the Company form, menu **Peru → Set Up IGV**. The company must have account `40111`
(apply the PCGE first). It creates:

| | |
|---|---|
| Tax categories | IGV - Gravado, IGV - Exonerado, IGV - Inafecto, IGV - Exportación |
| Sales templates | IGV 18% - Ventas gravadas (the default); IGV 0% - Ventas exoneradas; IGV 0% - Ventas inafectas; IGV 0% - Exportación |
| Purchase templates | IGV 18% - Compras gravadas (the default); IGV 0% - Compras exoneradas; IGV 0% - Compras inafectas |
| Tax rules | Choosing a tax category on a document selects its template |

- The 18% is calculated on the net total and posted to `40111`: credited on sales, debited on
  purchases, so the balance of the account is the IGV payable.
- The 0% templates post nothing. They exist so that the document states how it is treated.
- Each sales template carries its SUNAT catalogue 07 code (10, 20, 30, 40).
- The "Peru Tax" template at 16% that ERPNext creates on its own is disabled. If ERPNext
  creates it again (for example after the chart is replaced), saving the company disables it.
- Running it again creates nothing and does not undo local changes.
- If the site rounds half-céntimos to the even digit, a warning says so.

Example: a taxed sale of S/ 1,000 gives S/ 180 of IGV and a total of S/ 1,180.

Not handled: invoices that mix taxed and exempt items, and the reduced rate for small
restaurants and hotels.

## 11. SUNAT catalogues

Editable masters, loaded on install. Entries you change or disable are kept on upgrade.

| Master | Catalogue | Entries |
|---|---|---|
| SUNAT Comprobante Type | 01 | 17 |
| SUNAT Identity Document Type | 06 | 13 |
| SUNAT IGV Affectation Type | 07 | 18 |
| SUNAT Credit Note Reason | 09 | 13 |
| SUNAT Debit Note Reason | 10 | 3 |
| Ubigeo | Catálogo 13 (INEI codes) | 1,893 districts |

## 12. Amount in words

For developers building a print format:
`erpnext_peru.utils.amount_in_words.amount_in_words("1234.56", "PEN")` returns
`SON: MIL DOSCIENTOS TREINTA Y CUATRO CON 56/100 SOLES`. It supports PEN, USD and EUR.

## First-time setup

1. Install the app on the site.
2. In **Global Defaults**, turn on **Disable Rounded Total**: comprobantes are issued to the
   céntimo, and ERPNext otherwise rounds the total owed.
3. Open the company and enter its RUC in **Tax ID**.
4. On the company, menu **Peru → Apply PCGE 2019**. On a new company, tick "Delete the current
   chart of accounts first".
5. On the company, menu **Peru → Set Up IGV**.
6. In **SUNAT Voucher Series**, create the series: for example `F001` for type 01, `B001` for
   03, `FC01` and `BC01` for 07.
7. Register customers with their identity document, and issue the first invoice.

Before purchase invoices can be submitted, decide how inventory is booked: with ERPNext's
"perpetual inventory" on, every purchase invoice needs stock accounts the PCGE setup does not
define. See [HANDOVER.md](HANDOVER.md), section 7.

## 14. What is not included

- Electronic invoicing: no XML, no sending to SUNAT or a provider, no CDR, no QR.
- Restriction on cancelling an issued comprobante (comunicación de baja).
- A print format.
- SIRE sales and purchase registers.
- CONCAR import, opening balances, reconciliation.
- Destination entries (6 → 9 / 79).
- The daily SUNAT exchange rate.
- The wider list of document types for purchases.
- Data for real use: everything was checked on test sites with made-up companies, customers and
  amounts, on ERPNext v16.
