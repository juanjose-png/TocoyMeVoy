# Justificación de modelos — `core/models.py`

## Modelo `Invoice` (NUEVO)

Persiste en PostgreSQL la misma información de factura que se sube a Google Sheets, permitiendo consultar historial, auditar correcciones y rastrear el estado de cada factura sin depender de la API de Sheets.

### Status (TextChoices)

| Valor | Descripción |
|---|---|
| `PENDING` | La factura fue procesada por Gemini pero el usuario aún no confirmó el valor. No se ha subido nada a Sheets/Drive. |
| `CONFIRMED` | El usuario confirmó (o corrigió) el valor. La info ya fue subida a Google Sheets y el archivo a Drive. |
| `ABANDONED` | El usuario envió una nueva factura antes de confirmar la anterior. Esta factura quedó sin procesar. |
| `ERROR` | Hubo un error al intentar subir la factura confirmada a Google Sheets/Drive. |

### Campos

| Campo | Tipo Django | Para qué sirve |
|---|---|---|
| `employee` | `ForeignKey(Employee, SET_NULL, null)` | Vincula la factura con el empleado que la envió. Es `null` cuando quien envía es el admin o el mantenedor (no tienen registro en `Employee`). Se usa `SET_NULL` en vez de `CASCADE` para no perder facturas históricas si se elimina un empleado. |
| `cellphone` | `CharField(max_length=15)` | Número de celular con prefijo 57 (ej: `"573001234567"`). Desnormalizado del Employee para poder enviar mensajes de WhatsApp sin necesidad de un JOIN, y para cubrir el caso donde `employee` es `null`. |
| `invoice_date` | `CharField(max_length=20, default="")` | Fecha de la factura tal cual la extrae Gemini (formato `DD-MM-AAAA`). Es `CharField` y no `DateField` porque Gemini puede devolver `"ERROR"` si no encuentra la fecha, y no queremos perder ese dato crudo. |
| `business_name` | `CharField(max_length=255, default="")` | Nombre del comercio o establecimiento que emitió la factura. Extraído por Gemini. Puede ser `"ERROR"` si la IA no lo identificó. |
| `nit` | `CharField(max_length=50, default="")` | NIT (Número de Identificación Tributaria) del comercio. Extraído por Gemini. Puede contener guiones (ej: `"860001022-9"`) o ser `"ERROR"`. |
| `invoice_number` | `CharField(max_length=100, default="")` | Número o identificador de la factura (ej: `"F001234"`, `"REC5678"`). Extraído por Gemini y limpiado (se eliminan espacios y guiones). Se llama `invoice_number` y no `invoice_id` para evitar confusión con el PK auto-generado de Django. |
| `original_value` | `DecimalField(12, 2, null)` | Valor monetario **original** que extrajo Gemini de la factura. Se guarda siempre, incluso si el usuario luego corrige el monto. Sirve para auditoría: saber qué dijo la IA vs. qué confirmó el humano. Es `Decimal` (no `Float`) para evitar errores de precisión en dinero. |
| `value` | `DecimalField(12, 2, null)` | Valor monetario **final/confirmado** de la factura. Inicialmente es igual a `original_value`. Si el usuario corrige el monto, este campo se actualiza con el valor corregido. Es el que se sube a Google Sheets. |
| `was_corrected` | `BooleanField(default=False)` | Flag que indica si el usuario corrigió el valor extraído por la IA. Útil para filtrar en admin y analizar qué tan precisa es la extracción de Gemini (si muchas facturas se corrigen, puede indicar un problema con el modelo de IA). |
| `cost_center` | `CharField(max_length=255, default="")` | Centro de costos ingresado por el usuario vía texto en WhatsApp. Es opcional: el usuario puede saltarse este paso enviando una nueva factura. Queda vacío (`""`) si no se proporcionó. |
| `concept` | `TextField(default="")` | Concepto o descripción de la factura ingresado por el usuario. Es `TextField` (sin límite práctico) porque algunos usuarios escriben descripciones largas. También es opcional. |
| `file_path` | `CharField(max_length=500, default="")` | Ruta en disco del archivo temporal (imagen o PDF) que se descargó de WhatsApp. Se usa para subir el archivo a Google Drive después de la confirmación. Una vez subido a Drive, el archivo se elimina de disco. Ejemplo: `"archivos_img/573xxx_20260302_120000.jpg"` o `"archivos_pdf/factura_20260302.pdf"`. |
| `is_pdf` | `BooleanField(default=False)` | Indica si el archivo original enviado por el usuario era un PDF (`True`) o una imagen (`False`). Necesario para saber cómo procesarlo: los PDFs se convierten a imagen antes de pasar a Gemini, y se suben a Drive con mime type diferente. |
| `sheet_row` | `IntegerField(null)` | Número de fila en Google Sheets donde se insertó la factura. Se llena después de la subida exitosa en `confirm_and_upload`. Sirve para que `upload_user_data` sepa en qué fila escribir el centro de costos y concepto. Es `null` hasta que se confirma. |
| `sheet_record_id` | `CharField(max_length=50, null)` | ID autoincremental dentro de la hoja de Sheets (no confundir con el PK de Django). Cada hoja de empleado tiene su propio contador. Se llena junto con `sheet_row`. |
| `status` | `CharField(max_length=20, choices)` | Estado actual de la factura en el ciclo de vida (ver tabla de Status arriba). Controla qué acciones son válidas sobre esta factura. |
| `created_at` | `DateTimeField(auto_now_add)` | Timestamp de creación del registro. Se establece automáticamente al crear la factura (cuando Gemini termina la extracción). No se modifica después. |
| `updated_at` | `DateTimeField(auto_now)` | Timestamp de la última modificación. Se actualiza automáticamente cada vez que se hace `.save()`. Útil para ver cuándo fue la última interacción con esta factura. |

### Meta

- `ordering = ["-created_at"]` — Las facturas más recientes aparecen primero por defecto.
- `verbose_name = "Factura"` — Nombre en español para el admin de Django.

---

## Modelo `InvoiceSession` (MODIFICADO)

### Nuevos estados

| Estado | Valor en DB | Cuándo se usa |
|---|---|---|
| `WAITING_CONFIRMATION` | `"waiting_confirmation"` | Gemini extrajo los datos y se enviaron botones de confirmación al usuario. El sistema espera que el usuario presione "Sí" o "No". |
| `WAITING_CORRECTION` | `"waiting_correction"` | El usuario presionó "No" en los botones. El sistema espera que escriba el valor correcto como número. |

Estos dos estados se insertan entre `PROCESSING` y `WAITING_COST_CENTER` en la máquina de estados:

```
PROCESSING → WAITING_CONFIRMATION → [Sí] → WAITING_COST_CENTER
                                  → [No] → WAITING_CORRECTION → WAITING_COST_CENTER
```

### Nuevo campo

| Campo | Tipo Django | Para qué sirve |
|---|---|---|
| `current_invoice` | `ForeignKey(Invoice, SET_NULL, null)` | Apunta a la factura que está siendo procesada en este momento por esta sesión. Permite acceder rápidamente a la factura activa sin hacer queries por celular + status. Se usa `related_name="+"` porque no necesitamos acceso reverso desde Invoice hacia la sesión. Se vuelve `null` implícitamente cuando la sesión vuelve a `IDLE`. |

### Campos legacy (sin cambios, se mantienen)

| Campo | Por qué se mantiene |
|---|---|
| `last_row` | Backward compatibility. Se sigue escribiendo en paralelo con `Invoice.sheet_row`. Permite rollback seguro al código anterior si hay problemas con el modelo Invoice. Se eliminará en un PR futuro. |
| `last_id` | Misma razón. Duplica `Invoice.sheet_record_id`. |
| `invoice_id` | Misma razón. Duplica `Invoice.invoice_number`. |
| `cost_center` | Misma razón. Duplica `Invoice.cost_center`. |

---

## Modelos sin cambios

### `Employee`
No se modificó. La única interacción nueva es que `Invoice.employee` es un FK hacia este modelo.

### `CustomUser` / `CustomUserManager`
No se modificaron. No tienen relación con el flujo de facturas.
