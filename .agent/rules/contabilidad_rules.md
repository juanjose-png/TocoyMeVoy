# Reglas de Contabilidad — Caja Menor

## Regla 1: Integridad de Formato en Google Sheets
Toda actualización de la tabla debe mantener el formato de moneda (patrón `#,##0`) y las fórmulas de la columna **DIFERENCIA**. No se debe sobrescribir celdas con fórmulas; únicamente se escriben en columnas de datos raw (`URL Drive`, `CUFE`, `Check Odoo Doc`, `Check Odoo Pago`).

## Regla 2: Identificador Único
El **Número de Factura** (columna E en hojas normales / columna F en MANTENIMIENTO y TRAB SOCIALES) es el identificador único de cada registro. Toda búsqueda en Drive y en Odoo debe realizarse usando este campo como llave primaria.

## Regla 3: No modificar celdas de color
Las celdas con fondo **verde** (totales/saldos) o **amarillo** (resaltados especiales) y las de fondo **rojo** (separadores de mes) son de solo lectura para este sistema. La lógica debe detectar el color de fondo (`get_cell_background_color`) antes de intentar escribir.

## Regla 4: Preservar columna DIFERENCIA
La columna DIFERENCIA contiene fórmulas de Sheets (ej. `=H-G`). Jamás se debe escribir en esa columna con `values().update()`; se deben saltar explícitamente esas celdas en los rangos de escritura.

## Regla 5: Nuevas columnas — posición fija
Las 4 columnas de trazabilidad se insertan **después de CONCEPTO** en todas las hojas, siguiendo este orden:
1. `URL_DRIVE` — link directo al archivo de factura en Google Drive
2. `CUFE` — Código Único de Factura Electrónica
3. `CHECK_ODOO_DOC` — ✅/❌ indica si el documento fue encontrado en Odoo
4. `CHECK_ODOO_PAGO` — ✅/❌ indica si el pago fue asignado en Odoo
