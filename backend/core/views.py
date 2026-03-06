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

from core.services.google_sheets import get_sheets_service
from .services.sheet_navigator import get_cards_list, get_months_in_sheet, get_month_rows

class CardsListView(View):
    def get(self, request):
        try:
            service = get_sheets_service()
            sheet_id = settings.SHEET_ID
            cards = get_cards_list(service, sheet_id)
            
            # Additional metrics for each card (M8, N8)
            from core.services.google_sheets import read_data
            for card in cards:
                try:
                    # Read M8 (Cupo) and N8 (Gastos)
                    # We assume sheet_navigator correctly returns sheet_name
                    metrics = read_data(service, sheet_id, card["sheet_name"], "M8:N8")
                    if metrics and metrics[0]:
                        card["cupo_mensual"] = metrics[0][0]
                        card["valor_gastos"] = metrics[0][1] if len(metrics[0]) > 1 else "0"
                        # Calculate available
                        try:
                            cupo = float(str(card["cupo_mensual"]).replace(",", ""))
                            gastos = float(str(card["valor_gastos"]).replace(",", ""))
                            card["disponible"] = cupo - gastos
                        except:
                            card["disponible"] = 0
                except Exception as e:
                    logger.error(f"Error reading metrics for card {card['sheet_name']}: {e}")
                    card["cupo_mensual"] = 0
                    card["valor_gastos"] = 0
                    card["disponible"] = 0

            return JsonResponse(cards, safe=False)
        except Exception as e:
            logger.error(f"Error in CardsListView: {e}")
            return JsonResponse({"error": str(e)}, status=500)

class CardMonthsView(View):
    def get(self, request, sheet_name):
        try:
            service = get_sheets_service()
            sheet_id = settings.SHEET_ID
            months = get_months_in_sheet(service, sheet_id, sheet_name)
            return JsonResponse(months, safe=False)
        except Exception as e:
            logger.error(f"Error in CardMonthsView: {e}")
            return JsonResponse({"error": str(e)}, status=500)

class ReportDataView(View):
    def get(self, request, sheet_name):
        try:
            start_row = int(request.GET.get("start_row", 12))
            end_row = int(request.GET.get("end_row", 100))
            service = get_sheets_service()
            sheet_id = settings.SHEET_ID
            rows = get_month_rows(service, sheet_id, sheet_name, start_row, end_row)
            return JsonResponse(rows, safe=False)
        except Exception as e:
            logger.error(f"Error in ReportDataView: {e}")
            return JsonResponse({"error": str(e)}, status=500)
