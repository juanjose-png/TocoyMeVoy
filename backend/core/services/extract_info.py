import io
import logging
import time
from decimal import Decimal

from django.conf import settings
from google import genai
from google.genai import types
from pdf2image import convert_from_path
from PIL import Image
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

### ---- Configuraciones para el uso de API Gemini para imágenes ---- ###

API_KEY = settings.GOOGLE_API_KEY

SYSTEM_INSTRUCTION = """Eres un asistente experto en la extracción de datos de documentos e imágenes. Tu única tarea es analizar la imagen de una factura o recibo de compra de Colombia que se te proporciona y extraer de manera precisa y literal los siguientes campos específicos.

1.  **Fecha de la factura**: La fecha exacta en que se emitió la factura. Analizala y entrégala en formato DD-MM-AAAA.
2.  **Nombre del comercio**: El nombre de la tienda, empresa, establecimiento o persona que emitió la factura o la que se le debe (ignora los nombres de *Solenium*, esa es nuestra empresa).
3.  **NIT**: El Número de Identificación Tributaria del comercio. Este número usualmente está precedido por las siglas "NIT" o está en un campo cercano al nombre del comercio, si no lo encuentras así, también aparece como firma o cédula (C.C) del vendedor o persona a la que se le debe.
4.  **ID ó # de factura**: El número o identificador único de la factura. Busca términos como "Factura Nro.", "Factura de Venta", "Recibo #", "ID" o similares.
5.  **Valor de la factura**: El monto **total** pagado. Busca el valor final, "TOTAL A PAGAR", "TOTAL" o el valor más prominente en la imagen. Extrae únicamente el valor numérico, sin el símbolo de pesos ($).

**Salida**:Devuelve un objeto JSON válido sin ningún texto adicional, delimitadores o formato especial. El JSON debe contener los siguientes campos: invoice_date, bussiness_name, nit, invoice_id, invoice_value.
**Regla crítica e inalterable**: Para cada uno de los campos solicitados, si no puedes encontrar la información en la imagen, si es ilegible o si tienes alguna duda sobre su exactitud, debes responder **únicamente** con el string "ERROR" para ese campo específico. No inventes, infieras o dejes un campo vacío.
**Consideración importante**: Al extraer el **Valor de la factura**, te puedes encontrar con separadores de punto '.' y de coma ','. Cuando luego de cualquiera de esos separadores, hayan solo 1 o 2 dígitos, estos seran la parte decimal.
Por ejemplo:
- 7.000,00 debe ser reportado como 7000.00
- 373,065.00 debe ser reportado como 373065.00
- 19.025 debe ser reportado como 19025.00

**Observación sobre el NIT**: La empresa nuestra se llama Solenium (SOLENIUM S.A.S), y su NIT es 901097244-5, si te encuentras con ese NIT o variaciones con puntos/comas de ese NIT, ignóralo y busca el NIT del vendedor."""

class Invoice(BaseModel):
    invoice_date: str
    bussiness_name: str
    nit: str
    invoice_id: str
    invoice_value: Decimal = Field(..., decimal_places=2)


class GeminiExtractor:
    """Cliente encapsulado para extracción de datos de facturas con Gemini."""

    def __init__(self, api_key: str | None = API_KEY) -> None:
        """Inicializa el cliente de la API Gemini.

        Args:
            api_key: Clave de API de Google AI Studio. Si es None o vacía,
                el extractor queda inoperativo y `extract_invoice` retornará None.
        """
        self._client = self._build_client(api_key)

    def _build_client(self, api_key: str | None) -> genai.Client | None:
        """Construye y retorna el cliente Gemini.

        Args:
            api_key: Clave de API de Google AI Studio.

        Returns:
            Cliente Gemini inicializado, o None si la clave no es válida o
            ocurrió un error durante la inicialización.
        """
        if not api_key:
            logger.warning("No se encontró una clave de API válida. Por favor, verifica tu archivo .env.")
            return None

        try:
            client = genai.Client(api_key=api_key)
            logger.info("Cliente GenAI inicializado correctamente.")
            return client
        except ImportError:
            logger.error("Por favor, instala el paquete 'google-genai' para utilizar esta funcionalidad.")
            return None
        except Exception as e:
            logger.error("Se produjo un error al inicializar el cliente GenAI: %s", e)
            return None

    def extract_invoice(
        self,
        image_bytes: bytes,
        model: str = "gemini-2.5-flash-lite",
        request_msg: str = "Extrae la información de la imagen",
    ) -> types.GenerateContentResponse | None:
        """Analiza una imagen de factura con Gemini y retorna la respuesta estructurada.

        Args:
            image_bytes: Bytes JPEG de la imagen a analizar.
            model: ID del modelo Gemini a utilizar.
            request_msg: Prompt adicional enviado junto a la imagen.

        Returns:
            Respuesta del modelo con los datos extraídos, o None si el cliente no
            está disponible o ocurrió un error no recuperable.
        """
        if not self._client:
            logger.error("El cliente GenAI no está inicializado. Por favor, inicialízalo primero.")
            return None

        while True:
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type='image/jpeg'
                        ),
                        request_msg
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=Invoice,
                        seed=42,
                        temperature=0.0
                    ),
                )

                logger.info("La IA procesó la factura con salida exitosa.")
                return response

            except Exception as e:
                error_str = str(e)
                if "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str:
                    logger.warning("API key agotada. Esperando un minuto antes de reintentar...")
                    time.sleep(60)
                    continue
                elif "503 UNAVAILABLE" in error_str:
                    logger.warning("El servicio está temporalmente no disponible. Esperando un minuto antes de reintentar...")
                    time.sleep(60)
                    continue
                else:
                    logger.error("Error al procesar la factura: %s", e)
                    return None


def pdf_pages_to_image(pdf_path: str) -> Image.Image | None:
    """Convierte un PDF en una sola imagen apilando sus páginas verticalmente.

    Args:
        pdf_path: Ruta al archivo PDF a convertir.

    Returns:
        Imagen PIL con todas las páginas apiladas, o None si ocurrió un error
        o el PDF no contiene imágenes.
    """
    try:
        images = convert_from_path(pdf_path)
    except Exception as e:
        logger.error("Error al convertir el PDF: %s. Asegúrate de que el archivo existe y es un PDF válido. Error: %s", pdf_path, e)
        return None
    
    if not images:
        logger.warning("No se encontraron imágenes en el PDF: %s.", pdf_path)
        return None
    
    if len(images) == 1:
        return images[0]

    # Unir todas las páginas en una sola imagen apilada verticalmente
    total_width = max(image.width for image in images)
    total_height = sum(image.height for image in images)
    merged_image = Image.new('RGB', (total_width, total_height))
    y_offset = 0
    for image in images:
        merged_image.paste(image, (0, y_offset))
        y_offset += image.height

    return merged_image



def pil_image_to_bytes(image: Image.Image, format: str = 'JPEG') -> bytes:
    """Convierte una imagen PIL a bytes.

    Args:
        image: Imagen PIL a serializar.
        format: Formato de salida (por defecto 'JPEG').

    Returns:
        Bytes de la imagen en el formato especificado.
    """
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format=format)
    return img_byte_arr.getvalue()
