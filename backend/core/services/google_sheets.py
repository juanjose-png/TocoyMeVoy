import os
import re
import json
import time
import logging
import random

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.services.constants import months_spanish

logger = logging.getLogger(__name__)


# Definimos los SCOPES necesarios para acceder a Google Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# Especificamos el archivo de credenciales de la cuenta del servicio
if os.path.exists("config/spreadsheets_credentials.json"):
    logger.info("Archivo de credenciales de la cuenta de servicio encontrado.")
    SERVICE_ACCOUNT_FILE = "config/spreadsheets_credentials.json"
else:
    logger.warning("Archivo de credenciales de la cuenta de servicio no encontrado. Las funciones de Google Sheets no estarán disponibles.")
    SERVICE_ACCOUNT_FILE = None


# Función que recibe el string del path al archivo de credenciales y devuelve un objeto de servicio
def get_sheets_service(service_account_file: str = SERVICE_ACCOUNT_FILE):
    """
    Crea un servicio de Google Sheets a partir de un archivo de cuenta de servicio.
    :param service_account_file: Ruta al archivo de credenciales del servicio.
    :return: Objeto de servicio de Google Sheets.
    """

    try:
        credentials = Credentials.from_service_account_file(service_account_file,
                                                            scopes=SCOPES)
    except Exception as e:
        logger.error("Error al cargar las credenciales de servicio: %s", e)
        return None

    try:
        # Construimos el servicio de Google Sheets
        service = build("sheets", "v4", credentials=credentials)
        # Inicializamos el objeto de la API de Google Sheets
        service_sheet = service.spreadsheets()
        logger.info("Servicio de Google Sheets construido correctamente.")
        return service_sheet

    except HttpError as err:
        logger.error("Error al construir el servicio de Google Sheets: %s", err)
        return None


# Función para leer datos de una hoja de cálculo dada
def read_data(service_sheet, sheet_id: str, sheet_name: str, range_full: str):
    """
    Lee datos de una hoja de cálculo.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param range_full: Rango de celdas a leer.
    :return: Lista de valores leídos de la hoja de cálculo.
    """

    # Ajustamos la expresión regular para capturar solo las letras antes y después del ':',
    # y obtener el número de columnas a leer
    match = re.match(r"([A-Z]+)[0-9]*:([A-Z]+)[0-9]*", range_full)
    if match:
        start_col, end_col = match.groups()
        # Convertir las letras de columna a índices (A=1, B=2, ..., Z=26, AA=27, etc.)
        expected_columns = ord(end_col) - ord(start_col) + 1
    else:
        # Si no se puede inferir, asumimos 1 columna
        expected_columns = 1

    try:
        result = service_sheet.values().get(spreadsheetId=sheet_id, range=f"{sheet_name}!{range_full}").execute()
        values = result.get("values", [])
    except HttpError as err:
        logger.error("Error al leer datos de la hoja: %s", err)
        return None

    # Ajustar las filas para que tengan una longitud fija de 'expected_columns' columnas
    adjusted_values = [
        row + [''] * (expected_columns - len(row)) if len(row) < expected_columns else row
        for row in values
    ]

    return adjusted_values


def read_multiple_ranges(service_sheet, sheet_id: str, ranges: list) -> list:
    """
    Lee múltiples rangos de una o varias hojas de cálculo en una sola llamada a la API.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param ranges: Lista de rangos a leer en notación A1 (ej. ["Hoja1!A1:B2", "Hoja2!C3:D4"]).
    :return: Lista de diccionarios valueRanges con la respuesta de la API.
    """
    if not ranges:
        return []

    try:
        result = service_sheet.values().batchGet(spreadsheetId=sheet_id, ranges=ranges).execute()
        return result.get("valueRanges", [])
    except HttpError as err:
        logger.error("Error al leer múltiples rangos: %s", err)
        return []


# Función para escribir datos en una hoja de cálculo dada
def write_data(service_sheet, sheet_id: str, sheet_name: str, range_full: str,
               values: list, font_size: int = None, font_color = None):
    """
    Escribe datos en una hoja de cálculo.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param range_full: Rango de celdas donde escribir los datos.
    :param values: Lista de valores a escribir.
    :param font_size: Tamaño de fuente a aplicar (opcional).
    :return: None
    """

    try:
        body = {
            "values": values
        }
        service_sheet.values().update(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!{range_full}",
            valueInputOption="RAW",
            body=body
        ).execute()


        # Si se especifica font_size, aplicamos el formato
        if font_size is not None or font_color is not None:
            # Obtenemos el sheetId numérico de la hoja a partir de su nombre
            spreadsheet_metadata = service_sheet.get(spreadsheetId=sheet_id).execute()
            sheet_id_num = None
            for s in spreadsheet_metadata['sheets']:
                if s['properties']['title'] == sheet_name:
                    sheet_id_num = s['properties']['sheetId']
                    break

            if sheet_id_num is None:
                logger.error("Error: No se encontró la hoja con el nombre '%s'", sheet_name)
                return

            # Extraer coordenadas del rango
            parts = range_full.split(':')
            start_cell = parts[0]
            end_cell = parts[-1]

            start_row = int(re.search(r'\d+', start_cell).group()) - 1
            end_row = int(re.search(r'\d+', end_cell).group())
            start_col_str = re.search(r'[A-Z]+', start_cell).group()
            start_col = ord(start_col_str) - ord('A')
            end_col_str = re.search(r'[A-Z]+', end_cell).group()
            end_col = ord(end_col_str) - ord('A') + 1

            # Crear el formato de texto (tamaño y color)
            text_format = {}
            if font_size is not None:
                text_format["fontSize"] = font_size
            if font_color is not None:
                text_format["foregroundColor"] = {
                    "red": round(font_color[0]/255.0, 3),
                    "green": round(font_color[1]/255.0, 3),
                    "blue": round(font_color[2]/255.0, 3)
                }

            requests = [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id_num,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": text_format
                                # "textFormat": {
                                #     "fontSize": font_size
                                # }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat"
                    }
                }
            ]
            body_format = {
                'requests': requests
            }
            service_sheet.batchUpdate(spreadsheetId=sheet_id, body=body_format).execute()
            logger.info("Formato aplicado al rango %s en la hoja %s.", range_full, sheet_name)

    except HttpError as err:
        logger.error("Error al escribir datos en la hoja %s: %s", sheet_name, err)
    except Exception as e:
        logger.error("Error inesperado al escribir datos en la hoja %s: %s", sheet_name, e)


# Función para limpiar los datos de una hoja de cálculo dada
def clear_data(service_sheet, sheet_id: str, sheet_name: str, range_full: str):
    """
    Limpia los datos de una hoja de cálculo.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param range_full: Rango de celdas a limpiar.
    :return: None
    """

    try:
        service_sheet.values().clear(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!{range_full}"
        ).execute()

        logger.info("Datos en el rango %s de la hoja %s limpiados correctamente.", range_full, sheet_name)
    except HttpError as err:
        logger.error("Error al limpiar los datos de la hoja: %s", err)


# Función para encontrar la última fila llena en una hoja de cálculo dada
def find_last_filled_row(service_sheet, sheet_id: str, sheet_name: str) -> int:
    """
    Encuentra la última fila válida basada en la columna H:
    - La fila es válida si la celda en H no está vacía.
    - Además, las 5 filas siguientes en H deben estar vacías.

    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja.
    :return: Número de la última fila válida encontrada.
    """
    try:
        # HACK : Lee solo desde la fila 12 (indicado por A12), saltandose el header de la hoja de cálculo
        # FIXME: Esto debería configurarse de una forma más robusta, por ahora se tiene así

        if sheet_name == 'MANTENIMIENTO 2025' or sheet_name == 'TRAB SOCIALES 2025':
            # Para las hojas de 'MANTENIMIENTO 2025' y 'TRAB SOCIALES 2025', leemos desde A12 hasta I
            data = read_data(service_sheet, sheet_id, sheet_name, "A12:I")
        else:
            # Sino, desde la A12 hasta la H
            data = read_data(service_sheet, sheet_id, sheet_name, "A12:H")

        if not data:
            return 0

        # Recorremos desde el principio hasta 5 antes del final
        for i in range(len(data) - 5):
            # Valor de la última columna (VALOR LEGALIZADO)
            current = data[i][-1]
            # Los siguientes 5 valores de la última columna (VALOR LEGALIZADO)
            next_5 = [data[i + j][-1] for j in range(1, 6)]

            # Verificamos si esa fila es válida, y las siguientes 5 están vacías
            if (current.strip() != "" and ('-' not in current)) and all((cell.strip() == "" or '-' in cell) for cell in next_5):
                # Sumamos uno para la convención de las hojas de cálculo, y los 11 del header
                return (i + 1) + 11

        # Si no se encuentra, revisamos si el final de la hoja tiene una fila no vacía en H
        for i in reversed(range(len(data))):
            value = data[i][-1].strip()

            # Comprobamos si la última fue una celda llenada por automatización con error en valor
            if ('-' in value) and (data[i][1] != ""):
                return (i + 1) + 11

            elif value != "" and '-' not in value:
                return (i + 1) + 11

        # Si no se encuentra ninguna fila válida, retornamos 11 (inicio estándar)
        return 11

    except Exception as e:
        logger.error("Error al encontrar la última fila válida: %s", e)
        return 11


# Función para obtener el 'No' de fila de la hoja de cálculo
def get_id_row(service_sheet, sheet_id: str, sheet_name:str, row_number: int) -> int:
    """
    Obtiene el número de fila de la hoja de cálculo basado en el nombre de la hoja y el número de fila.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param row_number: Número de fila (1-indexed).
    :return: Número de fila ajustado para la hoja de cálculo.
    """
    # Hacemos la lectura únicamente de la columna A para obtener el ID de fila
    #range_full = f"{sheet_name}!A{row_number}:A{row_number}"
    range = f"A{row_number}"

    try:
        values = read_data(service_sheet, sheet_id, sheet_name, range)

        if values:
            return int(values[0][0])
        else:
            # Si no se encuentre, buscamos en las anteriores 5 filas a la dada
            range = f"A{row_number-5}:A{row_number-1}"
            values = read_data(service_sheet, sheet_id, sheet_name, range)
            new_values = [value[0] for value in values]
            for i in reversed(new_values):
                if i != "":
                    try:
                        return int(i)
                    except Exception as e:
                        logger.warning("Retornando ID de fila como 0 por excepción: %s", e)
                        return 0

    # Si ocurre un error al obtener el ID de fila, retornamos 0 (inicio estándar)
    except HttpError as err:
        logger.error("Error al obtener el ID de fila: %s", err)
        return 0


# Función para obtener una lista de todas las hojas de cálculo no ocultas de un archivo
def get_visible_sheets_names(service_sheet, sheet_id: str):
    """
    Obtiene una lista de todas las hojas de cálculo visibles en un archivo.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :return: Lista de nombres de hojas visibles.
    """

    visible_sheets = []
    max_retries = 3

    for attempt in range(max_retries):
        try:
            spreadsheet = service_sheet.get(spreadsheetId=sheet_id).execute()
            sheets = spreadsheet.get("sheets", [])
            for sheet_info in sheets:
                # Tomamos las hojas en el campo "properties" y de aquí totamomos "title" y "hidden"
                is_hidden = sheet_info.get("properties", {}).get("hidden", False)
                if not is_hidden:
                    sheet_name = sheet_info.get("properties", {}).get("title", "Sin título")
                    visible_sheets.append(sheet_name)

            # Removemos las hojas que no son de interés que son
            # 'SALDOS EN EFECTIVO' y 'RECARGAS'
            visible_sheets = [sheet for sheet in visible_sheets if sheet not in ['SALDOS EN EFECTIVO', 'RECARGAS']]
            return visible_sheets

        except HttpError as err:
            error_code = err.resp.status
            if error_code in [503, 500, 429] and attempt < max_retries - 1:
                # Error temporal, reintentar con una espera exponencial
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning("Error temporal %s, reintentando en %s segundos... (intento %s/%s)", error_code, wait_time, attempt + 1, max_retries)
                time.sleep(wait_time)
                continue
            else:
                logger.error("Error al obtener las hojas visibles: %s", err)
                return None

    return None


# Función para insertar valores de una lista en una hoja de cálculo específica
def insert_values_in_sheet(service_sheet, sheet_id: str, sheet_name: str, values: list, num_row: int):
    """
    Inserta valores en una hoja de cálculo específica.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param values: Lista de valores a insertar.
    :param num_row: Número de fila donde se insertarán los valores.
    :return: None
    """

    if len(values[0]) == 6:

        # Aplicamos el formato numérico a la celda del ID/No. y la del monto
        set_number_format(service_sheet, sheet_id, sheet_name, f"A{num_row}", pattern="0")

        # Si la solicitud es a alguna de las hojas especiales con columna C de 'RESPONSABLE'
        if sheet_name == 'MANTENIMIENTO 2025' or sheet_name == 'TRAB SOCIALES 2025':

            # Usamos la función write_data para insertar los valores de la A a la B
            cells = f"A{num_row}:B{num_row}"
            # A: ID/No. (autoincremental)
            # B: Fecha
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                cells,
                [values[0][0:2]]
            )

            # Usamos la función write_data para insertar los valores de la D a la F
            cells = f"D{num_row}:F{num_row}"
            # D: Nombre de negocio
            # E: NIT
            # F: Número de factura
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                cells,
                [values[0][2:5]]
            )

            # Ahora otra solicitud para insertar el monto en columna I (VALOR LEGALIZADO)
            cells = f"I{num_row}"
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                cells,
                [[float(values[0][-1])]]
            )

        # Sino, es una de las hojas normales de personal
        else:

            cells = f"A{num_row}:E{num_row}"
            # Usamos la función write_data para insertar los valores de la A a la E
            # A: ID/No. (autoincremental)
            # B: Fecha
            # C: Nombre de negocio
            # D: NIT
            # E: Número de factura
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                cells,
                [values[0][:-1]]
            )

            # Ahora otra solicitud para insertar el monto en columna H
            cells = f"H{num_row}"
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                cells,
                [[float(values[0][-1])]]
            )

    else:
        logger.error("La lista contiene %s elementos en lugar de 6. Asegúrate de que la lista tiene el formato correcto.", len(values[0]))


# Función para insertar entradas de usuario en una hoja de cálculo específica
def insert_user_data_in_sheet(service_sheet, sheet_id: str, sheet_name: str, input: list, num_row: int):
    """
    Inserta valores en una hoja de cálculo específica.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param values: Lista de valores a insertar.
    :param num_row: Número de fila donde se insertarán los valores.
    :return: None
    """

    # La información debe ser una lista de longitud 2 con esta información:
    # - Centro de Costos
    # - Observaciones
    if len(input) == 2:

        # Si la solicitud es a alguna de las hojas especiales con columna C de 'RESPONSABLE'
        if sheet_name == 'MANTENIMIENTO 2025' or sheet_name == 'TRAB SOCIALES 2025':

            # Escribimos el 'Centro de Costos'
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                f"G{num_row}:G{num_row}",
                [input[:1]]
            )

            # Escribimos las 'Observaciones'
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                f"K{num_row}:K{num_row}",
                [input[1:]]
            )

        # Sino, es una de las hojas normales de personal
        else:

            # Escribimos el 'Centro de Costos'
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                f"F{num_row}:F{num_row}",
                [input[:1]]
            )

            # Escribimos las 'Observaciones'
            write_data(
                service_sheet,
                sheet_id,
                sheet_name,
                f"J{num_row}:J{num_row}",
                [input[1:]]
            )

    else:
        logger.error("La lista contiene %s elementos en lugar de 2. Asegúrate de que la lista tiene el formato correcto.", len(input))


# Función que inserta datos de factura en la hoja correspondiente
def insert_invoice_data(service_sheet, sheet_id: str, sheet_name: str, invoice_data: list) -> int:
    """
    Inserta datos de factura en la hoja correspondiente.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param invoice_data: Lista de datos de la factura a insertar.
    :return: Número que indica la fila donde se insertaron los datos.
    """

    # Encontramos la última fila válida
    last_row = find_last_filled_row(service_sheet, sheet_id, sheet_name)
    # Extraemos el ID/No de esa última fila
    last_row_id = get_id_row(service_sheet, sheet_id, sheet_name, last_row)


    # Verificamos que la fila siguiente no sea de cambio de mes (chequeando color rojo único)
    while True:
        color = get_cell_background_color(service_sheet, sheet_id, sheet_name, f"A{last_row + 1}")
        if 'blue' not in color.keys() and 'green' not in color.keys() and ('red' in color.keys()):
            # Se debe sumar una fila más y resetear ID a 0
            if color['red'] == 1:
                last_row = last_row + 1
                last_row_id = 0

            # Si se llega aquí es porque es una celda blanca (con los 3 colores RGB), y se puede escribir en ella
        else:
            break

    logger.info("Insertando datos en la siguiente fila: %s", last_row + 1)
    logger.info("Nuevo ID/No. para insertar: %s", last_row_id + 1)

    # Creamos la lista nueva con el autoincremento
    values_insert = [[last_row_id + 1] + invoice_data]

    # Insertamos los datos en la siguiente fila
    insert_values_in_sheet(service_sheet, sheet_id, sheet_name, values_insert, last_row + 1)

    return last_row + 1, last_row_id + 1


# Función para setear el formato a numérico en una celda
def set_number_format(service_sheet, sheet_id: str, sheet_name: str, cell_range: str, pattern: str = "0"):
    """
    Aplica un formato numérico a un rango de celdas.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param cell_range: Rango de celdas (ej. "A1" o "H5:H10").
    :param pattern: Patrón de formato numérico (ej. "0" para entero, "#,##0.00" para decimal).
    """
    try:
        # Obtener el sheetId numérico de la hoja a partir de su nombre
        spreadsheet_metadata = service_sheet.get(spreadsheetId=sheet_id).execute()
        sheet_id_num = None
        for s in spreadsheet_metadata['sheets']:
            if s['properties']['title'] == sheet_name:
                sheet_id_num = s['properties']['sheetId']
                break

        if sheet_id_num is None:
            logger.error("Error: No se encontró la hoja con el nombre '%s'", sheet_name)
            return

        # Extraer coordenadas del rango
        parts = cell_range.split(':')
        start_cell = parts[0]
        end_cell = parts[-1]

        # Regular expressions para extraer fila y columna

        # -------- Coordenada de la celda de inicio --------
        start_row_match = re.search(r'\d+', start_cell)
        if not start_row_match:
            logger.error("Error: No se encontró el número de fila en la celda de inicio '%s'", start_cell)
            return
        start_row = int(start_row_match.group()) - 1

        start_col_match = re.search(r'[A-Z]+', start_cell)
        if not start_col_match:
            logger.error("Error: No se encontró la columna en la celda de inicio '%s'", start_cell)
            return
        start_col_str = start_col_match.group()
        # Obtenemos la ordinalidad de esa columna (A=0, B=1, ...)
        start_col = ord(start_col_str) - ord('A')

        # -------- Coordenada de la celda final --------
        end_row_match = re.search(r'\d+', end_cell)
        if not end_row_match:
            logger.error("Error: No se encontró el número de fila en la celda final '%s'", end_cell)
            return
        end_row = int(end_row_match.group())

        end_col_match = re.search(r'[A-Z]+', end_cell)
        if not end_col_match:
            logger.error("Error: No se encontró la columna en la celda final '%s'", end_cell)
            return
        end_col_str = end_col_match.group()
        end_col = ord(end_col_str) - ord('A') + 1


        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id_num,
                        "startRowIndex": start_row,
                        "endRowIndex": end_row,
                        "startColumnIndex": start_col,
                        "endColumnIndex": end_col
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {
                                "type": "NUMBER",
                                "pattern": pattern
                            }
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            }
        ]

        body = {
            'requests': requests
        }
        service_sheet.batchUpdate(spreadsheetId=sheet_id, body=body).execute()
        logger.info("Formato '%s' aplicado al rango %s en la hoja %s.", pattern, cell_range, sheet_name)

    except HttpError as err:
        logger.error("Error al aplicar el formato de celda: %s", err)
    except Exception as e:
        logger.error("Un error inesperado ocurrió al aplicar formato: %s", e)


# Función que dado un rango de celdas, las rellena del color dado en tupla RGB
def fill_cells_color(service_sheet, sheet_id: str, sheet_name: str, cell_range: str, rgb_color: tuple, row_height: int = None):
    """
    Rellena un rango de celdas en una hoja de cálculo de Google Sheets con el color dado.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo.
    :param sheet_name: Nombre de la hoja de cálculo.
    :param cell_range: Rango de celdas (ej. "A1:B5").
    :param rgb_color: Tupla con los valores RGB del color (rojo, verde, azul).
    """
    try:
        # Obtener el sheetId numérico de la hoja a partir de su nombre
        spreadsheet_metadata = service_sheet.get(spreadsheetId=sheet_id).execute()
        sheet_id_num = None
        for s in spreadsheet_metadata['sheets']:
            if s['properties']['title'] == sheet_name:
                sheet_id_num = s['properties']['sheetId']
                break

        if sheet_id_num is None:
            logger.error("Error: No se encontró la hoja con el nombre '%s'", sheet_name)
            return

        # Extraer coordenadas del rango
        parts = cell_range.split(':')
        start_cell = parts[0]
        end_cell = parts[-1]

        # -------- Coordenada de la celda de inicio --------
        start_row = int(re.search(r'\d+', start_cell).group()) - 1
        start_col_str = re.search(r'[A-Z]+', start_cell).group()
        start_col = ord(start_col_str) - ord('A')

        # -------- Coordenada de la celda final --------
        end_row = int(re.search(r'\d+', end_cell).group())
        end_col_str = re.search(r'[A-Z]+', end_cell).group()
        end_col = ord(end_col_str) - ord('A') + 1

        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id_num,
                        "startRowIndex": start_row,
                        "endRowIndex": end_row,
                        "startColumnIndex": start_col,
                        "endColumnIndex": end_col
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {
                                "red": round(rgb_color[0] / 255.0, 3),
                                "green": round(rgb_color[1] / 255.0, 3),
                                "blue": round(rgb_color[2] / 255.0, 3)
                            }
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
        ]

        # Si se especifica row_height, agregamos la petición para cambiar el alto de la fila
        if row_height is not None:
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id_num,
                        "dimension": "ROWS",
                        "startIndex": start_row,
                        "endIndex": end_row
                    },
                    "properties": {
                        "pixelSize": row_height
                    },
                    "fields": "pixelSize"
                }
            })

        body = {
            'requests': requests
        }
        service_sheet.batchUpdate(spreadsheetId=sheet_id, body=body).execute()

    except Exception as e:
        logger.error("Error al rellenar las celdas de color %s: %s", rgb_color, e)


# Función para actualizar el JSON tipo diccionario de celular y hojas de cálculo
def update_cellphones_sheets_json(service, sheet_id: str):
    """
    Actualiza el archivo JSON 'cellphones_sheets.json' (ubicado en la carpeta 'config') con los números de celular y sus hojas correspondientes.
    :return: None
    """

    # Leemos el diccionario actual para poder comparar
    current_dictionary = {}
    if os.path.exists("config/cellphones_sheets.json"):
        with open("config/cellphones_sheets.json", "r") as f:
            current_dictionary = json.load(f)

    # Obtenemos todas las hojas visibles
    visible_sheets = get_visible_sheets_names(service, sheet_id)

    if visible_sheets is None:
        logger.error("No se pudieron obtener las hojas visibles. Abortando la actualización del JSON, así que queda igual.")
        return

    new_dictionary_cellphones = {}
    # Iteramos sobre las hojas visibles de interés
    for sheet_name in visible_sheets:
        # Leemos las celdas K8:L8
        try:
            cell_values = read_data(service, sheet_id, sheet_name, "K8:L8")

            # Verificamos si se obtuvieron datos
            if not cell_values or not cell_values[0]:
                continue

            # Limpiamos los espacios de las celdas, para una lectura robusta
            cell_values_clean = [cell.strip() for cell in cell_values[0]]
            # Esto para identificar números colombianos
            patron = r'^\d{10}$'

            for cell in cell_values_clean:
                if re.match(patron, cell):
                    new_dictionary_cellphones[cell] = sheet_name

        except HttpError as err:
            logger.error("Error al leer las celdas K8:L8 en %s:\n%s", sheet_name, err)
            continue

    # Si el diccionario nuevo es diferente al anterior, lo actualizamos
    if new_dictionary_cellphones != current_dictionary:

        # Creamos el directorio 'config' si no existe
        os.makedirs("config", exist_ok=True)

        # Guardamos el diccionario actualizado en el archivo JSON
        with open("config/cellphones_sheets.json", "w") as f:
            json.dump(new_dictionary_cellphones, f, indent=4)

        logger.info("Archivo 'cellphones_sheets.json' actualizado correctamente.")

    else:
        logger.info("No se realizaron cambios en 'cellphones_sheets.json'. El diccionario es el mismo.")


# Función para mapear el número de celular a su hoja de cálculo correspondiente
def get_sheet_name_from_cellphone(cellphone: str) -> str:
    """
    Obtiene el nombre de la hoja de cálculo basado en el número de celular.
    :param cellphone: Número de celular a buscar.
    :return: Nombre de la hoja de cálculo donde se encuentra el número de celular.
    """

    from core.services.employee_service import get_sheet_name_from_db
    return get_sheet_name_from_db(cellphone)



# ------ FUNCIÓN PRINCIPAL PARA ENVIAR INFORMACIÓN A GOOGLE SHEETS DE UNA FACTURA ------
def upload_invoice_to_google_sheets(service_sheet, sheet_id: str, invoice_data: list, cellphone: str) -> tuple:
    """
    Función principal para subir la información de una factura a Google Sheets.
    :param invoice_data: Lista con los datos de la factura.
    :param sheet_id: ID de la hoja de cálculo donde se subirá la información.
    :param cellphone: Número de celular asociado a la factura.
    :return: None
    """

    if invoice_data is None or not invoice_data:
        logger.warning("No se proporcionaron datos de la factura o están vacíos.")
        return None, None

    elif invoice_data is not None and len(invoice_data) != 5:
        logger.error("Los datos de la factura deben contener 5 elementos, pero se recibieron %s.", len(invoice_data))
        return None, None

    try:

        # Inicializamos el servicio de Google Sheets si no estaba inicializado
        if not service_sheet:
            try:
                service_sheet = get_sheets_service()
                logger.info("Servicio de Google Sheets inicializado de nuevo correctamente.")
            except Exception as e:
                logger.error("Error al inicializar el servicio de Google Sheets: %s", e)
                return None, None

        # A partir del número de celular, obtenemos la hoja de cálculo correspondiente
        sheet_name = get_sheet_name_from_cellphone(cellphone)

        # Ahora teniendo el nombre de la hoja, insertamos los datos de la factura
        last_row, last_id = insert_invoice_data(service_sheet, sheet_id, sheet_name, invoice_data)

        logger.info("Factura subida correctamente a la hoja '%s' de Google Sheets.", sheet_name)
        return last_row, last_id

    except Exception as e:
        logger.error("Error al subir la factura a Google Sheets: %s", e)
        return last_row, last_id


# ------ FUNCIÓN PRINCIPAL PARA ENVIAR INFORMACIÓN A GOOGLE SHEETS DE LOS DATOS USUARIO WHATSAPP ------
def upload_user_data_to_google_sheets(service_sheet, sheet_id: str, user_data: list, cellphone: str, last_row: int) -> bool:
    """
    Función principal para subir la información de un usuario a Google Sheets.
    :param user_data: Lista con los datos ingresados por el usuario.
    :param sheet_id: ID de la hoja de cálculo donde se subirá la información.
    :param cellphone: Número de celular asociado a la factura.
    :return: None
    """

    if user_data is None or not user_data:
        logger.warning("No se proporcionaron datos de la factura o están vacíos.")
        return False

    elif user_data is not None and len(user_data) != 2:
        logger.error("Los datos del usuario deben contener 2 elementos, pero se recibieron %s.", len(user_data))
        return False

    try:

        # Inicializamos el servicio de Google Sheets si no estaba inicializado
        if not service_sheet:
            try:
                service_sheet = get_sheets_service()
                logger.info("Servicio de Google Sheets inicializado de nuevo correctamente.")
            except Exception as e:
                logger.error("Error al inicializar el servicio de Google Sheets: %s", e)
                return False

        # A partir del número de celular, obtenemos la hoja de cálculo correspondiente
        sheet_name = get_sheet_name_from_cellphone(cellphone)

        # Ahora teniendo el nombre de la hoja, insertamos los datos de la factura
        insert_user_data_in_sheet(service_sheet, sheet_id, sheet_name, user_data, last_row)
        #insert_user_data(service_sheet, sheet_id, sheet_name, user_data, last_row)

        logger.info("Datos del usuario subidos correctamente a la hoja '%s' de Google Sheets.", sheet_name)
        return True

    except Exception as e:
        logger.error("Error al subir los datos del usuario a Google Sheets: %s", e)
        return False


# Función que escribe el cabezado en las hojas de cálculo al inicio de cada mes
def write_monthly_headers(service_sheet, sheet_id: str, sheet_names: list[str]):
    """
    Escribe el encabezado del mes en las hojas de cálculo indicadas.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID de la hoja de cálculo donde se escribirán los encabezados.
    :param sheet_names: Lista de nombres de hojas donde escribir los encabezados.
    """

    # Obtenemos la fecha a poner (mes y año)
    current_month = months_spanish[time.strftime("%B", time.localtime())].upper()
    current_year = time.strftime("%Y", time.localtime())
    current_date = f"{current_month} {current_year}"

    # Ahora iteramos por cada hoja:
    for sheet_name in sheet_names:
        try:
            # Obtenemos la fila en la que vamos a escribir
            row_to_write = find_last_filled_row(service_sheet, sheet_id, sheet_name) + 1

            if sheet_name == 'MANTENIMIENTO 2025' or sheet_name == 'TRAB SOCIALES 2025':
                # Creamos los range
                cell_range = f"A{row_to_write}:F{row_to_write}"
                fill_cells_color(service_sheet, sheet_id,
                                    sheet_name, cell_range,
                                (255, 0 , 0), row_height=32)

                # Escribimos ahora la fecha
                cell_range = f"G{row_to_write}:G{row_to_write}"
                write_data(service_sheet, sheet_id, sheet_name, cell_range,
                            [[current_date]], font_size=18, font_color=(255, 0, 0))

                # Color a la otra parte
                cell_range = f"H{row_to_write}:L{row_to_write}"
                fill_cells_color(service_sheet, sheet_id,
                                    sheet_name, cell_range,
                                (255, 0, 0), row_height=32)

            else:
                # Creamos los range
                cell_range = f"A{row_to_write}:E{row_to_write}"
                fill_cells_color(service_sheet, sheet_id,
                                    sheet_name, cell_range,
                                (255, 0 , 0), row_height=32)

                # Escribimos ahora la fecha con el tamaño y en color rojo -> (255, 0, 0)
                cell_range = f"F{row_to_write}:F{row_to_write}"
                write_data(service_sheet, sheet_id, sheet_name, cell_range,
                            [[current_date]], font_size=18, font_color=(255, 0, 0))

                # Color a la otra parte
                cell_range = f"G{row_to_write}:K{row_to_write}"
                fill_cells_color(service_sheet, sheet_id,
                                    sheet_name, cell_range,
                                (255, 0, 0), row_height=32)

            logger.info("Encabezado escrito en hoja '%s' (fila %d).", sheet_name, row_to_write)

        except Exception as e:
            logger.error("Error al escribir encabezado en hoja '%s': %s", sheet_name, e)

        # Esperamos 5 segundos entre cada hoja para evitar problemas de límite de solicitudes
        time.sleep(5)


# Función que retorna de manera simple el color en una celda de Google Spreadsheets
def get_cell_background_color(service_sheet, sheet_id: str, sheet_name: str, cell: str):
    """
    Obtiene el color de fondo de una celda específica en Google Sheets.
    :param service_sheet: Objeto de servicio de Google Sheets.
    :param sheet_id: ID del archivo de Google Sheets.
    :param sheet_name: Nombre de la hoja.
    :param cell: Celda (ejemplo: "A1").
    :return: Diccionario con los valores RGB normalizados (0-1) o None si no hay color.
    """
    try:
        result = service_sheet.get(
            spreadsheetId=sheet_id,
            ranges=[f"{sheet_name}!{cell}"],
            fields="sheets.data.rowData.values.effectiveFormat.backgroundColor"
        ).execute()

        color = (
        result.get("sheets", [{}])[0]
        .get("data", [{}])[0]
        .get("rowData", [{}])[0]
        .get("values", [{}])[0]
        .get("effectiveFormat", {})
        .get("backgroundColor")
        )

        # Retornamos el color
        if color == {}:
            return {'red': 1, 'green': 1, 'blue': 1}
        else:
            return color
    except Exception as e:
        logger.error(f"Error al obtener color de {sheet_name}!{cell}: {e}")
        return {'red': 1, 'green': 1, 'blue': 1}

def get_range_background_colors(service_sheet, sheet_id: str, sheet_name: str, cell_range: str) -> list:
    """
    Obtiene los colores de fondo de un rango 1D vertical en Google Sheets en una sola petición.
    Retorna una lista donde cada elemento es el diccinario RGB de color correspondiente a esa fila.
    """
    try:
        result = service_sheet.get(
            spreadsheetId=sheet_id,
            ranges=[f"{sheet_name}!{cell_range}"],
            fields="sheets.data.rowData.values.effectiveFormat.backgroundColor"
        ).execute()

        row_data = (
            result.get("sheets", [{}])[0]
            .get("data", [{}])[0]
            .get("rowData", [])
        )
        
        colors = []
        for row in row_data:
            values = row.get("values", [])
            if values:
                color = values[0].get("effectiveFormat", {}).get("backgroundColor")
                if not color or color == {}:
                    colors.append({'red': 1, 'green': 1, 'blue': 1})
                else:
                    colors.append(color)
            else:
                colors.append({'red': 1, 'green': 1, 'blue': 1})
        return colors
    except Exception as e:
        logger.error(f"Error al obtener colores del rango {sheet_name}!{cell_range}: {e}")
        return []
