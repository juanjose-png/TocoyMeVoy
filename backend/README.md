# Automatización de Caja Menor — WhatsApp + Django + Celery + Gemini

Sistema webhook que recibe facturas (imagen o PDF) vía **WhatsApp Business**, extrae datos estructurados con **Google Gemini AI**, los registra en **Google Sheets**, sube el archivo a **Google Drive** y guía al empleado por un flujo conversacional de varios pasos.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Runtime | Python 3.13, Django 5.2 |
| Async / Colas | Celery 5.4 + Redis 7 |
| IA | Google Gemini 2.0 Flash (`google-genai`) |
| Base de datos | PostgreSQL 16 |
| Google Cloud | Sheets API v4, Drive API v3 |
| WhatsApp | Meta Business Cloud API |
| Servidor | Gunicorn + WhiteNoise |
| Deploy | Docker Compose (5 servicios) |
| Gestor de paquetes | uv + pyproject.toml |
| Variables de entorno | django-environ |

---

## Arquitectura

```
                       ┌──────────────────────────────────┐
  WhatsApp Business    │   web  (Django / Gunicorn :3000)  │
  ─────────────────>   │   WebhookView  GET│POST           │
                       │   Valida Employee en PostgreSQL   │
                       └──────────────┬───────────────────┘
                                      │ .delay()
                                      ▼
                               ┌─────────────┐
                               │    Redis 7   │  ← broker + backend
                               └──────┬──────┘
                         ┌────────────┼────────────┐
                         ▼            ▼             ▼
                   ┌──────────┐  ┌─────────┐  ┌──────────┐
                   │  celery  │  │  celery │  │  celery  │
                   │  worker  │  │  worker │  │  worker  │
                   │  (×4)    │  │  (×4)   │  │  (×4)    │
                   └────┬─────┘  └────┬────┘  └────┬─────┘
                        │             │              │
              ┌─────────▼─────────────▼──────────────▼──────────┐
              │              Google Cloud                         │
              │   ┌──────────────┐  ┌───────────┐  ┌──────────┐ │
              │   │  Gemini 2.0  │  │  Sheets   │  │  Drive   │ │
              │   │  (extracción)│  │  (datos)  │  │(archivos)│ │
              │   └──────────────┘  └───────────┘  └──────────┘ │
              └────────────────────────────────────────────────────┘
                        │
              ┌─────────▼──────────┐
              │  WhatsApp API      │  ← confirmaciones al usuario
              └────────────────────┘

  celery-beat ──> tareas programadas (1er día del mes)
  PostgreSQL  ──> Employee + Invoice + InvoiceSession + CustomUser (estado persistente)
```

---

## Estructura del proyecto

```
automatizacion-caja-menor/
├── solenium_project/              # Paquete de configuración Django
│   ├── settings.py                # django-environ: lee .env, expone vars; DB, Celery, Beat
│   ├── celery.py                  # Inicialización de la app Celery
│   ├── urls.py                    # /admin/ + include(core.urls)
│   └── logging_config.py          # WeeklyRotatingHandler + LOGGING dict → .logs/
│
├── core/                          # App principal
│   ├── models.py                  # Employee + Invoice + InvoiceSession + CustomUser
│   ├── views.py                   # WebhookView — GET (verificación) + POST (routing + interactive buttons)
│   ├── tasks.py                   # 8 Celery tasks + 4 singletons por worker
│   ├── signals.py                 # post_save Employee → encola create_employee_drive_folder
│   ├── admin.py                   # CustomUserAdmin + InvoiceAdmin + EmployeeAdmin + InvoiceSessionAdmin
│   ├── urls.py                    # /webhook, /webhook/, /health/
│   ├── apps.py                    # CoreConfig — registra signals en ready()
│   ├── services/
│   │   ├── extract_info.py        # GeminiExtractor + Invoice (Pydantic) + helpers PDF/PIL
│   │   ├── google_sheets.py       # 18 funciones para Google Sheets API
│   │   ├── google_drive.py        # 10 funciones para Google Drive API
│   │   ├── constants.py           # Constantes compartidas (months_spanish)
│   │   ├── whatsapp_utils.py      # WhatsAppClient — descarga media + envío + botones confirmación
│   │   └── employee_service.py    # get_sheet_name_from_db(cellphone)
│   └── management/commands/
│       └── load_initial_data.py   # Migración one-time: JSON → PostgreSQL
│
├── config/                        # Credenciales Google (no versionadas, bakeadas en imagen)
│   ├── spreadsheets_credentials.json  # Service account — Sheets
│   ├── oauth_token.json               # OAuth — Drive
│   ├── token_drive_v3.pickle          # Cache de token (se genera en el primer run)
│   └── cellphones_sheets.json         # Mapeo {celular: hoja} — generado por cellphones.py
│
├── .logs/                         # Logs con rotación semanal (bind mount en Docker)
├── docker-compose.yml
├── Dockerfile                     # Multi-stage: UV builder + debian:trixie-slim
├── pyproject.toml                 # Dependencias gestionadas con uv
├── run.sh                         # Setup automatizado: crea .logs/, build, migrate, load_initial_data
├── manage.py
└── cellphones.py                  # Script de emergencia: regenera cellphones_sheets.json
```

---

## Flujo de una factura

```
 1.  Usuario envía IMAGEN o PDF por WhatsApp
           │
 2.  WebhookView.post()
     ├── Extrae from_number del payload Meta
     ├── Valida que sea Employee activo (PostgreSQL) o admin/mantenedor
     └── Enruta por tipo de mensaje
           │
 3.  Descarga a disco
     ├── IMAGEN → download_image_to_disk() → archivos_img/
     └── PDF    → download_pdf()           → archivos_pdf/
           │
 4.  InvoiceSession.state = PROCESSING
     process_invoice.delay(path) → Redis
           │
 5.  Celery Worker — process_invoice()
     ├── Lee imagen de disco / convierte PDF→imagen (pdf2image + Pillow)
     ├── GeminiExtractor.extract_invoice(image_bytes, "gemini-2.0-flash")
     │     └── Retorna JSON: {invoice_date, business_name, nit, invoice_id, invoice_value}
     ├── Crea Invoice(status=PENDING) en PostgreSQL
     ├── send_invoice_data() → resumen al usuario
     ├── send_confirmation_buttons() → botones "Sí / No"
     └── InvoiceSession.state = WAITING_CONFIRMATION
           │
 6a. Botón "Sí" → confirm_and_upload.delay()
     InvoiceSession.state = WAITING_COST_CENTER
           │
 6b. Botón "No" → InvoiceSession.state = WAITING_CORRECTION
     Usuario escribe valor correcto → Invoice.was_corrected = True
     confirm_and_upload.delay() → WAITING_COST_CENTER
           │
 7.  Celery Worker — confirm_and_upload()
     ├── upload_invoice_to_google_sheets() → obtiene last_row, last_id
     ├── Invoice.status = CONFIRMED
     └── upload_invoice_file.delay() → sube imagen/PDF a Drive (en paralelo)
           │
 8.  Usuario responde: "Centro de costos"
     WebhookView._handle_text() → guarda cost_center
     InvoiceSession.state = WAITING_CONCEPT
           │
 9.  Usuario responde: "Concepto de la factura"
     upload_user_data.delay() → Redis
     InvoiceSession.state = IDLE
           │
10.  Celery Worker — upload_user_data()
     ├── upload_user_data_to_google_sheets() → completa la fila
     └── _whatsapp.send_message("Proceso completado ✅")
```

---

## Modelos

### `Employee`
Representa un empleado autorizado para usar el bot.

| Campo | Tipo | Descripción |
|---|---|---|
| `cellphone` | CharField(10) | Número sin prefijo 57, unique |
| `sheet_name` | CharField(100) | Nombre de la hoja en Google Sheets |
| `is_active` | BooleanField | Controla el acceso al webhook |
| `created_at` / `updated_at` | DateTimeField | Auditoría automática |

Al crear un `Employee`, la señal `post_save` encola automáticamente `create_employee_drive_folder` para crear su carpeta en Drive.

### `Invoice`
Registra cada factura procesada por el sistema. Creada por `process_invoice`, confirmada por `confirm_and_upload`.

| Campo | Tipo | Descripción |
|---|---|---|
| `employee` | FK → Employee | Empleado asociado (nullable) |
| `cellphone` | CharField(15) | Con prefijo 57 |
| `invoice_date` | DateField | Fecha extraída por Gemini (parseada de `DD-MM-AAAA`) |
| `business_name` | CharField(255) | Nombre del comercio |
| `nit` | CharField(50) | NIT del comercio |
| `invoice_number` | CharField(100) | Número de factura |
| `original_value` | DecimalField | Valor original extraído por IA |
| `value` | DecimalField | Valor final (puede diferir si fue corregido) |
| `was_corrected` | BooleanField | `True` si el usuario corrigió el valor |
| `cost_center` | CharField(255) | Centro de costos |
| `concept` | TextField | Concepto de la factura |
| `file_path` | CharField(500) | Ruta al archivo temporal (imagen/PDF) |
| `is_pdf` | BooleanField | Indica si es PDF |
| `sheet_row` | IntegerField | Fila en Google Sheets |
| `sheet_record_id` | CharField(50) | ID de fila en Sheets |
| `status` | CharField(20) | `pending` / `confirmed` / `abandoned` / `error` |
| `created_at` / `updated_at` | DateTimeField | Auditoría automática |

### `InvoiceSession`
Guarda el estado de cada conversación en curso.

| Campo | Tipo | Descripción |
|---|---|---|
| `cellphone` | CharField(15) | Con prefijo 57, unique |
| `state` | CharField | 6 estados (ver diagrama abajo) |
| `current_invoice` | FK → Invoice | Factura en proceso (nullable) |
| `last_row` | IntegerField | _(legacy)_ Fila de la factura en Sheets |
| `last_id` | CharField | _(legacy)_ ID de fila para indexado en Drive |
| `invoice_id` | CharField | _(legacy)_ Número de factura extraído por Gemini |
| `cost_center` | TextField | _(legacy)_ Centro de costos respondido por el usuario |
| `created_at` / `updated_at` | DateTimeField | Auditoría automática |

**Máquina de estados (6 estados):**
```
idle → processing_invoice → waiting_confirmation → waiting_cost_center → waiting_concept → idle
                                    │
                                    └→ waiting_correction → waiting_cost_center
```

### `CustomUser`
Usuario de Django Admin con email como identificador.

| Campo | Tipo | Descripción |
|---|---|---|
| `email` | EmailField | Identificador único (USERNAME_FIELD) |
| `is_staff` | BooleanField | Acceso al admin |
| `is_active` | BooleanField | Cuenta activa |
| `date_joined` | DateTimeField | Fecha de registro |

---

## Tareas Celery

### Tasks bajo demanda

| Task | Reintentos | Qué hace |
|---|---|---|
| `process_invoice` | 2 (delay 10s) | Extrae con Gemini, crea Invoice, envía botones de confirmación |
| `confirm_and_upload` | 2 (delay 10s) | Sube factura confirmada a Sheets, encadena Drive |
| `upload_invoice_file` | — | Sube imagen o PDF a la carpeta de Drive del empleado |
| `upload_user_data` | — | Escribe centro de costos + concepto en Sheets |
| `create_employee_drive_folder` | — | Crea carpeta en Drive para un empleado recién creado |

### Tasks programadas (Celery Beat)

| Task | Horario | Qué hace |
|---|---|---|
| `monthly_write_headers` | 1er del mes 00:00 | Escribe encabezados mensuales en hojas de empleados activos |
| `monthly_create_folders` | 1er del mes 00:10 | Crea carpetas de mes en Drive para todos los empleados |

### Singletons por worker

Los clientes de API se inicializan una sola vez por proceso worker (señal `worker_init`). Son `None` en el proceso `web` y en `celery-beat`.

```python
_extractor      # GeminiExtractor()
_sheets_service # get_sheets_service()
_drive_service  # create_google_service("drive", "v3", [...])
_whatsapp       # WhatsAppClient(token, phone_number_id)
```

---

## Servicios (`core/services/`)

### `extract_info.py`
- **`GeminiExtractor`** — clase que encapsula el cliente Gemini:
  - `extract_invoice(image_bytes, model)` — llama a Gemini; retorna respuesta con JSON estructurado. Reintenta automáticamente ante errores de cuota (`RESOURCE_EXHAUSTED`) o disponibilidad (`503`)
- **`pdf_pages_to_image(pdf_path)`** — convierte páginas de PDF a imagen PIL apilada verticalmente (requiere `poppler-utils`)
- **`pil_image_to_bytes(image)`** — convierte PIL Image a bytes JPEG
- Modelo Pydantic `Invoice`: `invoice_date`, `bussiness_name`, `nit`, `invoice_id`, `invoice_value`

### `google_sheets.py`
- **18 funciones** para Google Sheets API: `get_sheets_service()`, `read_data()`, `write_data()`, `clear_data()`, `find_last_filled_row()`, `get_id_row()`, `get_visible_sheets_names()`, `insert_values_in_sheet()`, `insert_user_data_in_sheet()`, `insert_invoice_data()`, `set_number_format()`, `fill_cells_color()`, `get_cell_background_color()`, `update_cellphones_sheets_json()`, `get_sheet_name_from_cellphone()`, `upload_invoice_to_google_sheets()`, `upload_user_data_to_google_sheets()`, `write_monthly_headers()`
- Autenticación: service account (`spreadsheets_credentials.json`)

### `google_drive.py`
- **10 funciones** para Google Drive API: `create_google_service()`, `upload_image_to_drive()`, `upload_pdf_to_drive()`, `create_folder_in_drive()`, `get_subfolder_id()`, `get_quantity_folders_in_folder_id()`, `get_quantity_files_in_folder_id()`, `upload_invoice_in_folder()`, `create_monthly_folders()`, `create_employee_folder()`
- Autenticación: OAuth (`oauth_token.json`)

### `constants.py`
- `months_spanish` — diccionario de mapeo de meses inglés → español, compartido por `google_sheets.py` y `google_drive.py`

### `whatsapp_utils.py`
- **`WhatsAppClient`** — clase con `_API_BASE = "https://graph.facebook.com/v22.0"`:
  - `download_image(media_id)` → bytes
  - `download_image_to_disk(media_id, cellphone)` → guarda en `archivos_img/`, retorna path
  - `download_pdf(media_id, filename)` → guarda en `archivos_pdf/`, retorna path
  - `send_message(cellphone, message)` → POST a Meta API (agrega prefijo 57 si falta)
  - `send_invoice_data(cellphone, invoice_data)` → mensaje formateado con datos de factura
  - `send_confirmation_buttons(cellphone, invoice_value)` → botones interactivos "Sí / No" para confirmar valor

### `employee_service.py`
- **`get_sheet_name_from_db(cellphone)`** — resuelve número de celular → nombre de hoja consultando `Employee` en PostgreSQL. Acepta número con o sin prefijo `57`. Retorna `"DESCONOCIDOS"` si no se encuentra.

---

## Servicios Docker

| Servicio | Imagen | Puerto | Descripción |
|---|---|---|---|
| `postgres` | postgres:16-alpine | `${DB_HOST_PORT:-5437}`→5432 | Base de datos principal |
| `redis` | redis:7-alpine | `${REDIS_HOST_PORT:-6379}`→6379 | Broker + backend Celery |
| `web` | (build) | 3000 | Django + Gunicorn (2 workers) |
| `celery-worker` | (build) | — | Worker Celery (4 concurrencias) |
| `celery-beat` | (build) | — | Scheduler de tareas programadas |

**Volúmenes:**
- `postgres_data` — persistencia de BD
- `static_files` — archivos estáticos Django
- `archivos_pdf` — compartido entre `web` y `celery-worker`
- `archivos_img` — compartido entre `web` y `celery-worker`
- `.logs` — bind mount compartido entre `web`, `celery-worker` y `celery-beat`

> **Credenciales de Google:** `config/` no está en `.dockerignore`, así que `COPY . /app` las bake en la imagen al momento del build. Deben estar presentes **antes** de `docker compose up --build`.

---

## Setup

### Primera vez

```bash
# 1. Tener config/ con credenciales y .env completo
cp .env.example .env   # editar con tus valores

# 2. Setup automatizado (crea .logs/, build, migrate, load_initial_data)
bash run.sh
docker compose exec web python manage.py createsuperuser   # separado por ser interactivo
```

<details>
<summary>Alternativa manual (sin run.sh)</summary>

```bash
mkdir -p .logs
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py load_initial_data   # JSON → PostgreSQL
docker compose exec web python manage.py createsuperuser
```
</details>

### Desarrollo local (sin Docker)

```bash
uv venv --python 3.13 && uv sync
# Requiere PostgreSQL y Redis corriendo localmente (ajustar DB_HOST en .env)
python manage.py migrate && python manage.py runserver
```

### Comandos de operación

```bash
# Logs en tiempo real
docker compose logs -f celery-worker

# Forzar tarea programada manualmente
docker compose exec celery-worker celery -A solenium_project call core.tasks.monthly_write_headers

# Detener (preserva datos)
docker compose down

# Reset total — borra volúmenes incluyendo postgres_data
docker compose down -v

# Emergencia: regenerar cellphones_sheets.json desde Sheets
python cellphones.py
```

---

## Variables de entorno

Copiar `.env.example` como `.env` y completar. Todas son leídas por `django-environ` en `settings.py` y expuestas al resto del proyecto vía `django.conf.settings`.

| Variable | Descripción |
|---|---|
| `DEBUG` | `False` en producción |
| `DJANGO_SECRET_KEY` | Generar: `python -c "import secrets; print(secrets.token_hex(50))"` |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | Credenciales PostgreSQL |
| `DB_HOST` | `postgres` dentro de Docker, `localhost` en local |
| `DB_PORT` | `5432` |
| `DB_HOST_PORT` | Puerto mapeado al host (default `5437`, evita colisión con postgres local) |
| `REDIS_URL` | `redis://redis:6379/0` dentro de Docker |
| `REDIS_HOST_PORT` | Puerto Redis mapeado al host (default `6379`) |
| `GOOGLE_API_KEY` | API Key de Google AI Studio (Gemini) |
| `SHEET_ID` | ID numérico del Google Sheet (del URL) |
| `MAIN_FOLDER_ID` | ID de la carpeta raíz en Google Drive |
| `ADMIN_CELLPHONE` | Número del admin con prefijo `57...` |
| `MANTAINER_CELLPHONE` | Número del mantenedor con prefijo `57...` |
| `VERIFY_TOKEN` | Token elegido por el dev, debe coincidir con la config del webhook en Meta |
| `PHONE_NUMBER_ID` | ID del número de teléfono en Meta Business Console |
| `TOKEN` | Token de acceso permanente de Meta |
| `LOG_LEVEL` | Nivel de logging: `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |
| `CSRF_TRUSTED_ORIGINS` | Orígenes confiables para CSRF (ej. `https://cajamenor.solenium.co`). Requerido en producción |

**Credenciales Google** en `config/` (no se versionan):

| Archivo | Propósito |
|---|---|
| `config/spreadsheets_credentials.json` | Service account para Sheets |
| `config/oauth_token.json` | OAuth para Drive |
| `config/token_drive_v3.pickle` | Cache de token (se genera en el primer run) |

---

## Django Admin

Disponible en `http://localhost:3000/admin/` tras crear superusuario.

- **CustomUserAdmin** — gestión de usuarios del admin con email como identificador.
- **InvoiceAdmin** — read-only, filtros por estado/fecha/`was_corrected`. Monitoreo de facturas procesadas.
- **EmployeeAdmin** — CRUD de empleados. Al crear un empleado se encola automáticamente la creación de su carpeta en Drive.
- **InvoiceSessionAdmin** — monitoreo read-only de sesiones activas (útil para depurar estados bloqueados).

---

## Django vs Flask legacy

La versión original usaba Flask con estado en memoria. La arquitectura actual resuelve sus limitaciones:

| Aspecto | Flask legacy | Django + Celery |
|---|---|---|
| Estado de sesión | `dict` en memoria (perdido al reiniciar) | `InvoiceSession` en PostgreSQL |
| Procesamiento async | `Queue + Threads` | Celery + Redis (reintentos, persistencia) |
| Tareas programadas | APScheduler | Celery Beat |
| Reintentos automáticos | Manual | `max_retries` + `self.retry()` |
| Gestión de empleados | JSON estático | `Employee` en BD + Django Admin |
| Observabilidad | Logs en archivo | Django Admin + `WeeklyRotatingHandler` (rotación semanal en `.logs/`) |
| Variables de entorno | `python-dotenv` disperso en varios archivos | `django-environ` centralizado en `settings.py` |
| Resiliencia ante reinicios | ❌ | ✅ |
