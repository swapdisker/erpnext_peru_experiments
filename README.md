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

Peruvian localization for [ERPNext](https://github.com/frappe/erpnext), as a separate Frappe app.
Nothing in ERPNext core is modified, so ERPNext can be upgraded independently.

> **Status: prototype, first stage (v0.1.0).** It covers identity documents, comprobante
> fields, voucher numbering and SUNAT catalogues. It does **not** yet contain the PCGE chart of
> accounts, IGV tax templates, electronic invoicing, SIRE registers or the CONCAR import tools.
> Nothing here has been reviewed by an accountant. Read [docs/HANDOVER.md](docs/HANDOVER.md)
> before using it with real data.

*Versión en español más abajo.*

## What it does

| Area | Behaviour |
|---|---|
| Customers and Suppliers | Identity document type (SUNAT catalogue 06) and number. RUC is checked with the modulus-11 check digit, DNI must have 8 digits. The number is copied to Tax ID. The same document cannot be registered twice among Customers, or twice among Suppliers. |
| Company | The Tax ID of a Peruvian company must be a valid RUC. |
| Address | Ubigeo field. District, province and department are filled from it. An address in Peru without Ubigeo gives a warning. |
| Sales Invoice | Comprobante type (01 Factura, 03 Boleta, 07 Nota de crédito, 08 Nota de débito), series, and a correlative number assigned on submission. Credit/debit note reason (catalogues 09 and 10) and reference to the modified voucher. |
| Purchase Invoice | Type, series and number of the supplier's document, validated and protected against duplicates. |
| Catalogues | SUNAT catalogues 01, 06, 09 and 10 as editable masters. |
| Utilities | Amount in Spanish words (`SON: ... CON 00/100 SOLES`). |

### Rules enforced when a Sales Invoice is submitted

Only for companies whose country is **Peru**. Opening invoices are exempt.

- The company must have a valid RUC.
- A **Factura** needs a customer identified with a RUC (or type `0`, non-domiciled, for exports).
- A **Boleta de venta** above **S/ 700.00** needs the customer's identity document.
- A credit or debit note needs a reason and the voucher it modifies. Its series starts with `F`
  when it modifies a Factura and with `B` when it modifies a Boleta.
- The series must be registered and enabled in **SUNAT Voucher Series**.

### Voucher numbering

- Numbers are assigned when the invoice is submitted, never typed by users.
- Each company + type + series has its own counter, locked while a number is allocated.
- A failed submission does not consume a number. A cancelled voucher keeps its number. An
  amended invoice gets a new one. A voucher that has a number cannot be deleted.

## Install

```bash
bench get-app <repository-url>
bench --site <site> install-app erpnext_peru
```

Requires ERPNext v15. Then:

1. Enter the RUC in the **Tax ID** of the company.
2. Turn on **Disable Rounded Total** in Global Defaults: comprobantes are issued to the céntimo.
3. Create the series in **SUNAT Voucher Series** (for example `F001` for type `01`, `B001` for
   `03`). Set **Last Number Issued** to continue an existing numbering.
4. Load the Ubigeo master (see `erpnext_peru/setup/ubigeo.py`): the district list is not shipped yet.

## Tests

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app erpnext_peru
```

The validators have no database dependency and also run alone:

```bash
python -m unittest erpnext_peru.tests.test_identity erpnext_peru.tests.test_voucher \
    erpnext_peru.tests.test_amount_in_words erpnext_peru.tests.test_translations
```

## Licence

GNU General Public License v3.0, the same licence as ERPNext. See `license.txt`.

No code was copied from other localizations. Regulatory data (catalogue codes) comes from
SUNAT's public resolutions; each data file names its source.

---

# ERPNext Perú (español)

Localización peruana para ERPNext, como una app de Frappe independiente.

> **Estado: prototipo, primera etapa (v0.1.0).** Incluye documentos de identidad, campos del
> comprobante, numeración y catálogos de SUNAT. **No** incluye todavía el PCGE, las plantillas
> de IGV, la facturación electrónica, los registros SIRE ni las herramientas de importación
> desde CONCAR. Ningún contador ha revisado esta versión. Lea [docs/HANDOVER.md](docs/HANDOVER.md)
> antes de usarla con datos reales.

## Qué hace

- **Clientes y proveedores:** tipo y número de documento de identidad (catálogo 06). El RUC se
  valida con su dígito verificador (módulo 11) y el DNI debe tener 8 dígitos. No se permite
  registrar dos veces el mismo documento entre clientes, ni dos veces entre proveedores.
- **Compañía:** el Tax ID de una compañía peruana debe ser un RUC válido.
- **Dirección:** campo Ubigeo, con aviso cuando falta.
- **Factura de venta:** tipo de comprobante (01, 03, 07, 08), serie y número correlativo
  asignado al validar. Motivo de la nota (catálogos 09 y 10) y comprobante que modifica.
- **Factura de compra:** tipo, serie y número del comprobante del proveedor, con control de
  duplicados.

## Reglas al validar una venta (solo compañías peruanas)

- La compañía debe tener un RUC válido.
- La **Factura** requiere un cliente con RUC (o tipo `0`, no domiciliado, en exportaciones).
- La **Boleta de venta** por más de **S/ 700.00** requiere el documento de identidad del cliente.
- La nota de crédito o débito requiere el motivo y el comprobante que modifica.
- La serie debe estar registrada y habilitada en **Series de Comprobantes SUNAT**.

## Numeración

El número se asigna al validar y nunca lo escribe el usuario. Si la validación falla, el
número no se consume. Un comprobante anulado conserva su número y no se puede eliminar.

## Configuración inicial

1. Ingrese el RUC en el **Tax ID** de la compañía.
2. Active **Disable Rounded Total** en Global Defaults: los comprobantes se emiten al céntimo.
3. Cree las series en **Series de Comprobantes SUNAT** (por ejemplo `F001` para el tipo `01`).
   Use **Último número emitido** para continuar la numeración de un sistema anterior.
4. Cargue el maestro de Ubigeo (ver `erpnext_peru/setup/ubigeo.py`).
