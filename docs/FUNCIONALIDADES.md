# erpnext_peru — funcionalidades

Versión 0.2.0. *[English version](FEATURES.md).*

Este documento describe lo que hace la app desde el punto de vista del usuario. Es un
prototipo: lea [HANDOVER.md](HANDOVER.md) (en inglés) para saber qué se ha verificado y qué
no, y qué decisiones contables aún debe tomar un contador.

Los nombres de campos y menús aparecen como se ven con la interfaz en español. Algunos nombres
propios de ERPNext se dejan también en inglés entre paréntesis, porque su traducción puede
variar según la versión.

## Contenido

1. [Dónde se aplica](#1-dónde-se-aplica)
2. [El icono y el espacio de trabajo Perú](#2-el-icono-y-el-espacio-de-trabajo-perú)
3. [Documentos de identidad de clientes y proveedores](#3-documentos-de-identidad-de-clientes-y-proveedores)
4. [RUC de la compañía](#4-ruc-de-la-compañía)
5. [Direcciones y Ubigeo](#5-direcciones-y-ubigeo)
6. [Ventas: comprobantes de pago](#6-ventas-comprobantes-de-pago)
7. [Series y numeración](#7-series-y-numeración)
8. [Compras: el comprobante del proveedor](#8-compras-el-comprobante-del-proveedor)
9. [Plan de cuentas: PCGE 2019](#9-plan-de-cuentas-pcge-2019)
10. [IGV](#10-igv)
11. [Catálogos de SUNAT](#11-catálogos-de-sunat)
12. [Monto en letras](#12-monto-en-letras)
13. [Configuración inicial](#configuración-inicial)
14. [Lo que no incluye](#14-lo-que-no-incluye)

## 1. Dónde se aplica

- Las reglas de los comprobantes se aplican solo a las compañías cuyo **país es Perú**. Las
  compañías de otros países en el mismo sitio no se ven afectadas.
- Las **facturas de apertura** ("Is Opening Entry" = Sí) están exentas de esas reglas.
- **Punto de venta.** Cada venta en caja es una factura de venta (lo predeterminado en la
  Configuración POS de ERPNext v16), así que es un comprobante como cualquier otro: recibe tipo,
  serie y número al validarse, y se aplica la regla de los S/ 700. Una devolución hecha en caja
  es una nota de crédito cuyo motivo se llena solo al validarla, según el carrito en ese
  momento: `06` (devolución total) cuando vuelven completos todos los artículos de la venta,
  `07` (devolución por ítem) en otro caso. Un motivo elegido a mano se respeta. Si la
  Configuración POS se cambia a POS Invoices, la factura que ERPNext genera al cerrar el turno
  queda exenta: no recibe tipo ni número.
- Las reglas de documentos de identidad se aplican a todo cliente o proveedor que tenga un
  documento de identidad registrado. Si no lo tiene, no se le exige nada.
- La interfaz está disponible en español y en inglés.

## 2. El icono y el espacio de trabajo Perú

Un icono **Perú** en la pantalla de aplicaciones (la página de inicio), visible solo para los
usuarios del escritorio. Abre el espacio de trabajo; la barra lateral que lo acompaña la arma
Frappe.

Un espacio de trabajo **Perú** con:

- accesos directos a Series de Comprobantes SUNAT, Compañía, Cliente, Proveedor, Factura de
  venta y Factura de compra;
- una tarjeta **Configuración**: compañía, series, plan de cuentas, plantillas de impuestos,
  categorías de impuestos;
- una tarjeta **Documentos**: facturas, clientes, proveedores, direcciones;
- una tarjeta **Catálogos SUNAT**: los cinco catálogos y Ubigeo.

## 3. Documentos de identidad de clientes y proveedores

Dos campos en Cliente y en Proveedor, que también aparecen en la ventana rápida de "nuevo
cliente / proveedor":

| Campo | Contenido |
|---|---|
| Tipo de documento de identidad | Un código del catálogo 06 de SUNAT: `6` RUC, `1` DNI, `4` carnet de extranjería, `7` pasaporte, `0` no domiciliado sin RUC, entre otros |
| Número de documento de identidad | El número, sin espacios |

Al guardar:

- **RUC:** debe tener 11 dígitos, empezar con 10, 15, 16, 17 o 20 y tener el dígito verificador
  correcto (módulo 11). Un dígito mal escrito se detecta.
- **DNI:** debe tener exactamente 8 dígitos. Se conservan los ceros a la izquierda.
- **Carnet de extranjería y pasaporte:** solo letras y dígitos, hasta 12 caracteres.
- **Otros tipos:** hasta 15 caracteres.
- Se eliminan los espacios y las letras pasan a mayúsculas.
- Se rechaza un tipo sin número y un número sin tipo.
- **Duplicados:** el mismo documento no puede registrarse dos veces entre los clientes, ni dos
  veces entre los proveedores. El mensaje enlaza al registro existente. El mismo RUC sí puede
  existir una vez como cliente y otra como proveedor. La base de datos también rechaza los
  duplicados.
- El número se copia al campo **Tax ID** de ERPNext. Si se quita el documento, también se quita
  esa copia, salvo que el Tax ID se haya cambiado por separado.

No se verifica si el contribuyente existe o está activo en SUNAT.

## 4. RUC de la compañía

En una compañía cuyo país es Perú, el campo **Tax ID**, cuando está lleno, debe ser un RUC
válido. Puede quedar vacío mientras se configura la compañía, pero una compañía sin RUC válido
no puede validar facturas de venta.

## 5. Direcciones y Ubigeo

- Las direcciones tienen un campo **Ubigeo** (el código de distrito de seis dígitos).
- Al elegir un Ubigeo se completan la ciudad, la provincia y el departamento si están vacíos.
  Lo que el usuario escribió nunca se sobrescribe.
- Una dirección en Perú guardada sin Ubigeo muestra un aviso y se guarda de todos modos.
- **Incluye los 1 893 distritos** (25 departamentos, 196 provincias), con los códigos del INEI,
  los que usan los comprobantes electrónicos, y sus nombres con tildes. Fuentes: la relación de
  códigos del INEI y su directorio de municipalidades de noviembre de 2026, contrastados con el
  Catálogo 13 de SUNAT. La lista se carga al instalar y en cada actualización.
- En el campo Ubigeo se puede escribir el distrito, la provincia o el departamento, con o sin
  tildes: "jesus maria" encuentra 150113, Jesús María, Lima, Lima.
- Los códigos que el INEI ya no publica se **deshabilitan**, no se borran: las direcciones que
  los usan los conservan y muestran un aviso al guardarse; las nuevas no pueden elegirlos.
- La lista es un dato de referencia. Lo que se edite a mano se deshace en la siguiente
  actualización.

## 6. Ventas: comprobantes de pago

### Campos

Una sección **Comprobante de pago (SUNAT)** en la Factura de venta:

| Campo | Contenido |
|---|---|
| Tipo de comprobante | `01` Factura, `03` Boleta de venta, `07` Nota de crédito, `08` Nota de débito |
| Serie | Cuatro caracteres, por ejemplo `F001` |
| Número | Se asigna al validar; solo lectura |
| Número de comprobante | Serie y número juntos, por ejemplo `F001-00000123`; solo lectura, se puede buscar |
| Tipo / Número de documento de identidad del cliente | Copiados del cliente; solo lectura |
| Motivo de la nota de crédito | Catálogo 09 de SUNAT; aparece en las devoluciones |
| Motivo de la nota de débito | Catálogo 10 de SUNAT; aparece en las notas de débito |
| Tipo / Número del comprobante que modifica | El comprobante al que se refiere la nota |

### Lo que se completa solo

- **Tipo:** si se deja vacío, se asigna Factura cuando el cliente tiene RUC y Boleta en los
  demás casos. Una devolución pasa a ser Nota de crédito y una nota de débito, Nota de débito.
- **Serie:** si se deja vacía, se completa cuando la compañía tiene exactamente una serie
  habilitada para ese tipo. Si hay varias, se debe elegir. Si cambia el tipo de un borrador
  guardado, la serie que quedó del tipo anterior se vuelve a elegir de la misma forma.
- **Comprobante que modifica:** en una nota creada a partir de un comprobante emitido en este
  sistema, el tipo y el número de ese comprobante se completan y no se pueden cambiar a mano.
- **Documento del cliente:** se copia del cliente cada vez que se guarda, hasta la validación.
  Después ya no cambia, aunque se corrija la ficha del cliente.

Se permite una Boleta para un cliente que tiene RUC, con un aviso.

### Reglas al guardar

- El tipo debe ser 01, 03, 07 u 08 y corresponder al documento: una devolución es 07, una nota
  de débito es 08, una venta normal es 01 o 03.
- La serie debe tener cuatro letras o dígitos y empezar con `F` en una Factura y con `B` en una
  Boleta. La serie de una nota empieza con la letra del comprobante que modifica.
- Una nota solo puede modificar una Factura o una Boleta; el campo «Tipo de comprobante que
  modifica» solo ofrece esas dos.

### Reglas al validar

El documento no se valida, y no se usa ningún número, salvo que:

1. la compañía tenga un RUC válido;
2. una vez creadas las plantillas de IGV, el documento tenga al menos una línea de impuesto
   (la de 18%, o una de las de 0% para ventas exoneradas, inafectas o de exportación);
3. en una **Factura**, el cliente esté identificado con RUC (o con el tipo `0`, no
   domiciliado, pensado para exportaciones);
4. en una **Boleta de venta** cuyo total en soles, con IGV, sea **mayor a S/ 700.00**, el
   cliente tenga documento de identidad (con S/ 700.00 exactos se permite sin documento); lo
   mismo vale para una nota de crédito o débito que modifica una Boleta, según el importe de la
   nota;
5. en una **nota de crédito o de débito**, se haya elegido el motivo e indicado el comprobante
   que modifica (su tipo y su número, por ejemplo `F001-00000123`);
6. la serie esté registrada y habilitada en Series de Comprobantes SUNAT.

En un documento en otra moneda, el límite de S/ 700 se mide sobre el importe convertido a
soles. Esto vale también para una compañía que lleva su contabilidad en otra moneda: el total se
convierte con el tipo de cambio de la fecha de contabilización, y la Boleta se rechaza si no hay
un tipo de cambio a PEN registrado en Cambio de Divisas.

### Después de validar

- Los campos del comprobante no se pueden cambiar.
- Un documento anulado conserva su número. Al corregirlo ("Amend") se crea un documento nuevo
  con un número nuevo.
- Un documento que tiene número de comprobante no se puede eliminar. Cuando una compañía ya
  emitió algún comprobante, el botón **Eliminar transacciones** de la compañía se rechaza con
  un mensaje: borraría las facturas y las series con ellas.

La anulación en sí no está restringida: vea la [sección 14](#14-lo-que-no-incluye).

## 7. Series y numeración

En **Series de Comprobantes SUNAT** se registra cada serie que emite una compañía:

| Campo | Contenido |
|---|---|
| Compañía | Una compañía peruana |
| Tipo de comprobante | 01, 03, 07 u 08 |
| Serie | Cuatro caracteres. El mismo código puede usarse en tipos distintos; cada uno lleva su propia numeración |
| Último número emitido | El siguiente comprobante recibe este número más uno |
| Habilitado | Una serie deshabilitada no se puede usar |

- Para continuar la numeración de un sistema anterior, configure **Último número emitido** una
  sola vez.
- No se puede poner por debajo de un número ya emitido, incluidos los comprobantes anulados.
- La compañía, el tipo y la serie no se pueden cambiar después de crear el registro.
- Cada serie se registra una sola vez por compañía y tipo, así que tiene un único contador.
- Una serie ya usada no se puede eliminar; se deshabilita.
- Los números van de 1 a 99,999,999 y se muestran con ocho dígitos.

Cómo se comportan los números:

- Se asignan en el momento de validar; nunca se escriben a mano.
- Son consecutivos por compañía, tipo y serie, también cuando varios usuarios validan a la vez.
- Un documento que no llega a validarse no consume número.

## 8. Compras: el comprobante del proveedor

Una sección **Comprobante de pago (SUNAT)** en la Factura de compra:

| Campo | Contenido |
|---|---|
| Tipo de comprobante | El tipo impreso en el documento del proveedor (catálogo 01 de SUNAT) |
| Serie / Número | Tal como figuran en el documento |
| Número de comprobante | Serie y número juntos; solo lectura, se puede buscar |
| Tipo / Número del comprobante que modifica | Para notas de crédito y de débito |

Estos campos son opcionales por ahora. Cuando se llenan:

- en Facturas, Boletas y sus notas, la serie debe tener cuatro caracteres y el número hasta
  ocho dígitos; `F001` / `123` se guarda como `F001-00000123`;
- los demás tipos de documento (recibos de servicios públicos, etc.) se revisan con menos
  rigor: hasta 20 letras, dígitos o guiones;
- se rechaza un número sin tipo;
- **duplicados:** el mismo documento del mismo proveedor no puede registrarse dos veces en
  una compañía, se escriba como se escriba. Un documento anulado sí puede volver a registrarse;
- una devolución de compra debe ser tipo 07, y un documento tipo 07 debe registrarse como
  devolución;
- una nota de crédito o de débito necesita el comprobante que modifica para poder validarse;
  se completa solo cuando la nota se crea a partir de una factura que lo tiene;
- el campo **Supplier Invoice No** de ERPNext se llena con el número de comprobante si está
  vacío, y lo sigue cuando ese número se corrige o se borra. Un Supplier Invoice No escrito
  aparte se respeta.

## 9. Plan de cuentas: PCGE 2019

La app incluye el catálogo del **Plan Contable General Empresarial Modificado 2019** publicado
por el MEF: 1,764 cuentas de los elementos 1 al 8, hasta cinco dígitos (seis en las cuentas 682
y 683). Los elementos 9 y 0 solo tienen su cuenta raíz, porque el catálogo no los desarrolla.

### Aplicar PCGE 2019

En el formulario de la Compañía, menú **Perú → Aplicar PCGE 2019**. Hace una pregunta, muestra
una vista previa y solo escribe después de que usted confirme.

| Opción | Qué hace |
|---|---|
| Sin marcar (por defecto) | Agrega las cuentas del PCGE que la compañía no tiene. No se elimina, renombra ni cambia nada de lo existente. Si se ejecuta de nuevo, no crea nada. |
| "Eliminar primero el plan de cuentas actual" | Elimina el plan actual de la compañía y luego crea el PCGE. Solo es posible mientras la compañía **no tenga asientos contables**. Úselo en una compañía nueva para reemplazar el plan estándar de ERPNext. |

La vista previa y el informe final muestran:

- cuántas cuentas se crean y cuántas ya existían;
- **diferencias de nombre:** cuentas que la compañía ya tiene con el mismo código y otro
  nombre. Se conserva el nombre de la compañía;
- **conflictos**, en los que no se sobrescribe nada y alguien debe decidir; por ejemplo, una
  cuenta que el PCGE divide en subcuentas pero en la que la compañía ya registra asientos;
- los valores predeterminados de la compañía que se asignaron, se conservaron o quedaron
  vacíos.

Cada cuenta recibe su número, su nombre según el PCGE, su lugar en el árbol y un tipo raíz
(activo, pasivo, patrimonio, ingreso, gasto). El tipo de cuenta se asigna solo donde ERPNext lo
necesita: caja, banco, por cobrar, por pagar, impuesto, costo de ventas, ingreso.

Valores predeterminados que se asignan si están vacíos: por cobrar `1212`, por pagar `4212`,
ingresos `70121` y redondeo `7599` (provisional). Caja, banco, costo de ventas, diferencia de
cambio y cuentas de existencias quedan para el contador.

La aplicación se ejecuta en segundo plano y tarda alrededor de medio minuto; la página espera y luego muestra el resultado. Si falla, no se modifica nada y se muestra el motivo. Requiere un proceso de trabajo en segundo plano (worker), presente en toda instalación estándar. En un sitio se modifica un solo plan de cuentas a la vez: si se está modificando el de otra compañía, la segunda ejecución espera hasta dos minutos y luego se rechaza con un mensaje.

### Las subcuentas propias de la compañía

Para desarrolladores: `erpnext_peru.accounts.pcge.import_client_accounts(company, rows, dry_run=True)`
agrega cuentas como `104101 BCP Soles` bajo la cuenta del PCGE que corresponde. Rechaza las
filas incorrectas indicando el motivo y continúa, informa los conflictos y tiene una ejecución
de prueba. Todavía no tiene pantalla.

## 10. IGV

En el formulario de la Compañía, menú **Perú → Configurar IGV**. La compañía debe tener la
cuenta `40111` (aplique primero el PCGE). Se crean:

| | |
|---|---|
| Categorías de impuestos | IGV - Gravado, IGV - Exonerado, IGV - Inafecto, IGV - Exportación |
| Plantillas de ventas | IGV 18% - Ventas gravadas (la predeterminada); IGV 0% - Ventas exoneradas; IGV 0% - Ventas inafectas; IGV 0% - Exportación |
| Plantillas de compras | IGV 18% - Compras gravadas (la predeterminada); IGV 0% - Compras exoneradas; IGV 0% - Compras inafectas |
| Reglas de impuestos | Al elegir una categoría de impuestos en un documento se selecciona su plantilla |

- El 18% se calcula sobre el total neto y se registra en la `40111`: al haber en las ventas y
  al debe en las compras, de modo que el saldo de la cuenta es el IGV por pagar.
- Las plantillas de 0% no generan asiento. Existen para que el documento indique cómo se trata.
- Cada plantilla de ventas lleva su código del catálogo 07 de SUNAT (10, 20, 30, 40).
- Se deshabilita la plantilla "Peru Tax" de 16% que ERPNext crea por su cuenta. Si ERPNext la
  vuelve a crear (por ejemplo, tras reemplazar el plan de cuentas), al guardar la compañía se
  deshabilita de nuevo.
- Si se ejecuta de nuevo, no crea nada ni deshace cambios locales.
- Si el sitio redondea los medios céntimos al dígito par, se muestra un aviso.

Ejemplo: una venta gravada de S/ 1,000 genera S/ 180 de IGV y un total de S/ 1,180.

No se contempla: documentos que mezclan ítems gravados y exonerados, ni la tasa reducida para
pequeños restaurantes y hoteles.

## 11. Catálogos de SUNAT

Maestros editables, cargados al instalar. Las entradas que usted cambie o deshabilite se
conservan al actualizar.

| Maestro | Catálogo | Entradas |
|---|---|---|
| Tipo de Comprobante SUNAT | 01 | 17 |
| Tipo de Documento de Identidad SUNAT | 06 | 13 |
| Tipo de Afectación del IGV SUNAT | 07 | 18 |
| Motivo de Nota de Crédito SUNAT | 09 | 13 |
| Motivo de Nota de Débito SUNAT | 10 | 3 |
| Ubigeo | Catálogo 13 (códigos del INEI) | 1 893 distritos |

## 12. Monto en letras

Para desarrolladores que preparen un formato de impresión:
`erpnext_peru.utils.amount_in_words.amount_in_words("1234.56", "PEN")` devuelve
`SON: MIL DOSCIENTOS TREINTA Y CUATRO CON 56/100 SOLES`. Admite PEN, USD y EUR.

## Configuración inicial

1. Instale la app en el sitio.
2. En **Valores predeterminados globales** (Global Defaults), active **Disable Rounded Total**:
   los comprobantes se emiten al céntimo y, de lo contrario, ERPNext redondea el total adeudado.
3. Abra la compañía e ingrese su RUC en **Tax ID**.
4. En la compañía, menú **Perú → Aplicar PCGE 2019**. En una compañía nueva, marque "Eliminar
   primero el plan de cuentas actual".
5. En la compañía, menú **Perú → Configurar IGV**.
6. En **Series de Comprobantes SUNAT**, cree las series: por ejemplo `F001` para el tipo 01,
   `B001` para el 03, `FC01` y `BC01` para el 07.
7. Registre a los clientes con su documento de identidad y emita el primer comprobante.

Antes de poder validar facturas de compra, decida cómo se contabilizan las existencias: con el
"inventario perpetuo" de ERPNext activado, toda factura de compra exige cuentas de existencias
que la configuración del PCGE no define. Vea [HANDOVER.md](HANDOVER.md), sección 7.

## 14. Lo que no incluye

- Facturación electrónica: no genera XML, no envía a SUNAT ni a un proveedor, no hay CDR ni QR.
- Restricción para anular un comprobante emitido (comunicación de baja).
- Formato de impresión.
- Registros de ventas y de compras del SIRE.
- Importación desde CONCAR, saldos iniciales, conciliación.
- Asientos de destino (6 → 9 / 79).
- Tipo de cambio diario de SUNAT.
- La lista ampliada de tipos de documento para compras.
- Uso con datos reales: todo se revisó en sitios de prueba con compañías, clientes e importes
  inventados, en ERPNext v16.
