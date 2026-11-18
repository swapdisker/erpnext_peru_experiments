# ERPNext Peru

> # ⚠️ DO NOT USE — LOCAL EXPERIMENT
>
> **This repository is a personal, local experiment. It is not a product and must not be
> installed on any site that holds real data.**
>
> - It is an unfinished prototype. Expect bugs, wrong behaviour and code that will be rewritten.
> - No accountant has reviewed it. Its rules may be incorrect under Peruvian tax law.
> - Its screens have barely been tried in a browser, and it has never run in production.
> - It can block invoices and assign legal document numbers. A mistake there has real consequences.
> - There is no support, no warranty and no promise that later versions will be compatible.
>
> If you need a Peruvian localization for ERPNext, do not start from this code.
>
> **NO USAR — EXPERIMENTO LOCAL.** Este repositorio es un experimento personal e inconcluso.
> Puede tener errores y reglas tributarias incorrectas, y ningún contador lo ha revisado. No lo
> instale en un sitio con datos reales.

Peruvian localization for [ERPNext](https://github.com/frappe/erpnext) v16 (Frappe and
ERPNext 16, Python 3.14), as a separate Frappe app. Nothing in ERPNext core is modified.

**Status:** prototype, v0.2.0. Not reviewed by an accountant.

## What it does

- **Identity documents:** RUC and DNI validation on customers and suppliers, with duplicate checks.
- **Comprobantes on sales:** Factura, Boleta, credit and debit notes, with series and a
  gapless number assigned on submission, and the Factura / Boleta rules enforced.
- **Supplier documents on purchases:** type, series and number, with duplicate checks.
- **Chart of accounts:** the PCGE Modificado 2019 (MEF), applied to a company in one action.
- **IGV:** 18% and 0% tax templates for sales and purchases.
- **Addresses:** the Ubigeo list of all 1,893 districts (INEI), with accents.
- **Point of sale:** each counter sale is a numbered Boleta or Factura; counter returns get
  their credit note reason.
- **SUNAT catalogues** 01, 06, 07, 09 and 10, and a **Peru** icon on the apps screen.

It does not yet include electronic invoicing, SIRE registers or the CONCAR import tools.

## Documentation

| | |
|---|---|
| [docs/FEATURES.md](docs/FEATURES.md) | Everything the app does, in English |
| [docs/FUNCIONALIDADES.md](docs/FUNCIONALIDADES.md) | Todo lo que hace la app, en español |
| [docs/HANDOVER.md](docs/HANDOVER.md) | Design, verification, open decisions and next steps, for developers and the accountant |
| [tools/pcge/README.md](tools/pcge/README.md) | Where the chart of accounts data comes from |
| [tools/ubigeo/README.md](tools/ubigeo/README.md) | Where the Ubigeo list comes from |

## Install

```bash
bench get-app <repository-url>                # on a Frappe / ERPNext v16 bench
bench --site <site> install-app erpnext_peru  # refused on any other version
```

Then follow "First-time setup" in [docs/FEATURES.md](docs/FEATURES.md#first-time-setup).

## Tests

```bash
bench --site <test-site> set-config allow_tests true
bench --site <test-site> run-tests --app erpnext_peru
```

Use a site that holds no real data. Details are in [docs/HANDOVER.md](docs/HANDOVER.md#10-working-on-it).

## Licence

GNU General Public License v3.0, the same as ERPNext. See `license.txt`.
