import logging
import re

logger = logging.getLogger(__name__)


def get_sheet_name_from_db(cellphone: str) -> str:
    """Resuelve número de celular → nombre de hoja leyendo la tabla Employee.

    Acepta el número con o sin prefijo colombiano (57XXXXXXXXXX o XXXXXXXXXX).
    Retorna 'DESCONOCIDOS' si no se encuentra o si el empleado está inactivo.
    """
    from core.models import Employee  # import local para evitar circular imports

    # Normalizar: quitar prefijo "57" si viene con él
    match = re.match(r'^57(\d{10})$', cellphone)
    if match:
        cellphone = match.group(1)

    try:
        employee = Employee.objects.get(cellphone=cellphone, is_active=True)
        return employee.sheet_name
    except Employee.DoesNotExist:
        logger.warning("Celular %s no encontrado en DB. Asignando DESCONOCIDOS.", cellphone)
        return "DESCONOCIDOS"
    except Exception as e:
        logger.error("Error buscando celular %s en DB: %s", cellphone, e)
        return "DESCONOCIDOS"
