import json
import os
import logging
from datetime import datetime
from django.conf import settings
from core.services.google_sheets import get_sheets_service, write_data

logger = logging.getLogger(__name__)

class PettyFlowService:
    @staticmethod
    def check_request_day():
        """
        Validates if the current day is Monday (0) or Tuesday (1).
        Returns a dictionary with 'warning' status and a 'message'.
        """
        day = datetime.now().weekday()
        if day not in [0, 1]:
            return {
                'warning': True,
                'message': "🤖 *Bot PettyFlow:* Veo que te gusta vivir al límite solicitando recargas fuera de Lunes/Martes. Lo registraré, pero mi circuito de sarcasmo está activo. 😉"
            }
        return {'warning': False, 'message': ""}

    @staticmethod
    def validate_budget(employee_name, amount_requested):
        """
        Validates the requested amount against budget limits in presupuestos_iniciales.json.
        """
        # Note: The path depends on where the file is actually located in the project.
        # Based on Odoo code, it was in ../../.agent/data/presupuestos_iniciales.json
        # In this project, let's assume it's in the root or a known data directory.
        data_path = os.path.join(settings.BASE_DIR, '..', '.agent', 'data', 'presupuestos_iniciales.json')
        
        if not os.path.exists(data_path):
            logger.warning(f"Budget file not found at {data_path}")
            return True, ""

        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            limit_data = next((item for item in data if item['tarjeta'].lower() == employee_name.lower()), None)
            
            if limit_data:
                budget_limit = limit_data.get('monto_por_recarga')
                if isinstance(budget_limit, (int, float)) and float(amount_requested) > budget_limit:
                    return False, f"El monto solicitado (${amount_requested}) supera el estándar permitido para esta tarjeta (${budget_limit})."
                
                if limit_data.get('cupo_mensual') == "Pendiente de aprobación manual":
                    return True, "ATENCIÓN: Este perfil requiere validación manual de cupo (Visitador)."
        except Exception as e:
            logger.error(f"Error validating budget: {e}")
            
        return True, ""

    @staticmethod
    def sync_to_google_sheets(petty_reload):
        """
        Synchronizes the reload request to the 'RECARGAS' sheet of the main spreadsheet.
        """
        try:
            service = get_sheets_service()
            if not service:
                raise Exception("Could not initialize Google Sheets service.")

            # Main Spreadsheet ID - should be in settings or constants
            # Using a placeholder for now as it's not explicitly clear which ID to use
            # but usually it's passed or stored in some config.
            spreadsheet_id = os.getenv("MAIN_SPREADSHEET_ID", "REPLACE_WITH_ACTUAL_ID")
            
            sheet_name = "RECARGAS"
            
            # Prepare data row
            # Format: [Referencia, Fecha, Empleado, Monto, Estado, Observaciones]
            row_data = [
                petty_reload.reference,
                petty_reload.date_request.strftime("%Y-%m-%d %H:%M:%S"),
                petty_reload.employee.sheet_name,
                float(petty_reload.amount_requested),
                petty_reload.get_state_display(),
                petty_reload.observations
            ]
            
            # Append data (this logic might need adjustment based on how write_data works)
            # Find last row or use append? core/services/google_sheets.py has custom logic
            # Let's use a simple approach for now or follow existing patterns
            # Actually, google_sheets.py has insert_values_in_sheet but it's specific to invoices.
            
            # Simple append logic for Google Sheets API v4
            range_name = f"{sheet_name}!A:F"
            service.values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                body={"values": [row_data]}
            ).execute()
            
            logger.info(f"Successfully synced PettyReload {petty_reload.reference} to Sheets.")
            return True
        except Exception as e:
            logger.error(f"Error syncing to Google Sheets: {e}")
            return False

    @staticmethod
    def notify_discord_visitador(employee_name, amount):
        """
        Placeholder for Discord notification if the employee is a visitador.
        """
        visitadores = ['Mauro Madera', 'Milton Arcos', 'Julio Cesar', 'Benjamin Juli Owen', 'Bayron Cajica', 'Derwin Urdaneta']
        if employee_name in visitadores:
            msg = f"🔔 **Solicitud de Visitador** | @AlanM, el visitador **{employee_name}** ha solicitado una recarga por ${amount}. Requiere tu aprobación previa."
            # Integration logic here (e.g., via webhook)
            logger.info(f"Discord notification: {msg}")
            return True
        return False
