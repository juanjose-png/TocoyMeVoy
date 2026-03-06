import os
import re
import io
import time
import pickle
import datetime
import logging

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

from core.services.constants import months_spanish

logger = logging.getLogger(__name__)


# Especificamos el archivo de OAuth token
if os.path.exists("config/oauth_token.json"):
    logger.info("Archivo de OAuth token encontrado.")
    OAUTH_TOKEN_FILE = "config/oauth_token.json"
else:
    logger.error("Archivo de OAuth token no encontrado. Asegúrate de que 'oauth_token.json' existe en el directorio actual.")
    raise FileNotFoundError("El archivo de OAuth token no se encontró.")


# Función para crear un objeto de servicio de la APIs de Google
def create_google_service(api_name: str = "sheets", api_version: str = "v4", *scopes):
    scopes_un = [scope for scope in scopes[0]]


    creds = None
    pickle_file = f"token_{api_name}_{api_version}.pickle"
    pickle_file = os.path.join("config", pickle_file)

    if os.path.exists(pickle_file):
        with open(pickle_file, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_TOKEN_FILE, scopes_un)
            # creds = flow.run_local_server(port=0)
            creds = flow.run_local_server()

        with open(pickle_file, "wb") as token:
            pickle.dump(creds, token)


    try:
        service = build(api_name, api_version, credentials=creds)

        if api_name == "sheets":
            service = service.spreadsheets()
        logger.info("Servicio de Google '%s' creado correctamente.", api_name.upper())
        return service
    except Exception as e:
        logger.error("Error al crear el servicio de Google %s: %s", api_name.upper(), e)
        return None


# Función para subir una imagen en bytes a una carpeta de Google Drive
def upload_image_to_drive(service_drive, image_bytes, image_name, folder_id):
    """
    Subir una imagen en bytes a Google Drive.
    :param service_drive: Objeto de servicio de Google Drive.
    :param folder_id: ID de la carpeta de destino en Drive.
    :param image_bytes: Imagen en bytes a subir.
    :param image_name: Nombre que tendrá la imagen en Drive.
    :return: ID del archivo subido o None en caso de error.
    """

    try:
        # Crear un objeto MediaIoBaseUpload a partir de los bytes de la imagen
        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype='image/jpeg')

        # Configurar metadatos del archivo
        file_metadata = {
            'name': image_name,
            'parents': [folder_id]
        }

        # Subir el archivo
        file = service_drive.files().create(
            body=file_metadata,
            media_body=media,
            fields='name'
        ).execute()

        logger.info("Imagen subida correctamente: %s", file['name'])

    except Exception as e:
        logger.error("Error al subir la imagen: %s", e)


# Función para subir un archivo PDF a una carpeta de Google Drive
def upload_pdf_to_drive(service_drive, pdf_path, pdf_name, folder_id):
    """
    Sube un archivo PDF a Google Drive.
    :param service_drive: Objeto de servicio de Google Drive.
    :param pdf_path: Ruta al archivo PDF local.
    :param pdf_name: Nombre que tendrá el archivo PDF en Drive.
    :param folder_id: ID de la carpeta de destino en Drive.
    """
    try:
        # Crear un objeto MediaFileUpload a partir del path del PDF
        media = MediaFileUpload(pdf_path, mimetype='application/pdf')

        # Configurar metadatos del archivo
        file_metadata = {
            'name': pdf_name,
            'parents': [folder_id]
        }

        # Subir el archivo
        file = service_drive.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'  # Solicitar también el ID en la respuesta
        ).execute()

        logger.info("PDF subido correctamente: %s", file['name'])

    except Exception as e:
        logger.error("Error al subir el PDF: %s", e)


# Función para crear una carpeta en Google Drive
def create_folder_in_drive(service_drive, parent_folder_id, folder_name):
    """
    Crea una carpeta en Google Drive dentro de otra carpeta especificada.
    :param service_drive: Objeto de servicio de Google Drive.
    :param parent_folder_id: ID de la carpeta padre donde se creará la nueva carpeta.
    :param folder_name: Nombre de la nueva carpeta.
    """
    try:
        # Metadatos de la carpeta que se va a crear
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }

        # Crear la carpeta
        file = service_drive.files().create(body=file_metadata,
                                            fields='id, name').execute()
        return file.get("id")

    except Exception as e:
        logger.error("Error al crear la carpeta: %s", e)
        return None


# Función para obtener el ID de un subfolder de acuerdo al número de celular
def get_subfolder_id(service_drive, folder_id: str, cellphone: str) -> str:
    """
    Obtiene el ID de un subfolder específico en Google Drive basado en el número de celular.
    :param service_drive: Objeto de servicio de Google Drive.
    :param folder_id: ID del folder principal donde se buscará el subfolder.
    :param cellphone: Número de celular para identificar el subfolder.
    :return: ID del subfolder encontrado o None si no se encuentra.
    """

    def get_folder_by_cellphone(folder_id, cellphone):
        query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed = false and name contains '{cellphone}'"
        response = service_drive.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        return response['files']

    try:
        folder_info = get_folder_by_cellphone(folder_id, cellphone)
        # Si el folder es una lista vacía, significa que no se encontró un subfolder con ese número de celular
        if len(folder_info) == 0:
            # Usamos entonces el folder "DESCONOCIDOS"
            query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed = false and name contains 'DESCONOCIDOS'"
            response = service_drive.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            folder_info = response.get("files", [])

        employee_folder_id = folder_info[0].get("id")

        # Ahora obtenemos el mes y año actual
        current_month = months_spanish[time.strftime("%B", time.localtime())].upper()
        current_year = time.strftime("%Y", time.localtime())
        # Patrón de búsqueda para el subfolder hijo según la fecha (sin importar mayúsculas o minúsculas)
        pattern = r"(?i)" + re.escape(current_month) + r"\s+" + re.escape(current_year)

        # Ahora obtenemos todos los subfolders de ese folder
        query = f"'{employee_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed = false"
        response = service_drive.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        subfolders_info = response.get("files", [])

        # Buscamos el subfolder correspondiente al mes actual
        for subfolder_info in subfolders_info:
            name_folder = subfolder_info.get("name")

            # Si coincide lo retornamos
            if bool(re.search(pattern, name_folder)):
                return subfolder_info.get("id")

        # Si pasó por el ciclo sin encontrar el folder, se retorna la raíz
        return employee_folder_id

    except Exception as e:
        logger.error("Error al obtener el ID del subfolder: %s", e)
        return None


def get_quantity_folders_in_folder_id(service_drive, folder_id: str):
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed = false"
    folders = service_drive.files().list(q=query, spaces='drive', fields='files(name)').execute().get('files', [])
    return len(folders)


def get_quantity_files_in_folder_id(service_drive, folder_id: str):
    query = f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed = false"
    files = service_drive.files().list(q=query, spaces='drive', fields='files(name)').execute().get('files', [])
    return len(files)


# Función para cargar una factura en Google Drive según número celular
def upload_invoice_in_folder(service_drive, main_folder_id: str, cellphone: str, invoice_id: str,
                             flag_pdf: bool, image_bytes = None, pdf_path = None, row_id: int = None):
    """
    Carga una factura en la carpeta correspondiente de Google Drive según el número de celular.
    :param service_drive: Objeto de servicio de Google Drive.
    :param main_folder_id: ID de la carpeta principal donde se encuentra el subfolder.
    :param cellphone: Número de celular del usuario.
    :param flag_pdf: Indica si se debe subir un PDF o una imagen.
    :param image_bytes: Bytes de la imagen a subir (si aplica).
    :param pdf_path: Ruta al archivo PDF a subir (si aplica).
    :param row_id: ID de la fila en Google Sheets donde se encuentra la factura (relacionado al mes).
    :return: ID del subfolder donde se subió la factura o None si hubo error.
    """

    # Primero verificamos si el número de celular es trae el prefijo colombiano
    patron = r'^57\d{10}$'
    if re.match(patron, cellphone):
        # Si trae el prefijo, nos quedamos solo con parte del número
        cellphone = cellphone[2:]


    # Primero obtenemos el ID del subfolder correspondiente al número de celular
    folder_id = get_subfolder_id(service_drive, main_folder_id, cellphone)

    if not folder_id:
        logger.warning("No se encontró un subfolder para el número de celular %s.", cellphone)
        return None

    # Obtenemos la cantidad de archivos en el folder
    # row_id = get_quantity_files_in_folder_id(service_drive, folder_id)
    # Definimos el nombre del archivo
    file_name = f"{row_id}. {invoice_id}.{'pdf' if flag_pdf else 'jpg'}"

    if flag_pdf:
        # Subimos el PDF al subfolder
        if pdf_path:
            upload_pdf_to_drive(service_drive, pdf_path, file_name, folder_id)
        else:
            logger.warning("No se proporcionó la ruta del archivo PDF.")
            return None
    else:
        # Subimos la imagen en bytes al subfolder
        if image_bytes:
            upload_image_to_drive(service_drive, image_bytes, file_name, folder_id)
        else:
            logger.warning("No se proporcionaron los bytes de la imagen.")
            return None

    return folder_id


# Función para el evento mensual de crear las nuevas carpetas de mes en cada subfolder
def create_monthly_folders(service_drive, main_folder_id: str):
    """
    Crea carpetas para cada mes en el subfolder correspondiente.
    :param service_drive: Objeto de servicio de Google Drive.
    :param main_folder_id: ID de la carpeta principal donde se encuentran los subfolders.
    """

    current_month = months_spanish[time.strftime("%B", time.localtime())].upper()
    current_year = time.strftime("%Y", time.localtime())
    folder_name_base = f"{current_month} {current_year}"
    # Obtenemos la lista de subfolders
    query = f"'{main_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed = false"
    response = service_drive.files().list(q=query, spaces='drive', fields='files(id, name)').execute().get('files', [])

    for subfolder in response:
        # Obtenemos el ID del subfolder
        subfolder_id = subfolder.get('id')

        # Contamos cantidad de carpetas existentes
        num_folders = get_quantity_folders_in_folder_id(service_drive, subfolder_id)
        folder_name = f"{num_folders + 1}. {folder_name_base}"

        # Creamos ahora el folder del mes
        create_folder_in_drive(service_drive, subfolder_id, folder_name)

        logger.info("Carpeta creada '%s' exitosamente para %s", folder_name, subfolder.get('name'))


# Función para crear carpeta de nuevo empleado
def create_employee_folder(service_drive, main_folder_id: str, cellphone: str, sheet_name: str) -> str:
    """
    Crea una carpeta para un nuevo empleado en Google Drive.
    :param service_drive: Objeto de servicio de Google Drive.
    :param main_folder_id: ID de la carpeta principal donde se crearán las carpetas de empleados.
    :param cellphone: Número de celular del empleado.
    :param sheet_name: Nombre de la hoja de cálculo donde se almacenará la información del empleado.
    :return: ID de la carpeta creada o None si hubo error.
    """

    try:
        # Primero verificamos si el número de celular es trae el prefijo colombiano
        patron = r'^57\d{10}$'
        if re.match(patron, cellphone):
            # Si trae el prefijo, nos quedamos solo con parte del número
            cellphone = cellphone[2:]

        # Ahora verificamos si ya existe una carpeta con ese número de celular
        query = f"'{main_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed = false and name contains '{cellphone}'"
        response = service_drive.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        existing_folders = response.get('files', [])
        if existing_folders:
            return f"Ya existe una carpeta para el número de celular {cellphone}. COMANDO TERMINADO"

        num_folders = get_quantity_folders_in_folder_id(service_drive, main_folder_id)
        # Extraemos el nombre de la hoja, para crear el nombre completo de la nueva carpeta
        match = re.match(r"^(.*?)(?:\s+\d+)?\s*$", sheet_name)
        if match:
            # NOTE: Aquí no se suma 1, porque la carpeta 'DESCONOCIDOS' no tiene numeración
            folder_name = f"{num_folders}.{match.group(1).strip().title()}_{cellphone}"
        else:
            folder_name = f"{num_folders}.{sheet_name}"


        # Creamos la carpeta del empleado
        folder_id = create_folder_in_drive(service_drive, main_folder_id, folder_name)

        # Ahora creamos la carpeta con el mes
        current_month = months_spanish[time.strftime("%B", time.localtime())].upper()
        current_year = time.strftime("%Y", time.localtime())
        month_folder_name = f"1. {current_month} {current_year}"
        folder_id = create_folder_in_drive(service_drive, folder_id, month_folder_name)

        if folder_id:
            return f"Carpeta creada exitosamente para el número de celular {cellphone}. 📂"
        else:
            return f"Error al crear la carpeta para el número de celular {cellphone}. ❌"

    except Exception as e:
        # Obtenemos la hora y fecha actual
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.error("%s: Error inesperado: %s", current_datetime, e)
        return "Ocurrió un error inesperado, será mejor reportarlo 🤒"
