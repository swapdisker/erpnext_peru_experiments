# ERPNext Peru

Peruvian localization for [ERPNext](https://github.com/frappe/erpnext) v16 (Frappe and
ERPNext 16, Python 3.14), as a separate Frappe app. Nothing in ERPNext core is modified.

**Status: early development, v0.2.0.** It runs on Frappe / ERPNext v16 and has 330 automated
tests; its main screens have been checked on a test site. It has not yet been reviewed by an
accountant or used by a company in production, and it sends nothing to SUNAT: electronic
invoicing is still to be built. Try it on a test site first, and have an accountant confirm
its rules before relying on it. Licensed under GPL-3.0, without warranty.

**Estado: en desarrollo inicial, v0.2.0.** Funciona en Frappe / ERPNext v16 y tiene 330 pruebas
automáticas; sus pantallas principales se revisaron en un sitio de prueba. Aún no lo ha revisado
un contador ni lo usa una empresa en producción, y no envía nada a SUNAT: la facturación
electrónica está pendiente. Pruébelo primero en un sitio de prueba y pida a un contador que
confirme sus reglas antes de depender de él.

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
| [docs/ODOO_REFERENCE.md](docs/ODOO_REFERENCE.md) | How Odoo implements Peru, compared with this app, and what to take from it |
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
