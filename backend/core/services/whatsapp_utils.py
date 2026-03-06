import logging
import os
import re
import time

import requests

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Cliente para la API de WhatsApp Business (Graph API v22.0).

    Centraliza las credenciales y la URL base para todas las operaciones
    de descarga de medios y envío de mensajes.

    Attributes:
        _API_BASE: URL raíz de la Graph API de Meta.

    Example:
        >>> from core.services.whatsapp_utils import WhatsAppClient
        >>> wa = WhatsAppClient(token="TOKEN", phone_number_id="PHONE_ID")
        >>> wa.send_message("3001234567", "Hola!")
    """

    _API_BASE = "https://graph.facebook.com/v22.0"

    def __init__(self, token: str, phone_number_id: str) -> None:
        """Inicializa el cliente con las credenciales de la API.

        Args:
            token: Token de acceso de Meta Business (``TOKEN`` en ``.env``).
            phone_number_id: ID del número de teléfono registrado en Meta
                (``PHONE_NUMBER_ID`` en ``.env``).
        """
        self._token = token
        self._phone_number_id = phone_number_id
        self._headers = {"Authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------------
    # Descarga de medios
    # ------------------------------------------------------------------

    def download_image(self, media_id: str) -> bytes:
        """Descarga una imagen enviada por WhatsApp y devuelve sus bytes.

        Args:
            media_id: ID del medio asignado por la API de WhatsApp.

        Returns:
            Contenido binario de la imagen descargada.
        """
        url_info = f"{self._API_BASE}/{media_id}"
        res = requests.get(url_info, headers=self._headers)
        res.raise_for_status()
        
        media_url = res.json()["url"]

        image_res = requests.get(media_url, headers=self._headers)
        return image_res.content

    def download_image_to_disk(self, media_id: str, cellphone: str) -> str:
        """Descarga una imagen de WhatsApp y la guarda en ``archivos_img/``.

        Args:
            media_id: ID del medio asignado por la API de WhatsApp.
            cellphone: Número de celular (usado para nombrar el archivo).

        Returns:
            Ruta relativa al archivo guardado
            (e.g. ``archivos_img/573xxx_20260302_120000.jpg``).
        """
        url_info = f"{self._API_BASE}/{media_id}"
        res = requests.get(url_info, headers=self._headers)
        res.raise_for_status()

        media_url = res.json()["url"]

        image_res = requests.get(media_url, headers=self._headers)
        image_res.raise_for_status()

        filename = f"{cellphone}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        os.makedirs("archivos_img", exist_ok=True)
        filepath = os.path.join("archivos_img", filename)
        with open(filepath, "wb") as f:
            f.write(image_res.content)

        logger.info("Imagen guardada como '%s'", filepath)
        return filepath

    def download_pdf(self, media_id: str, filename: str | None = None) -> str:
        """Descarga un PDF enviado por WhatsApp y lo guarda en ``archivos_pdf/``.

        Args:
            media_id: ID del medio asignado por la API de WhatsApp.
            filename: Nombre del archivo de destino. Si es ``None`` se genera
                uno con marca de tiempo (``factura_YYYYMMDD_HHMMSS.pdf``).

        Returns:
            Ruta relativa al archivo guardado
            (e.g. ``archivos_pdf/factura_...pdf``).
        """
        media_info_url = f"{self._API_BASE}/{media_id}"

        res_info = requests.get(media_info_url, headers=self._headers)
        res_info.raise_for_status()

        media_url = res_info.json()["url"]

        res_file = requests.get(media_url, headers=self._headers)
        res_file.raise_for_status()

        if not filename:
            filename = f"factura_{time.strftime('%Y%m%d_%H%M%S')}.pdf"

        os.makedirs("archivos_pdf", exist_ok=True)
        filename = os.path.join("archivos_pdf", filename)
        with open(filename, "wb") as f:
            f.write(res_file.content)

        logger.info("PDF guardado como '%s'", filename)
        return filename

    # ------------------------------------------------------------------
    # Envío de mensajes
    # ------------------------------------------------------------------

    def send_message(self, cellphone: str, message: str) -> str:
        """Envía un mensaje de texto a un número de WhatsApp.

        Añade automáticamente el prefijo ``57`` si el número no lo incluye.

        Args:
            cellphone: Número de teléfono del destinatario (10 dígitos o con
                prefijo ``57``/``+57``).
            message: Texto del mensaje a enviar.

        Returns:
            Cadena descriptiva del resultado (éxito o error con código HTTP).
        """
        pattern = re.compile(r'^\+?57\d{10}$')
        if not pattern.match(cellphone):
            cellphone = f"57{cellphone}"

        url = f"{self._API_BASE}/{self._phone_number_id}/messages"

        data = {
            "messaging_product": "whatsapp",
            "to": cellphone,
            "type": "text",
            "text": {"body": message}
        }

        headers = {**self._headers, "Content-Type": "application/json"}

        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            logger.error(
                "Error al enviar mensaje a %s: %s - %s",
                cellphone, response.status_code, response.text,
            )
            response.raise_for_status()
        return f"Mensaje enviado a {cellphone}: {message}"

    def send_invoice_data(self, cellphone: str, invoice_data: list) -> str:
        """Envía un resumen de los datos de una factura procesada al usuario.

        Formatea cada campo con su etiqueta y envía el mensaje vía
        :meth:`send_message`.

        Args:
            cellphone: Número de teléfono del destinatario.
            invoice_data: Lista de valores de la factura en el orden
                ``[fecha, comercio, nit, id_factura, valor]``.

        Returns:
            Cadena descriptiva del resultado de :meth:`send_message`.
        """
        message = "🤖 Datos de la factura procesada:\n"
        keys = ["Fecha", "Comercio", "NIT", "ID/# Factura", "Valor"]
        for key, value in zip(keys, invoice_data):
            if key == "Valor":
                value = f"$ {value}"
            message += f"\t*{key}*: {value}\n"

        return self.send_message(cellphone, message)

    def send_confirmation_buttons(self, cellphone: str, invoice_value) -> str:
        """Envía botones interactivos para confirmar el valor de la factura.

        Args:
            cellphone: Número de teléfono del destinatario.
            invoice_value: Valor extraído de la factura (se formatea como moneda).

        Returns:
            Cadena descriptiva del resultado.
        """
        pattern = re.compile(r'^\+?57\d{10}$')
        if not pattern.match(cellphone):
            cellphone = f"57{cellphone}"

        url = f"{self._API_BASE}/{self._phone_number_id}/messages"

        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cellphone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": (
                        f"El valor extraído de la factura es: *$ {invoice_value}*\n\n"
                        "¿Es correcto?"
                    ),
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "confirm_yes",
                                "title": "✅ Sí, correcto",
                            },
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "confirm_no",
                                "title": "❌ No, corregir",
                            },
                        },
                    ],
                },
            },
        }

        headers = {**self._headers, "Content-Type": "application/json"}

        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            logger.error(
                "Error al enviar botones a %s: %s - %s",
                cellphone, response.status_code, response.text,
            )
            response.raise_for_status()
        return f"Botones de confirmación enviados a {cellphone}"
