---
name: sheet_enlarger
description: >
  Especialista en extender hojas de Google Sheets con columnas de trazabilidad documental y contable.
  Inserta 4 columnas nuevas (URL Drive, CUFE, Check Odoo Doc, Check Odoo Pago) respetando colores y fórmulas existentes.
---

# Skill: Sheet Enlarger — Inserción de Columnas de Trazabilidad

## Objetivo
Añadir 4 columnas de trazabilidad **después de la columna CONCEPTO** en cada hoja de Caja Menor, sin alterar las celdas con color de fondo (verde/amarillo/rojo) ni las fórmulas existentes.

## Nuevas Columnas (en orden)

| # | Nombre Encabezado | Letra (hojas normales) | Letra (MANTENIMIENTO/TRAB SOCIALES) | Descripción |
|---|---|---|---|---|
| 1 | URL DRIVE | I | J | Hyperlink al archivo de factura en Google Drive |
| 2 | CUFE | J | K | Código Único de Factura Electrónica (20 chars) |
| 3 | CHECK ODOO DOC | K | L | ✅ doc encontrado en Odoo / ❌ no encontrado |
| 4 | CHECK ODOO PAGO | L | M | ✅ pago asignado en Odoo / ❌ no asignado |

> **Nota:** Las columnas existentes DIFERENCIA y OBSERVACIONES se desplazan a la derecha.

## Capacidades

### 1. Inserción de Columnas vía Sheets API
```python
# Usar insertDimension request para insertar columnas sin borrar celdas existentes
requests = [{
    "insertDimension": {
        "range": {
            "sheetId": sheet_id_num,
            "dimension": "COLUMNS",
            "startIndex": 8,   # después de H (CONCEPTO en hojas normales)
            "endIndex": 12     # 4 columnas nuevas
        },
        "inheritFromBefore": False
    }
}]
service_sheet.batchUpdate(spreadsheetId=sheet_id, body={"requests": requests}).execute()
```

### 2. Escritura de Encabezados con Formato
- Color de fondo: azul claro `(173, 216, 230)` para distinguir columnas nuevas
- Texto en negrita, tamaño 10pt, color negro
- Usar `repeatCell` con `fields: "userEnteredFormat(backgroundColor,textFormat)"`

### 3. Búsqueda de Archivos en Drive por Número de Factura
```python
def find_invoice_in_drive(service_drive, folder_id: str, invoice_number: str) -> str | None:
    """
    Busca el archivo de factura en Drive usando el número de factura como nombre parcial.
    Retorna la URL directa (https://drive.google.com/file/d/{id}/view) o None.
    """
    query = (
        f"'{folder_id}' in parents and trashed = false "
        f"and name contains '{invoice_number}'"
    )
    response = service_drive.files().list(
        q=query, spaces='drive', fields='files(id, name)'
    ).execute()
    files = response.get('files', [])
    if files:
        file_id = files[0]['id']
        return f"https://drive.google.com/file/d/{file_id}/view"
    return None
```

### 4. Lógica de Extracción de CUFE
**Método preferido**: Lectura de texto del PDF en Drive vía Google Drive API + expresión regular.
```python
import re
CUFE_PATTERN = re.compile(r'\bCUFE[\s:\-]*([A-Fa-f0-9]{96})\b')

def extract_cufe_from_pdf_text(text: str) -> str | None:
    match = CUFE_PATTERN.search(text)
    return match.group(1) if match else None
```
**Fallback**: Entrada manual asistida vía WhatsApp (nuevo estado `waiting_cufe` en la máquina de estados de `InvoiceSession`).

### 5. Validación contra Odoo (Cruce por Exportación)
Dado que no existe conexión directa XML-RPC a Odoo, la lógica de validación funcionará por cruce de datos:

#### Fase A — Importación de datos de Odoo
1. Exportar desde Odoo → Módulo Contabilidad → Facturas → CSV/Excel con campos:
   - `Número de Factura`, `Estado`, `Pago Asignado`
2. Subir el CSV a una hoja auxiliar oculta en el mismo Google Sheet (`_ODOO_IMPORT`)
3. El sistema lee esa hoja y construye un diccionario de búsqueda en memoria.

#### Fase B — Función de Validación
```python
def check_odoo_status(invoice_number: str, odoo_data: dict) -> tuple[str, str]:
    """
    Retorna (check_doc, check_pago) como '✅' o '❌'
    """
    entry = odoo_data.get(invoice_number)
    if not entry:
        return "❌", "❌"
    check_doc = "✅" if entry.get("estado") in ["publicado", "posted"] else "❌"
    check_pago = "✅" if entry.get("pago_asignado") == "true" else "❌"
    return check_doc, check_pago
```

## Flujo de Ejecución (Task Celery)

```
trigger_traceability_update(sheet_id, sheet_name)
    ├─ load_odoo_data_from_aux_sheet()       → dict {invoice_no: {estado, pago}}
    ├─ get_all_invoice_rows(sheet_name)      → list of (row_num, invoice_no, folder_id)
    └─ for each row:
        ├─ find_invoice_in_drive()           → url_drive
        ├─ extract_cufe_from_pdf_text()      → cufe  (o "" si no encontrado)
        ├─ check_odoo_status()              → (check_doc, check_pago)
        └─ write_traceability_row()          → escribe I, J, K, L en la fila
```

## Restricciones
- **No escribir** en filas con fondo rojo (separadores de mes).
- **No escribir** en filas donde la columna E (número de factura) esté vacía.
- Todas las escrituras deben ser atómicas por fila para evitar datos parciales.
- Respetar rate limits de Sheets API: máx. 60 requests/min por usuario; usar `time.sleep(1)` entre filas si el batch supera 50 filas.
