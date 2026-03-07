import json
import logging
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Employee, Invoice, InvoiceSession
from .tasks import confirm_and_upload, process_invoice, upload_user_data

logger = logging.getLogger(__name__)

ADMIN_CELLPHONE = settings.ADMIN_CELLPHONE
MANTAINER_CELLPHONE = settings.MANTAINER_CELLPHONE
TOKEN = settings.TOKEN
PHONE_NUMBER_ID = settings.PHONE_NUMBER_ID
VERIFY_TOKEN = settings.VERIFY_TOKEN


def _strip_prefix(number: str) -> str:
    """Devuelve el número de 10 dígitos sin el prefijo 57."""
    if number.startswith("57") and len(number) == 12:
        return number[2:]
    return number


def _parse_invoice_value(text: str) -> Decimal | None:
    """Valida que el texto sea un número entero o con punto decimal (máx 2 decimales).

    Formatos válidos: 125000, 125000.50, 125000.5
    NO acepta: comas, puntos de millar, signos de moneda, espacios.
    Retorna Decimal o None si es inválido.
    """
    cleaned = text.strip()

    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None

    try:
        value = Decimal(cleaned)
        if value <= 0:
            return None
        return value
    except (InvalidOperation, ValueError):
        return None


def _abandon_pending_invoice(session: InvoiceSession) -> None:
    """Marca como ABANDONED el invoice pendiente de la sesión, si existe."""
    if session.current_invoice_id and session.current_invoice.status == Invoice.Status.PENDING:
        Invoice.objects.filter(pk=session.current_invoice_id).update(
            status=Invoice.Status.ABANDONED
        )


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):

    def get(self, request):
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return HttpResponse(challenge)
        return HttpResponse("Verificación fallida", status=403)

    def post(self, request):
        try:
            data = json.loads(request.body)
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            from_number = message["from"]  # e.g. "573XXXXXXXXX"
        except (KeyError, IndexError, json.JSONDecodeError):
            # WhatsApp envía status updates que no contienen "messages"
            return HttpResponse("ok", status=200)

        bare_number = _strip_prefix(from_number)
        bare_admin = _strip_prefix(ADMIN_CELLPHONE)
        bare_mantainer = _strip_prefix(MANTAINER_CELLPHONE)

        is_admin = bare_number in (bare_admin, bare_mantainer)
        has_access = is_admin or Employee.objects.filter(
            cellphone=bare_number, is_active=True
        ).exists()

        if not has_access:
            logger.warning("Intento de acceso no autorizado de %s", from_number)
            return HttpResponse("ok", status=200)

        msg_type = message["type"]

        if msg_type == "image":
            self._handle_image(from_number, message)

        elif msg_type == "document":
            self._handle_document(from_number, message)

        elif msg_type == "text":
            self._handle_text(from_number, message)

        elif msg_type == "interactive":
            self._handle_interactive(from_number, message)

        else:
            from core.services.whatsapp_utils import WhatsAppClient
            wa = WhatsAppClient(TOKEN, PHONE_NUMBER_ID)
            wa.send_message(
                from_number,
                "Tipo de mensaje no soportado. Por favor, envía una imagen, PDF o texto.",
            )

        return HttpResponse("ok", status=200)

    # ------------------------------------------------------------------
    # Handlers por tipo de mensaje
    # ------------------------------------------------------------------

    def _handle_image(self, from_number: str, message: dict):
        from core.services.whatsapp_utils import WhatsAppClient
        wa = WhatsAppClient(TOKEN, PHONE_NUMBER_ID)

        sheet_name = (
            Employee.objects
            .filter(cellphone=_strip_prefix(from_number), is_active=True)
            .values_list("sheet_name", flat=True)
            .first()
        )
        sheet_line = f"\nSe registrará en la hoja: *{sheet_name}*" if sheet_name else ""
        wa.send_message(
            from_number, f"Tu factura fue recibida y está siendo procesada... 🛠️{sheet_line}"
        )

        image_id = message["image"]["id"]
        image_path = wa.download_image_to_disk(image_id, from_number)

        session, _ = InvoiceSession.objects.get_or_create(cellphone=from_number)
        _abandon_pending_invoice(session)
        session.state = InvoiceSession.State.PROCESSING
        session.save()

        process_invoice.delay(from_number, image_path=image_path)
        logger.info("Imagen encolada para procesamiento: %s", from_number)

    def _handle_document(self, from_number: str, message: dict):
        from core.services.whatsapp_utils import WhatsAppClient
        wa = WhatsAppClient(TOKEN, PHONE_NUMBER_ID)

        sheet_name = (
            Employee.objects
            .filter(cellphone=_strip_prefix(from_number), is_active=True)
            .values_list("sheet_name", flat=True)
            .first()
        )
        sheet_line = f"\nSe registrará en la hoja: 📄 *{sheet_name}*" if sheet_name else ""
        wa.send_message(
            from_number, f"Tu factura fue recibida y está siendo procesada... 🛠️{sheet_line}"
        )
        document_id = message["document"]["id"]
        filename = message["document"].get("filename", None)
        pdf_path = wa.download_pdf(document_id, filename)

        session, _ = InvoiceSession.objects.get_or_create(cellphone=from_number)
        _abandon_pending_invoice(session)
        session.state = InvoiceSession.State.PROCESSING
        session.save()

        process_invoice.delay(from_number, pdf_path=pdf_path, is_pdf=True)
        logger.info("PDF encolado para procesamiento: %s", from_number)

    def _handle_interactive(self, from_number: str, message: dict):
        from core.services.whatsapp_utils import WhatsAppClient
        wa = WhatsAppClient(TOKEN, PHONE_NUMBER_ID)

        try:
            button_id = message["interactive"]["button_reply"]["id"]
        except KeyError:
            logger.warning("Mensaje interactivo sin button_reply de %s", from_number)
            return

        try:
            session = InvoiceSession.objects.select_related("current_invoice").get(
                cellphone=from_number
            )
        except InvoiceSession.DoesNotExist:
            return

        if session.state != InvoiceSession.State.WAITING_CONFIRMATION:
            wa.send_message(from_number, "No hay ninguna confirmación pendiente.")
            return

        if button_id == "confirm_yes":
            session.state = InvoiceSession.State.WAITING_COST_CENTER
            session.save()
            confirm_and_upload.delay(from_number, session.current_invoice_id)
            logger.info("Valor confirmado por %s — confirm_and_upload encolado", from_number)

        elif button_id == "confirm_no":
            session.state = InvoiceSession.State.WAITING_CORRECTION
            session.save()
            wa.send_message(
                from_number,
                "Escribe el valor correcto (solo números, sin comas ni puntos de miles).\n"
                "Si requieres cifras decimales, usa un punto.\n"
                "Ejemplos: 125000 o 125000.50",
            )
            logger.info("Usuario %s solicitó corrección de valor", from_number)

    def _handle_text(self, from_number: str, message: dict):
        from core.services.whatsapp_utils import WhatsAppClient
        wa = WhatsAppClient(TOKEN, PHONE_NUMBER_ID)

        text = message["text"]["body"].strip()

        try:
            session = InvoiceSession.objects.select_related("current_invoice").get(
                cellphone=from_number
            )
        except InvoiceSession.DoesNotExist:
            wa.send_message(
                from_number,
                "Por favor, sube tu factura en formato PDF o imagen para iniciar.",
            )
            return

        state = session.state

        if state == InvoiceSession.State.PROCESSING:
            wa.send_message(
                from_number,
                "Tu factura está siendo procesada. Por favor, espera a que termine.",
            )

        elif state == InvoiceSession.State.WAITING_CONFIRMATION:
            wa.send_message(
                from_number,
                "Por favor, usa los botones para confirmar o corregir el valor de la factura.",
            )

        elif state == InvoiceSession.State.WAITING_CORRECTION:
            parsed = _parse_invoice_value(text)
            if parsed is None:
                wa.send_message(
                    from_number,
                    "El valor debe ser un número sin comas ni puntos de miles.\n"
                    "Ejemplos: 125000 o 125000.50\n"
                    "Intenta de nuevo:",
                )
                return

            invoice = session.current_invoice
            invoice.original_value = invoice.original_value  # preservar original
            invoice.value = parsed
            invoice.was_corrected = True
            invoice.save()

            session.state = InvoiceSession.State.WAITING_COST_CENTER
            session.save()
            confirm_and_upload.delay(from_number, invoice.pk)
            logger.info("Valor corregido por %s a %s — confirm_and_upload encolado", from_number, parsed)

        elif state == InvoiceSession.State.WAITING_COST_CENTER:
            # Guardar en Invoice y en legacy field
            if session.current_invoice:
                Invoice.objects.filter(pk=session.current_invoice_id).update(cost_center=text)
            session.cost_center = text
            session.state = InvoiceSession.State.WAITING_CONCEPT
            session.save()
            wa.send_message(from_number, "¿Cuál es el concepto de la factura?")
            logger.info("Centro de costos recibido de %s", from_number)

        elif state == InvoiceSession.State.WAITING_CONCEPT:
            invoice_pk = session.current_invoice_id
            # Guardar en Invoice
            if invoice_pk:
                Invoice.objects.filter(pk=invoice_pk).update(concept=text)

            session.state = InvoiceSession.State.IDLE
            session.save()
            upload_user_data.delay(
                from_number, session.cost_center, text, session.last_row,
                invoice_pk=invoice_pk,
            )
            logger.info("Concepto recibido de %s — upload_user_data encolado", from_number)

        else:
            wa.send_message(
                from_number,
                "Usuario reconocido. Por favor, sube tu factura en formato PDF o imagen para iniciar.",
            )


class HealthView(View):
    def get(self, request):
        try:
            connection.ensure_connection()
        except Exception:
            return JsonResponse({"status": "error", "db": "unavailable"}, status=503)
        return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# API Views for Administrative Portal
# ---------------------------------------------------------------------------

from core.models import Employee, Invoice
from django.db.models import Sum
import datetime

class CardsListView(View):
    def get(self, request):
        try:
            employees = Employee.objects.filter(is_active=True).order_by('sheet_name')
            cards = []
            
            today = datetime.date.today()
            current_month = today.month
            current_year = today.year
            
            for emp in employees:
                gastos = Invoice.objects.filter(
                    employee=emp,
                    invoice_date__year=current_year,
                    invoice_date__month=current_month
                ).aggregate(total=Sum('value'))['total'] or 0
                
                cupo = emp.monthly_limit or 0
                disponible = float(cupo) - float(gastos)
                
                cards.append({
                    "sheet_name": emp.sheet_name,
                    "card_label": emp.sheet_name.replace(f" {current_year}", "").strip(),
                    "leader": emp.sheet_name.split()[0], # Leader estimation
                    "cupo_mensual": float(cupo),
                    "valor_gastos": float(gastos),
                    "disponible": disponible
                })

            return JsonResponse(cards, safe=False)
        except Exception as e:
            logger.error(f"Error in CardsListView: {e}")
            return JsonResponse({"error": str(e)}, status=500)

class CardMonthsView(View):
    def get(self, request, sheet_name):
        try:
            emp = Employee.objects.filter(sheet_name=sheet_name).first()
            if not emp:
                return JsonResponse([], safe=False)
            
            months_qs = Invoice.objects.filter(employee=emp, invoice_date__isnull=False).dates('invoice_date', 'month')
            meses_espanol = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
            
            months_list = []
            for date_obj in months_qs:
                mes_str = f"{meses_espanol[date_obj.month - 1]} {date_obj.year}"
                months_list.append({
                    "month_label": mes_str,
                    "month_num": date_obj.month,
                    "year": date_obj.year,
                    "start_row": 0,
                    "end_row": 0
                })

            if not months_list:
                # If no invoices exist, add current month as default
                today = datetime.date.today()
                months_list.append({
                    "month_label": f"{meses_espanol[today.month - 1]} {today.year}",
                    "month_num": today.month,
                    "year": today.year,
                    "start_row": 0,
                    "end_row": 0
                })
                
            return JsonResponse(months_list, safe=False)
        except Exception as e:
            logger.error(f"Error in CardMonthsView: {e}")
            return JsonResponse({"error": str(e)}, status=500)

class ReportDataView(View):
    def get(self, request, sheet_name):
        try:
            month_num = request.GET.get("month")
            year_num = request.GET.get("year")
            
            emp = Employee.objects.filter(sheet_name=sheet_name).first()
            if not emp:
                return JsonResponse([], safe=False)
                
            qs = Invoice.objects.filter(employee=emp)
            if month_num and year_num:
                qs = qs.filter(invoice_date__year=int(year_num), invoice_date__month=int(month_num))
            
            rows = []
            for idx, inv in enumerate(qs.order_by('invoice_date')):
                rows.append({
                    "no": idx + 1,
                    "fecha": inv.invoice_date.strftime("%Y-%m-%d") if inv.invoice_date else "",
                    "nombre_negocio": inv.business_name,
                    "nit": inv.nit,
                    "num_factura": inv.invoice_number,
                    "centro_costos": inv.cost_center,
                    "concepto": inv.concept,
                    "valor_legalizado": float(inv.value or 0),
                    "url_drive": f"https://drive.google.com/drive/folders/{inv.drive_folder_id}" if inv.drive_folder_id else "",
                    "cufe": inv.cufe,
                    "check_odoo_doc": "VERDADERO" if inv.check_odoo_doc else "FALSO",
                    "check_odoo_pago": "VERDADERO" if inv.check_odoo_pago else "FALSO",
                    "diferencia": str(inv.difference or ""),
                    "observaciones": inv.observations,
                    "row_num": inv.id,
                    "row_bg_color": {'red': 1, 'green': 1, 'blue': 1}
                })

            return JsonResponse(rows, safe=False)
        except Exception as e:
            logger.error(f"Error in ReportDataView: {e}")
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class SyncOdooMonthView(View):
    def post(self, request, sheet_name):
        try:
            data = json.loads(request.body)
            month_num = data.get("month")
            year_num = data.get("year")

            if not month_num or not year_num:
                return JsonResponse({"error": "Missing month or year"}, status=400)

            emp = Employee.objects.filter(sheet_name=sheet_name).first()
            if not emp:
                return JsonResponse({"error": "Employee not found"}, status=404)

            qs = Invoice.objects.filter(
                employee=emp,
                invoice_date__year=int(year_num),
                invoice_date__month=int(month_num)
            )

            count = qs.count()
            if count == 0:
                return JsonResponse({"message": "No invoices found for this month"}, status=200)

            from core.tasks import sync_invoice_payment_to_odoo

            # Trigger Celery task for each invoice found
            queued = 0
            for inv in qs:
                # We skip invoices that are already marked as paid to avoid unnecessary syncs
                if not inv.check_odoo_pago:
                    sync_invoice_payment_to_odoo.delay(inv.pk)
                    queued += 1

            return JsonResponse({
                "message": f"Sync started for {queued} out of {count} invoices",
                "total": count,
                "queued": queued
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"Error in SyncOdooMonthView: {e}")
            return JsonResponse({"error": str(e)}, status=500)
