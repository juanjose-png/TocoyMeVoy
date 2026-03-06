# Justificación de cambios en admin — `core/admin.py`

## `InvoiceAdmin` (NUEVO)

Registra el modelo `Invoice` en Django Admin para visualizar todas las facturas procesadas por el sistema.

### `list_display`

| Columna | Por qué se muestra |
|---|---|
| `id` | PK de Django. Permite identificar rápidamente una factura específica y es el enlace al detalle. |
| `cellphone` | Número del empleado que envió la factura. Permite filtrar visualmente por persona. |
| `business_name` | Comercio de la factura. Es el dato más descriptivo para identificar una factura de un vistazo. |
| `invoice_number` | Número de factura extraído por Gemini. Permite buscar una factura específica si el empleado la reporta. |
| `value` | Valor final confirmado. Es el dato más crítico de la factura (el monto). |
| `was_corrected` | Muestra si el usuario corrigió el valor de la IA. Útil para monitorear la precisión de Gemini: si hay muchos `True`, la extracción de valores no está funcionando bien. |
| `status` | Estado actual (pendiente, confirmada, abandonada, error). Permite ver de un vistazo cuántas facturas están pendientes o con error. |
| `created_at` | Fecha de creación. Permite ordenar cronológicamente y ver la actividad reciente. |

### `list_filter`

| Filtro | Para qué sirve |
|---|---|
| `status` | Filtrar por estado: ver solo las pendientes, solo las confirmadas, solo las abandonadas o solo las que tuvieron error. Caso de uso principal: "¿hay facturas con error que necesiten atención?" |
| `was_corrected` | Filtrar facturas donde el usuario corrigió el valor. Sirve para análisis de calidad del modelo de IA. |
| `is_pdf` | Filtrar por tipo de archivo. Puede revelar si un formato tiene más problemas que otro con la extracción. |
| `created_at` | Filtro por rango de fechas. Permite ver facturas de un período específico. |

### `search_fields`

| Campo buscable | Para qué sirve |
|---|---|
| `cellphone` | Buscar todas las facturas de un empleado por su número. |
| `business_name` | Buscar facturas de un comercio específico (ej: "EXITO", "CARREFOUR"). |
| `nit` | Buscar por NIT del comercio. Útil si se necesita cruzar info tributaria. |
| `invoice_number` | Buscar una factura específica por su número. Caso de uso: el empleado dice "la factura 12345 salió mal". |

### `date_hierarchy = "created_at"`

Agrega navegación por fecha (año → mes → día) en la parte superior del listado. Permite explorar facturas por período sin usar el filtro lateral.

### `ordering = ["-created_at"]`

Las facturas más recientes aparecen primero. Es el orden más natural para monitorear la actividad.

### `readonly_fields` (TODOS los campos)

**Todos** los campos son de solo lectura. Razón: las facturas son registros de auditoría — los datos vienen de Gemini y del usuario vía WhatsApp. Editarlos manualmente desde el admin rompería la integridad con lo que está en Google Sheets. Si hay un error, el flujo correcto es que el empleado envíe la factura de nuevo.

---

## `InvoiceSessionAdmin` (MODIFICADO)

### Cambios en `list_display`

Se agregó `current_invoice` a la lista de columnas visibles.

| Columna nueva | Por qué se agregó |
|---|---|
| `current_invoice` | Muestra qué factura está procesando actualmente esta sesión. Permite ver de un vistazo si una sesión tiene una factura activa o está idle. Aparece como link clickeable al Invoice correspondiente gracias al FK. |

### Cambios en `readonly_fields`

Se agregó `current_invoice` a la lista de campos de solo lectura.

| Campo nuevo | Por qué es readonly |
|---|---|
| `current_invoice` | El FK se gestiona automáticamente por el código (se asigna en `process_invoice`, se limpia cuando vuelve a IDLE). Editarlo manualmente desde el admin podría dejar la sesión apuntando a una factura incorrecta y romper el flujo de conversación del usuario. |

---

## Modelos sin cambios en admin

### `CustomUserAdmin`
No se modificó. Sigue gestionando los usuarios del admin con email como USERNAME_FIELD.

### `EmployeeAdmin`
No se modificó. Sigue siendo editable (`is_active` en el listado) para activar/desactivar empleados.
