import logging
import os
from datetime import datetime

from celery import shared_task
from celery.signals import worker_init
from django.conf import settings

logger = logging.getLogger(__name__)
tokens_logger = logging.getLogger("tokens")

MODEL_STR = "gemini-2.0-flash"
SHEET_ID = settings.SHEET_ID
MAIN_FOLDER_ID = settings.MAIN_FOLDER_ID
TOKEN = settings.TOKEN
PHONE_NUMBER_ID = settings.PHONE_NUMBER_ID

# Singletons de servicios — se inicializan una vez por proceso worker
# vía la señal worker_init. Son None en el proceso web y en celery-beat.
_extractor = None
_sheets_service = None
_drive_service = None
_whatsapp = None


@worker_init.connect
def init_worker_services(**kwargs):
    """Inicializa los clientes de API una sola vez al arrancar el worker."""
    global _extractor, _sheets_service, _drive_service, _whatsapp

    from core.services.extract_info import GeminiExtractor
    from core.services.google_drive import create_google_service
    from core.services.google_sheets import get_sheets_service
    from core.services.whatsapp_utils import WhatsAppClient

    _extractor = GeminiExtractor()
    _sheets_service = get_sheets_service()
    _drive_service = create_google_service(
        "drive", "v3", ["https://www.googleapis.com/auth/drive"]
    )
    _whatsapp = WhatsAppClient(
        token=TOKEN,
        phone_number_id=PHONE_NUMBER_ID,
    )
    logger.info("Servicios de worker inicializados (Gemini, Sheets, Drive, WhatsApp).")


def _parse_invoice_date(raw: str):
    """Convierte 'DD-MM-AAAA' a date. Retorna None si es 'ERROR' o inválido."""
    if not raw or raw == "ERROR":
        return None
    try:
        return datetime.strptime(raw, "%d-%m-%Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Tasks de procesamiento de facturas
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def process_invoice(self, cellphone, image_path=None, pdf_path=None, is_pdf=False):
    """Extrae datos de la factura con Gemini y crea registro Invoice.

    Ya NO sube a Google Sheets ni Drive — eso ocurre en confirm_and_upload
    tras la confirmación del usuario.
    """
    import json
    from decimal import Decimal

    from core.services.extract_info import pdf_pages_to_image, pil_image_to_bytes

    from core.models import Employee, Invoice, InvoiceSession

    def _strip_prefix(number: str) -> str:
        if number.startswith("57") and len(number) == 12:
            return number[2:]
        return number

    try:
        # --- Obtener bytes de imagen ---
        if is_pdf:
            pil_img = pdf_pages_to_image(pdf_path)
            if pil_img is None:
                if pdf_path and os.path.exists(pdf_path):
                    os.remove(pdf_path)
                _whatsapp.send_message(
                    cellphone,
                    "No se pudo procesar la factura, revisa la extensión del archivo.",
                )
                InvoiceSession.objects.filter(cellphone=cellphone).update(state="idle")
                return
            image_bytes = pil_image_to_bytes(pil_img)
        else:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

        # --- Llamada a Gemini ---
        response = _extractor.extract_invoice(image_bytes, MODEL_STR)

        if not response or not hasattr(response, "text"):
            _whatsapp.send_message(
                cellphone,
                "La IA no pudo extraer la información. "
                "Verifique la imagen o PDF de factura. "
                "Si en el otro intento no funciona, reporte el problema. 🤖",
            )
            InvoiceSession.objects.filter(cellphone=cellphone).update(state="idle")
            return

        if response.text is None:
            _whatsapp.send_message(
                cellphone,
                "Según la IA, la imagen no contiene información válida (None). 🤖",
            )
            InvoiceSession.objects.filter(cellphone=cellphone).update(state="idle")
            return

        # --- Parsear datos de la factura ---
        invoice_data = list(json.loads(response.text).values())

        # Limpiar invoice_id (posición -2): eliminar espacios y guiones
        if invoice_data[-2] and invoice_data[-2] != "ERROR":
            invoice_data[-2] = str(invoice_data[-2]).replace(" ", "").replace("-", "")

        if invoice_data[-1] == "ERROR":
            invoice_data[-1] = 0.00

        # Registrar consumo de tokens
        tokens = int(response.usage_metadata.total_token_count)
        if tokens > 0:
            tokens_logger.info("Tokens usados: %d para el numero %s", tokens, cellphone)
        else:
            tokens_logger.warning("Error al procesar la imagen para el numero %s", cellphone)

        # --- Crear registro Invoice en DB ---
        parsed_value = Decimal(str(invoice_data[-1]))
        employee = Employee.objects.filter(
            cellphone=_strip_prefix(cellphone), is_active=True
        ).first()

        invoice = Invoice.objects.create(
            cellphone=cellphone,
            employee=employee,
            invoice_date=_parse_invoice_date(str(invoice_data[0])),
            business_name=str(invoice_data[1]),
            nit=str(invoice_data[2]),
            invoice_number=str(invoice_data[3]),
            original_value=parsed_value,
            value=parsed_value,
            file_path=pdf_path if is_pdf else image_path,
            is_pdf=is_pdf,
            status=Invoice.Status.PENDING,
        )

        # Enviar resumen de factura + botones de confirmación
        _whatsapp.send_invoice_data(cellphone, invoice_data)
        _whatsapp.send_confirmation_buttons(cellphone, invoice_data[-1])

        # --- Actualizar sesión ---
        InvoiceSession.objects.filter(cellphone=cellphone).update(
            state="waiting_confirmation",
            current_invoice=invoice,
            invoice_id=str(invoice_data[3]) if invoice_data[3] else None,
        )

        logger.info("Factura extraída para %s — esperando confirmación.", cellphone)

    except Exception as exc:
        logger.error("Error procesando factura para %s: %s", cellphone, exc)
        InvoiceSession.objects.filter(cellphone=cellphone).update(state="idle")
        _whatsapp.send_message(
            cellphone,
            "Hubo un error al procesar la factura. Por favor, inténtalo de nuevo más tarde.",
        )
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def confirm_and_upload(self, cellphone, invoice_pk):
    """Sube la factura confirmada a Google Sheets y encadena subida a Drive."""
    from core.services.google_sheets import upload_invoice_to_google_sheets

    from core.models import Invoice, InvoiceSession

    try:
        invoice = Invoice.objects.get(pk=invoice_pk)

        invoice_data = [
            invoice.invoice_date.strftime("%d-%m-%Y") if invoice.invoice_date else "ERROR",
            invoice.business_name,
            invoice.nit,
            invoice.invoice_number,
            float(invoice.value),
        ]

        # --- Subir a Google Sheets ---
        last_row, last_id = upload_invoice_to_google_sheets(
            _sheets_service, SHEET_ID, invoice_data, cellphone
        )

        # --- Actualizar Invoice ---
        invoice.sheet_row = last_row
        invoice.sheet_record_id = str(last_id) if last_id is not None else None
        invoice.status = Invoice.Status.CONFIRMED
        invoice.save()

        _whatsapp.send_message(
            cellphone,
            "La información de la factura ha sido subida exitosamente a Google Sheets. ☀️\n\n"
            "Ahora *escribe la información de centro de costos* en el siguiente mensaje.",
        )

        # --- Actualizar sesión (legacy fields) ---
        InvoiceSession.objects.filter(cellphone=cellphone).update(
            last_row=last_row,
            last_id=str(last_id) if last_id is not None else None,
        )

        # --- Encadenar subida a Drive ---
        upload_invoice_file.delay(
            cellphone, invoice.invoice_number, invoice.is_pdf, invoice.file_path, last_id
        )
        logger.info("Factura confirmada y subida para %s — Drive upload encolado.", cellphone)

    except Exception as exc:
        logger.error("Error subiendo factura confirmada para %s: %s", cellphone, exc)
        _whatsapp.send_message(
            cellphone,
            "Hubo un error al subir la factura a Google Sheets. "
            "Por favor, inténtalo de nuevo enviando la factura.",
        )
        InvoiceSession.objects.filter(cellphone=cellphone).update(state="idle")
        Invoice.objects.filter(pk=invoice_pk).update(status="error")
        raise self.retry(exc=exc)


@shared_task
def upload_invoice_file(cellphone, invoice_number, is_pdf, file_path, row_id):
    """Sube el archivo de la factura (imagen o PDF) a Google Drive."""
    from core.services.google_drive import upload_invoice_in_folder
    from core.models import Invoice

    if is_pdf:
        folder_id = upload_invoice_in_folder(
            _drive_service,
            MAIN_FOLDER_ID,
            cellphone,
            invoice_number,
            flag_pdf=True,
            pdf_path=file_path,
            row_id=row_id,
        )
    else:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        folder_id = upload_invoice_in_folder(
            _drive_service,
            MAIN_FOLDER_ID,
            cellphone,
            invoice_number,
            flag_pdf=False,
            image_bytes=image_bytes,
            row_id=row_id,
        )

    # Persistir el ID de carpeta Drive en el Invoice correspondiente
    if folder_id:
        Invoice.objects.filter(
            cellphone=cellphone, sheet_record_id=str(row_id)
        ).update(drive_folder_id=folder_id)
        logger.info("drive_folder_id '%s' guardado para %s (row_id=%s).", folder_id, cellphone, row_id)

    # Limpiar archivo temporal de disco
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    logger.info("Archivo de factura subido a Drive para %s.", cellphone)


@shared_task
def upload_user_data(cellphone, cost_center, concept, last_row, invoice_pk=None):
    """Escribe el centro de costos y concepto en Google Sheets y confirma al usuario."""
    from core.services.google_sheets import upload_user_data_to_google_sheets

    upload_user_data_to_google_sheets(
        _sheets_service, SHEET_ID, [cost_center, concept], cellphone, last_row
    )

    if invoice_pk:
        from core.models import Invoice
        Invoice.objects.filter(pk=invoice_pk).update(
            cost_center=cost_center,
            concept=concept,
        )
        # --- Trigger Odoo Sync ---
        sync_invoice_payment_to_odoo.delay(invoice_pk)

    _whatsapp.send_message(cellphone, "Proceso con la factura completado. ✅")
    logger.info("Datos de usuario subidos para %s.", cellphone)


@shared_task
def sync_invoice_payment_to_odoo(invoice_pk):
    """
    Busca la factura en Odoo por referencia y registra el pago.
    Actualiza Google Sheets con el resultado.
    """
    from core.models import Invoice
    from core.services.odoo_client import OdooClient
    from core.services.google_sheets import write_data, get_sheets_service
    
    try:
        invoice = Invoice.objects.get(pk=invoice_pk)
        client = OdooClient()
        
        # 1. Buscar factura
        odoo_invoice = client.get_invoice_by_ref(invoice.invoice_number)
        
        if not odoo_invoice:
            status_doc = "❌ No encontrada"
            status_pago = "❌"
        else:
            state = odoo_invoice['state']
            if state == 'draft':
                status_doc = "⏳ Borrador (Odoo)"
                status_pago = "⏳ Pendiente"
            elif state == 'posted':
                status_doc = "✅ Causada"
                # Intentar registro de pago si no está pagada
                if odoo_invoice['payment_state'] in ['not_paid', 'partial']:
                    # Requerimiento: Diario = Nombre de la persona, Fecha = Fecha factura, Valor = Valor factura
                    # Usamos el nombre del empleado completo como diario principal
                    journal_name = invoice.employee.sheet_name
                    payment_date = odoo_invoice['invoice_date']
                    amount = invoice.value
                    
                    result = client.register_payment(
                        odoo_invoice['id'], 
                        journal_name, 
                        payment_date,
                        amount
                    )
                    if result['success']:
                        status_pago = "✅ Pagada"
                    else:
                        status_pago = f"❌ Error: {result['error']}"
                else:
                    status_pago = "✅ Pagada anteriormente"
            else:
                status_doc = f"❓ Estado: {state}"
                status_pago = "❓"

        # 2. Actualizar Google Sheets
        service = _sheets_service or get_sheets_service()
        sheet_id = settings.SHEET_ID
        sheet_name = invoice.employee.sheet_name
        row_num = invoice.sheet_row
        
        is_special = sheet_name in ('MANTENIMIENTO 2025', 'TRAB SOCIALES 2025')
        col_doc = "L" if is_special else "K"
        col_pago = "M" if is_special else "L"
        
        write_data(service, sheet_id, sheet_name, f"{col_doc}{row_num}", [[status_doc]])
        write_data(service, sheet_id, sheet_name, f"{col_pago}{row_num}", [[status_pago]])
        
        logger.info(f"Odoo sync completed for invoice {invoice.invoice_number}")
        
    except Exception as e:
        logger.error(f"Error in sync_invoice_payment_to_odoo: {e}")


# ---------------------------------------------------------------------------
# Tasks programadas (Celery Beat)
# ---------------------------------------------------------------------------

@shared_task
def monthly_write_headers():
    """Escribe encabezados mensuales en todas las hojas de empleados."""
    from core.services.google_sheets import write_monthly_headers

    from core.models import Employee

    sheet_names = list(
        Employee.objects.filter(is_active=True)
        .values_list("sheet_name", flat=True)
    )
    # Agregamos la hoja de desconocidos
    sheet_names.append("DESCONOCIDOS")

    write_monthly_headers(_sheets_service, SHEET_ID, sheet_names)
    logger.info("Encabezados mensuales escritos en %d hojas.", len(sheet_names))


@shared_task
def monthly_create_folders():
    """Crea las carpetas mensuales de Drive para todos los empleados."""
    from core.services.google_drive import create_monthly_folders

    create_monthly_folders(_drive_service, MAIN_FOLDER_ID)
    logger.info("Carpetas mensuales creadas en Drive.")


@shared_task
def create_employee_drive_folder(cellphone: str, sheet_name: str):
    """Crea la carpeta de Drive para un empleado recién creado."""
    from core.services.google_drive import create_employee_folder

    result = create_employee_folder(_drive_service, MAIN_FOLDER_ID, cellphone, sheet_name)
    logger.info("Carpeta Drive para %s: %s", cellphone, result)
