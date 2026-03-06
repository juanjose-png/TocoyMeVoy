from core.services.google_sheets import (get_sheets_service,
                                         update_cellphones_sheets_json)
import os
from dotenv import load_dotenv
import time

load_dotenv()


# Inicializamos el servicio de Google Sheets
service_sheet = None
while service_sheet is None:
    service_sheet = get_sheets_service()
    if service_sheet is None:
        print("No se pudo inicializar el servicio de Google Sheets. Reintentando en 5 segundos...")
        time.sleep(5)

sheet_id = os.getenv("SHEET_ID")


update_cellphones_sheets_json(service_sheet, sheet_id)