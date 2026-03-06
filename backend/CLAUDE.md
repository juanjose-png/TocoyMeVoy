# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WhatsApp Business webhook that receives invoice images/PDFs, extracts structured data via Google Gemini AI, stores results in Google Sheets, uploads files to Google Drive, and guides employees through a multi-step conversation to complete each record.

**Current state**: Django + Celery on branch `master`. Migration from Flask completed.

## Commands

```bash
# Instalar dependencias localmente (Python 3.13 requerido)
uv venv --python 3.13 && uv sync

# Primera vez — setup automatizado (crea .logs/, build, migrate, load_initial_data)
bash run.sh
docker compose exec web python manage.py createsuperuser   # separado por ser interactivo

# O manualmente:
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py load_initial_data   # pobla Employee desde config/cellphones_sheets.json
docker compose exec web python manage.py createsuperuser

# Después de cualquier cambio en código o dependencias
docker compose up --build -d   # no hay live reload — el código está bakeado en la imagen

# Logs (Docker)
docker compose logs -f celery-worker
# Logs (archivos en .logs/ — rotación semanal)
ls .logs/

# Forzar tarea programada manualmente
docker compose exec celery-worker celery -A solenium_project call core.tasks.monthly_write_headers

# Parar containers (sin -v: preserva volúmenes y datos de DB)
docker compose down

# Reset total (borra volúmenes incluyendo postgres_data)
docker compose down -v
```

> **Credenciales de Google**: `config/` no está en `.dockerignore`, así que
> `COPY . /app` las bake en la imagen en el momento del build. Deben estar
> presentes en la máquina antes de correr `docker compose up --build`.

```bash
# Emergency: regenerar cellphones_sheets.json desde Google Sheets
python cellphones.py

# Accesos
# Webhook:      http://localhost:3000/webhook/
# Django Admin: http://localhost:3000/admin/
```

No hay suite de tests ni configuración de linter.

## Architecture

### Django project (`solenium_project/`)

- `settings.py` — usa `django-environ`; lee `.env` una sola vez y expone todas las variables de app como atributos (`settings.TOKEN`, `settings.SHEET_ID`, etc.). Config de Django, PostgreSQL, Celery broker/backend, `CELERY_BEAT_SCHEDULE`
- `celery.py` — app Celery con autodiscover
- `urls.py` — monta `/admin/` y delega el resto a `core.urls`
- `logging_config.py` — `WeeklyRotatingHandler` (rotación semanal); genera `LOGGING` dict. Archivos en `.logs/`: general, `important.log` (WARNING+), `*_tokens.log`

### App principal (`core/`)

| Archivo | Rol |
|---|---|
| `models.py` | `Employee`, `Invoice`, `InvoiceSession`, `CustomUser` (email como USERNAME_FIELD) |
| `views.py` | `WebhookView` — GET (verificación Meta) + POST (routing por tipo de mensaje e interactive buttons) |
| `tasks.py` | Celery tasks: `process_invoice`, `confirm_and_upload`, `upload_invoice_file`, `upload_user_data`, `create_employee_drive_folder` + Beat tasks |
| `signals.py` | `post_save` en `Employee` encola `create_employee_drive_folder`; `post_delete` loguea |
| `admin.py` | `CustomUserAdmin` + `InvoiceAdmin` (read-only) + `EmployeeAdmin` (editable) + `InvoiceSessionAdmin` (read-only) |
| `urls.py` | `/webhook`, `/webhook/`, `/health/` |
| `management/commands/load_initial_data.py` | Migración one-time desde JSON a DB |

### Servicios (`core/services/`)

| Archivo | Contenido clave |
|---|---|
| `extract_info.py` | `GeminiExtractor` (clase): `extract_invoice(image_bytes, model)` → respuesta Gemini. `pdf_pages_to_image()`, `pil_image_to_bytes()`. Lee `settings.GOOGLE_API_KEY` |
| `whatsapp_utils.py` | `WhatsAppClient` (clase): `download_image()`, `download_image_to_disk()`, `download_pdf()`, `send_message()`, `send_invoice_data()`, `send_confirmation_buttons()`. Recibe `token` y `phone_number_id` en `__init__` |
| `google_sheets.py` | 18 funciones para Sheets API. Service account (`config/spreadsheets_credentials.json`) |
| `google_drive.py` | 10 funciones para Drive API. OAuth (`config/oauth_token.json`) |
| `constants.py` | `months_spanish` — compartido entre `google_sheets.py` y `google_drive.py` |
| `employee_service.py` | `get_sheet_name_from_db(cellphone)` → nombre de hoja leyendo `Employee` en DB |

### Estado de una sesión de factura

```
idle → processing_invoice → waiting_confirmation → waiting_cost_center → waiting_concept → idle
                                    │
                                    └→ waiting_correction → waiting_cost_center
```

El estado vive en `InvoiceSession` (PostgreSQL). `current_invoice` (FK a `Invoice`) vincula la sesión con la factura en proceso. Persiste entre reinicios.

### Singletons en el Celery worker

`_extractor`, `_sheets_service`, `_drive_service` y `_whatsapp` se inicializan una vez por proceso worker vía la señal `worker_init` (en `core/tasks.py`). Son `None` en el proceso `web` y en `celery-beat`.

```python
_extractor      = GeminiExtractor()
_sheets_service = get_sheets_service()
_drive_service  = create_google_service("drive", "v3", [...])
_whatsapp       = WhatsAppClient(token=TOKEN, phone_number_id=PHONE_NUMBER_ID)
```

### Archivos de factura → Celery

Las imágenes se guardan en `archivos_img/` vía `download_image_to_disk()`, los PDFs en `archivos_pdf/`. Se pasan paths (strings) a `.delay()`. Ambos son volúmenes Docker compartidos entre `web` y `celery-worker`.

## Key Configuration

Variables de entorno en `.env` (ver `.env.example`). Todas leídas en `settings.py` con `django-environ` y expuestas como `settings.*`:

| Variable | Descripción |
|---|---|
| `DJANGO_SECRET_KEY` | Generar con `python -c "import secrets; print(secrets.token_hex(50))"` |
| `DB_*` | Credenciales PostgreSQL (`DB_HOST=postgres` dentro de Docker) |
| `DB_HOST_PORT` | Puerto del host para postgres (default `5437`) |
| `REDIS_URL` | `redis://redis:6379/0` dentro de Docker |
| `GOOGLE_API_KEY` | Google AI Studio |
| `SHEET_ID` | ID numérico del Google Sheet (del URL) |
| `MAIN_FOLDER_ID` | ID de la carpeta raíz en Google Drive |
| `ADMIN_CELLPHONE` / `MANTAINER_CELLPHONE` | Con prefijo `57...` |
| `VERIFY_TOKEN` | Token elegido por el dev, debe coincidir con la config del webhook en Meta |
| `PHONE_NUMBER_ID` / `TOKEN` | Meta Business Console |
| `LOG_LEVEL` | Nivel de logging (default `INFO`). Leído en `logging_config.py` |
| `CSRF_TRUSTED_ORIGINS` | Orígenes CSRF confiables (ej. `https://cajamenor.solenium.co`). Requerido en producción |

Credenciales de Google en `config/` (no versionadas, bakeadas en imagen al build):

- `config/spreadsheets_credentials.json` — service account para Sheets
- `config/oauth_token.json` — OAuth para Drive
- `config/token_drive_v3.pickle` — cache de token (se genera en el primer run)
