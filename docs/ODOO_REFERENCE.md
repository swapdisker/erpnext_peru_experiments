# Odoo's Peru localization, as a reference

Version 1, 18 November 2026. How Odoo implements Peru, compared area by area with this app, and
what is worth taking from it. The proposal names Odoo `l10n_pe` as a functional reference, to
be read as a specification only: **no Odoo code is copied into this app.**

## Contents

1. [What was looked at](#1-what-was-looked-at)
2. [Summary](#2-summary)
3. [Odoo's modules](#3-odoos-modules)
4. [Area by area](#4-area-by-area)
5. [Where this app is ahead](#5-where-this-app-is-ahead)
6. [Suggested changes, in order](#6-suggested-changes-in-order)
7. [Questions for the accountant](#7-questions-for-the-accountant)

## 1. What was looked at

| Source | What | Licence |
|---|---|---|
| Odoo source, branch 19.0 | `l10n_pe`, `l10n_pe_pos`, `l10n_latam_base`, `l10n_latam_invoice_document`: models, data files, the POS scripts | LGPL-3 (Community) |
| A production Odoo database, Odoo SaaS 19.3 with Enterprise | Installed modules, settings, journals, one test Boleta, reports, and the field definitions of the Peru fields (`fields_get`) | Enterprise code is not public; only its behaviour and field definitions were read |
| [Odoo's Peru documentation](https://www.odoo.com/documentation/latest/applications/finance/fiscal_localizations/peru.html) | E-invoicing workflow, cancellation, delivery guide | |

Nothing was changed in the Odoo database, and no customer data from it is reproduced here.

## 2. Summary

Odoo covers more ground than this app, mostly in places this app has not reached yet:
e-invoicing, SIRE and PLE files, detracciones, imports, non-domiciled suppliers and the delivery
guide. Its data model for those areas is a useful checklist for steps 5 and 7 of the proposal.

Three things that Odoo has and the proposal's **Phase 1** already promises are missing here:

1. **IGV per invoice line.** Odoo carries the IGV affectation code (catalogue 07) on each tax
   and each line, so one invoice can mix taxed, exempt and free items. This app sets it per
   invoice and creates no item tax templates, although step 4 of the proposal lists them.
2. **The daily SUNAT exchange rate.** Odoo fetches it automatically ("[PE] SUNAT").
3. **The full list of supplier documents.** Odoo loads the 58 document codes of the purchase
   register's list (Tabla 11); this app has only the 17 of the e-invoicing catalogue 01.
   Missing ones that a trading company meets often: `02` Recibo por Honorarios, `50` DUA
   (imports), `91` non-domiciled supplier.

One thing Odoo does that SIRE needs, and nothing in this app does yet: **purchase IGV split by
destination** (taxed, mixed and non-taxed operations), which are separate columns of the
purchase register.

Where this app is ahead: gapless numbering with locking, the S/ 700 Boleta rule, current Ubigeo
and correct PCGE names (section 5).

## 3. Odoo's modules

| Module | Edition | What it does | Installed in the database looked at |
|---|---|---|---|
| `l10n_pe` Perú - Contabilidad | Community | Chart, taxes, document and identity types, Ubigeo, banks | Yes |
| `l10n_latam_base`, `l10n_latam_invoice_document` | Community | Identity types and the "documents" engine shared by Latin American countries | Yes (dependencies) |
| `l10n_pe_pos` | Community | Point of sale rules | No |
| `l10n_pe_edi` EDI para Perú | Enterprise | UBL 2.1 e-invoicing, cancellation | Yes |
| `l10n_pe_reports` Perú - Informes contables | Enterprise | PLE and SIRE files, balance sheet, income statement | Yes |
| Peru - Inventory and Balance Reports | Enterprise | Libro de Inventarios y Balances | No |
| Perú - Nota de entrega electrónica (`l10n_pe_edi_stock_20`) | Enterprise | Electronic delivery guide (GRE 2.0) | Yes |
| Perú - Informes de stock, Stock Reports Landed Costs | Enterprise | Inventory books | No |

Books are switched on by installing modules. There is no tax-regime setting anywhere: the
accountant decides which files to produce.

## 4. Area by area

Each area: how Odoo does it, how this app does it, and what to take.

### 4.1 Document types

**Odoo.** 60 records (58 codes), each with a code, a one-letter prefix (`F`, `B`, `R`...) and
an internal kind (invoice, credit note, debit note). Sales offer `01`, `03`, `07`, `08`, `20`,
`40`; when the customer is not identified with a RUC, only the Boleta and the Boleta notes are
offered. There are separate credit-note and debit-note types for Facturas and for Boletas.

**This app.** 17 types, of which `01`, `03`, `07`, `08` can be issued. Same Factura / Boleta rule
(a Factura needs a RUC, or type `0` for exports).

**Two different SUNAT lists.** An export of the production database (60 records, 58 codes;
`07` and `08` appear twice, once for Facturas and once for Boletas) shows where the difference
comes from. This app's 17 types are exactly catalogue 01 of the e-invoicing annex (Anexo 8),
including the four delivery-guide codes `09`, `31`, `71`, `72`, which Odoo does not have (its
guide lives in the stock module). Odoo's list is the one the purchase register uses: Tabla 11
of R.S. 040-2022/SUNAT for the RCE, which adds documents nobody issues electronically through
this app (`02`, `05`, `10`, `50`, `91`...). For the 13 codes in both lists the meaning is the
same; the wording differs (Odoo uses the longer register descriptions).

**Take.** Keep catalogue 01 for what the app issues, and add a second list, the register's
Tabla 11, for supplier documents, loaded from SUNAT's table rather than from Odoo. Types the
client is likely to meet: `02` Recibo por Honorarios, `04` Liquidación de compra, `10` Recibo
por arrendamiento, `50` DUA, `91` Comprobante de no domiciliado (and its notes `97`, `98`).

### 4.2 Identity documents (catalogue 06)

**Odoo.** The same 13 codes as this app (`0`, `1`, `4`, `6`, `7`, `A`–`H`), on the partner. The
RUC is the type flagged as the tax number.

**This app.** The same, with RUC check-digit and DNI validation and duplicate checks.

**Take.** Nothing.

### 4.3 Numbering and series

**Odoo.** A journal has "Use Documents" ticked; the number is the document's letter, the series
and eight digits, for example `B BOL-00000001`. Each document type can have its own sequence
per journal, and credit and debit notes can have dedicated sequences. On purchases, the number
of a Factura, Boleta or note is padded to eight digits, and a database index keeps a supplier's
document unique per type among posted bills. In the database looked at, a posted test Boleta
had been reset to draft and cancelled, keeping its number (the database is in test mode).

**This app.** A SUNAT Voucher Series per company, type and series; the number is allocated at
submission without gaps, under a row lock, and protected by unique indexes; an invoice with a
number cannot be deleted. Purchases are padded and unique per supplier, as in Odoo.

**Take.** Nothing; this app is stricter (section 5).

### 4.4 IGV and other taxes

**Odoo.** Each tax carries the SUNAT tax code (catalogue 05: `1000` IGV, `9995` export, `9996`
free, `9997` exempt, `9998` unaffected, `2000` ISC, `7152` ICBPER...), the UN/ECE category, and
an IGV affectation code (catalogue 07). Each invoice line carries its own affectation code too,
plus a discount or charge code (catalogue 53). Taxes shipped:

| | Sales | Purchases |
|---|---|---|
| IGV 18% | to 40111 | three variants by destination of the purchase: taxed operations (40111), taxed and non-taxed (40117), non-taxed (40116) |
| 0% | exempt, unaffected, export, free | exempt, unaffected, export, free |
| Others | ISC (4012), IGV withholding −3% (40114) | |
| Free transfer | a group of three taxes: −100% of the base, 18% IGV to 40111, −18% to expense 6411 | |

**This app.** Four sales and three purchase templates, chosen per invoice through tax
categories. The sales templates carry the catalogue 07 code. Mixed invoices and free transfers
are not handled; no item tax templates.

**Take.**

- *Item tax templates per affectation* (gravado, exonerado, inafecto, exportación), so items
  set the line's treatment and one invoice can mix them. Promised in step 4. Store the
  catalogue 07 code per line, because the UBL needs it per line.
- *The SUNAT tax code (catalogue 05)* on each template, for the UBL.
- *Purchase IGV by destination*, as three templates, because the RCE reports the three bases
  separately. Which accounts receive them is for the accountant (section 7).
- Later: free transfers (codes 11–16, 21, 31–36) with the IGV booked as expense, ISC, ICBPER,
  the 3% withholding.

### 4.5 Chart of accounts

**Odoo.** 1,228 accounts, seven-digit codes in use (`7012100`), names in Spanish and English.
Company defaults: receivable 1213, payable 4212, income 70121, expense 6329, exchange
difference 776 / 676, early-payment discount 675 / 775, a POS receivable 1215, cash prefix
1031, bank 1041, internal transfers 1051. Odoo names both 4211 and 4212 "No emitidas"; in
the MEF's PCGE 2019, 4212 is **Emitidas**.

**This app.** The PCGE 2019 in full (1,764 codes) with the MEF's names, merged into the client's
chart. Defaults: receivable 1212, payable 4212, income 70121, round-off 7599 (provisional).
Expense, exchange difference, cash, bank and stock accounts are left to the accountant.

**Take.** Odoo's choices as a starting proposal for the defaults left open (section 7), not as
facts.

**Account by account** (from an export of the chart of the production database, 1,236
accounts, compared with `data/pcge_2019.csv`):

- *Codes.* Odoo pads every code with zeros to seven digits (`0111000`, `4212000`). Matched
  against Odoo's chart template, every padded code maps back to exactly one template code, so
  the conversion is safe for an import. All 1,228 template accounts are in the export; the
  other 8 were created by Odoo in the database (bank, suspense, outstanding receipts and
  payments, internal transfer, cash difference gain and loss, undistributed earnings), five
  under 1041 / 1051 and three under `999`, outside the PCGE.
- *Against the PCGE.* 1,210 of Odoo's codes are last-level accounts of the PCGE; none is a
  group account. Odoo has 18 codes the PCGE does not: 16 memorandum accounts (element 0,
  which the MEF catalogue leaves to each company), its own `1215` for the point of sale, and
  `63432`. The PCGE has 8 last-level accounts Odoo lacks: 36404, 36472, 36473, 36474, 39352,
  63422, 6343 and 683151.
- *They come from the MEF's misprints.* The PDF prints seven of them under wrong codes (33404,
  38472–38474, 38352, 63432, 683351); this app corrects each one
  (`data/pcge_2019_notes.json`). Odoo kept one as printed (`63432` for 63422) and dropped the
  other six. The eighth, 6343, is printed correctly, but Odoo's 63432 sits under it and turns
  it into a group.
- *Names.* Odoo writes "parent - child" names; ignoring that, 1,115 names agree. Of the other
  95, most are wording variants (Costos / Costo, Propiedades / Propiedad) or fragments left in
  English ("Fair value", "Financial leasing", "Basic services - Phone"). Those that change the
  meaning, where this app follows the MEF text: 4212 and 4312 (Odoo: No emitidas; MEF:
  Emitidas), 2984 (Odoo: Materias primas; MEF: Envases y embalajes), 36402 and 36405–36408
  (Odoo mixes "en producción" and "en desarrollo"), 66131 and 76131 (Odoo gives an unrelated
  name).
- *Types.* Odoo files element 8 under equity (882 as a non-current liability) and 3711 / 3712
  as liabilities; this app makes element 8 an expense root and 37 an asset. Odoo marks 84 more
  accounts as receivable (122, 14, 16...) and 41 more as payable (41, 422, 46, 47...); this app
  types only trade receivables and payables, because in ERPNext a receivable or payable
  account needs a party on every entry.

### 4.6 Addresses and Ubigeo

**Odoo.** Department as the state, 196 provinces as cities, 1,875 districts, with the district on
the partner and in the printed address. The website checkout requires department, province and
district.

**This app.** 1,893 districts from INEI, current to 2026, with accents; codes that disappear are
disabled, never deleted; choosing a district fills city, county and state.

**Take.** Nothing. This app's list is more current.

### 4.7 Point of sale

**Odoo** (`l10n_pe_pos`). A "Consumidor Final" customer, identified as DNI `00000000`, is the
default customer of every order and cannot be deleted. The payment screen ticks "Invoice" on
every order. A customer
without an identity number is stopped at payment and the customer form opens. A refund keeps
the original customer.

**This app.** On v16 every counter sale is a Sales Invoice and a comprobante; a Boleta above
S/ 700 needs the customer's document; returns get reason 06 or 07 automatically.

**Take.** A standard anonymous customer created by setup and protected from deletion, so every
company has the same one. How it is identified in the e-invoice (`00000000`, or the "-" that
SUNAT accepts below S/ 700) is decided in step 5. Odoo stops any customer without a number,
even below S/ 700, which is stricter than the rule.

### 4.8 Credit and debit notes

**Odoo.** The reason is chosen in the "Add Credit Note" / "Add Debit Note" dialogs: 12 credit
reasons; debit reasons `01`, `02`, `03`, `11`, `12`, `13`.

**This app.** Catalogue 09 with 13 reasons; catalogue 10 with 3 (`01`–`03`).

**Take.** Check catalogue 10 against SUNAT's current annex; codes 11 and 12 (export and IVAP
adjustments) appear in Odoo and not here.

### 4.9 Electronic invoicing (proposal step 5)

**Odoo.**

- *Provider:* Odoo's own service (IAP), Estela (formerly Digiflow), or SUNAT directly; a
  certificate (.pfx) and the SOL user when not using IAP; a test-environment switch.
- *Sending is asynchronous:* posting an invoice marks it "To be sent"; a job sends every hour, or
  the user presses "Send now". States: to send, sent, cancelled. On a rejection the invoice
  stays "to send": master data is fixed and the send retried, or the invoice is reset to draft,
  corrected and resent.
- *Cancellation:* "Request Cancellation" with a reason; the request is sent, and the ticket and
  CDR are kept.
- *Data the UBL needs, and where Odoo keeps it:*

| Data | Catalogue | Where in Odoo |
|---|---|---|
| Operation type (`0101` internal sale, `0200` export, `1001` subject to detracción...) | 51 | Invoice; default `0101` |
| Legends | 52 | Invoice (code and text) |
| IGV affectation per line | 07 | Tax and line |
| Discount / charge code | 53 | Line |
| Unit of measure code (`NIU`, `KGM`, `LTR`, `HUR`...) | 03 | Unit of measure |
| Product code | 25 (UNSPSC) | Product |
| Establishment code (`0000` when unknown) | | Company |
| SUNAT tax code | 05 | Tax |

**This app.** Nothing yet; the Factura / Boleta rules, numbering and reasons are in place.

**Take.** The table above is the checklist of fields to add before building the UBL. Copy the
asynchronous design: posting never waits on the provider, every document has a state, and a
rejected one can be fixed and resent. The daily summary of Boletas is not described in Odoo's
documentation; check it with the provider chosen.

### 4.10 Detracciones (Phase 2)

**Odoo.** The product carries its catalogue 54 code (48 codes) and percentage; the invoice uses
operation type `1001` and legend `2006`. A purchase bill stores the detracción deposit date and
number, which the purchase register asks for.

**Take.** The same fields when detracciones are built.

### 4.11 Imports and non-domiciled suppliers

**Odoo.** A supplier bill can point to its DUA (type `50`), so the IGV paid at customs is
linked to the purchase. For non-domiciled suppliers a bill has a service modality and a usage
type (SUNAT's table of income types), which the non-domiciled register (RCE 8.5) asks for.

**Take.** If the client imports, the DUA type and the link from the bill to it belong in Phase 1,
because the RCE reports the DUA. The non-domiciled fields only if the client has such
suppliers.

### 4.12 SIRE and PLE files (proposal step 7, and Phase 2)

**Odoo.**

- *SIRE:* the tax report has three variants, RCE 8.4 (purchases), RCE 8.5 (non-domiciled) and
  RVIE 14.4 (sales), each exported as a TXT file.
- *PLE:* the general ledger exports formats 5.1 (Libro Diario), 5.3 (chart used) and 6.1 (Libro
  Mayor). There is no export for 5.2 / 5.4, the simplified Diario for companies up to 300 UIT.
  Inventarios y Balances is a separate module.
- *Settings and fields:* the company states its chart type for the PLE (SUNAT's table of 8 types:
  general business plan, SBS-supervised charts, government, others); a journal entry can be
  marked as the opening or closing entry.
- *Statements:* a Peruvian balance sheet (36 lines) and income statement (18 lines).

**Take.** Build the SIRE files as reports with a TXT export, as Odoo does. For PLE, add the
simplified Diario that Odoo lacks, the chart-type setting and the opening / closing mark.

### 4.13 Exchange rate

**Odoo.** An automatic provider, "[PE] SUNAT (replaces Bank of Peru)".

**This app.** Not included; promised in step 4.

**Take.** A daily job that stores the SUNAT rate in Currency Exchange.

### 4.14 Delivery guide (Phase 2)

**Odoo.** Sender guides only, sent straight to SUNAT's API with a client ID and secret. It needs
the reason for transfer, the start date, the transport type, the vehicle, the driver's licence,
the carrier's MTC number, and each product's tariff item.

**Take.** That list, when the guide is built.

### 4.15 Banks

**Odoo.** 18 Peruvian banks, 9 of them with the bank's SUNAT code filled in.

**Take.** Minor; useful for detracción payments.

### 4.16 Other accounting configuration

From exports of the production database:

- **Journals (8):** Ventas (`INV`, income 7012100), Compras (`FACTU`, expense 6329000), Banco
  (1041001), and five technical ones: miscellaneous, exchange difference, cash-basis taxes,
  inventory valuation, tax returns. ERPNext has no journals; the equivalents are document types
  and naming series. Odoo's journals play the role of CONCAR's subdiarios, which matters for
  the import and for the PLE Diario (each entry carries its origin), not for daily use.
- **Fiscal positions (2):** "Local Perú" and "Extranjero - Exportación", both applied
  automatically by the customer's country. This app's four tax categories (gravado,
  exonerado, inafecto, exportación) do the same job but are chosen, not automatic: a foreign
  customer does not get the export template by itself. Making it automatic is possible with a
  country condition on the tax rule, but an export of services has conditions of its own, so
  that is for the accountant (section 7).
- **Tax return types (3):** "Tax (PE)", an annual corporate-tax closing, and an audit. These
  belong to Odoo's generic tax-return workflow; the "Tax Report (PE)" behind them has no lines,
  so Odoo does not prepare the monthly declaration (Formulario 621). Nothing to take now.
- **Depreciation models (5):** none, and straight line over 3, 5, 10 and 20 years. They are
  Odoo's generic models. The tax maximums are set by article 22 of the income-tax regulation
  (25% for data-processing equipment, 20% for land vehicles, 10% for machinery bought since
  1991) and by article 39 of the law (5% for buildings). Odoo's 5, 10 and 20 years match 20%,
  10% and 5%; it has no 4-year (25%) model for computers, and its 3 years matches only the
  temporary special regimes. Fixed assets are out of Phase 1 (assets come across as balances);
  when they are built, the models should follow the regulation's table.
- **Closing checklist (54 items):** Odoo's generic audit and year-end checklist (bank, payables,
  receivables, inventory, assets, equity...), not Peruvian; several items are left in English
  or follow other countries' rules. Nothing to take.

## 5. Where this app is ahead

- **Numbering.** Gapless allocation under a row lock, tested with parallel connections;
  unique indexes; no deletion of numbered invoices; "Delete Transactions" refused once
  comprobantes exist.
- **S/ 700 Boleta rule** enforced on every sale, including at the counter.
- **POS returns** get their credit note reason automatically.
- **Ubigeo** current to 2026 (1,893 districts against Odoo's 1,875), with retired codes kept.
- **PCGE names** match the MEF's plan (Odoo labels 4212 "No emitidas").
- **Spanish throughout**, and a test suite with a mutation check.

## 6. Suggested changes, in order

**Phase 1 (already in the proposal's scope):**

1. Item tax templates per IGV affectation, with the catalogue 07 code per line (step 4).
2. Daily SUNAT exchange rate (step 4).
3. The purchase register's document list (Tabla 11) for supplier documents, with `02`, `50`,
   `91` first (steps 4 and 7).
4. Purchase IGV split into the three RCE bases (step 7).
5. The fields from the table in 4.9: establishment code, operation type, legends, unit codes,
   product code, tax code (before step 5).
6. Asynchronous sending with states and retry (step 5).
7. SIRE files as reports with a TXT export: RVIE 14.4, RCE 8.4, and 8.5 if needed (step 7).
8. A protected anonymous customer for Boletas and the counter.
9. If the client imports: the DUA link on supplier bills.

**Phase 2:**

10. Detracciones: product code and rate, operation type `1001`, deposit fields on bills.
11. Free transfers with the IGV as expense; ISC; the 3% withholding; perceptions.
12. Debit note reasons 11 and 12, after checking catalogue 10.
13. PLE: 5.1 / 5.3 / 6.1, plus 5.2 / 5.4, the chart-type setting, opening and closing entries;
    then Inventarios y Balances.
14. Delivery guide.

## 7. Questions for the accountant

1. **Default accounts left open:** Odoo uses 776 / 676 for exchange differences, 675 / 775 for
   early-payment discounts, 6329 as the default expense, and 1213 (not 1212) as the receivable.
   Which should this app propose?
2. **Purchase IGV by destination:** which accounts for purchases used in taxed, mixed and
   non-taxed operations? Odoo uses 40111, 40117 and 40116.
3. **Free transfers:** does the client give away goods (samples, promotions)? If so, how should
   the IGV be booked?
4. **Imports and non-domiciled suppliers:** does the client have them? That decides whether
   the DUA and RCE 8.5 belong in Phase 1.
5. **Anonymous customer:** DNI `00000000` like Odoo, or no document below S/ 700?
6. **Memorandum accounts (element 0):** does the client use them? Odoo ships 16; this app none.
7. **Element 8:** expense, as this app sets it, or outside the income statement, as Odoo does?
   It decides where the closing entries (8x to 89 to 59) appear.
8. **Accounts with a party:** which accounts beyond 12 / 13 and 42 / 43 carry a party (staff,
   shareholders, other receivables and payables)? In ERPNext those need the receivable or
   payable type, and it matches the "anexos" the client keeps in CONCAR.
9. **Automatic export template:** should a foreign customer get the export template by itself,
   as Odoo's fiscal position does, or should the user always choose it?
