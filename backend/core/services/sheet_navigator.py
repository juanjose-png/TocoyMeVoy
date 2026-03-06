import logging
import re
from core.services.google_sheets import get_visible_sheets_names, read_data, get_cell_background_color

logger = logging.getLogger(__name__)

def get_cards_list(service_sheet, sheet_id: str) -> list[dict]:
    """
    Retorna la lista de todas las hojas visibles (tarjetas) con metadata.
    Cada dict contiene:
      - 'sheet_name' : nombre de la pestaña (ej. 'JULIAN 2025')
      - 'card_label' : nombre recortado para mostrar en UI (sin el año)
      - 'leader'     : nombre del líder leído de la celda K8 o L8
    """
    sheets = get_visible_sheets_names(service_sheet, sheet_id)
    cards = []
    for sheet_name in sheets:
        # Leer celdas K8:L8 para obtener el número de celular y/o nombre de líder
        meta = read_data(service_sheet, sheet_id, sheet_name, "K8:L8")
        leader = ""
        if meta and meta[0]:
            # La celda puede tener el nombre del líder en L8 y celular en K8
            leader = meta[0][1] if len(meta[0]) > 1 else meta[0][0]

        # card_label: extraer solo la parte del nombre sin año
        label_match = re.match(r"^(.*?)(?:\s+\d{4})?$", sheet_name)
        card_label = label_match.group(1).strip() if label_match else sheet_name

        cards.append({
            "sheet_name": sheet_name,
            "card_label": card_label,
            "leader": leader,
        })
    return cards

def get_months_in_sheet(service_sheet, sheet_id: str, sheet_name: str,
                        year_filter: int = None) -> list[dict]:
    """
    Retorna la lista de meses disponibles en la hoja, ordenados cronológicamente.
    Cada dict contiene:
      - 'month_label' : ej. 'ENERO 2025'
      - 'start_row'   : fila donde empieza el bloque de ese mes (rojo + 1)
      - 'end_row'     : fila donde termina (siguiente separador rojo - 1)
    """
    # Leer columna F desde fila 12 (Centro Costos en hojas normales)
    # o columna G en hojas especiales
    is_special = sheet_name in ('MANTENIMIENTO 2025', 'TRAB SOCIALES 2025')
    label_col = "G" if is_special else "F"
    data_range = f"A12:{label_col}"
    data = read_data(service_sheet, sheet_id, sheet_name, data_range)
    if not data:
        return []

    months = []
    label_col_idx = 6 if is_special else 5  # G=6, F=5 (0-based)

    for i, row in enumerate(data):
        row_num = i + 12
        # Leer color de la columna A para detectar separadores
        color = get_cell_background_color(service_sheet, sheet_id, sheet_name, f"A{row_num}")
        if color and color.get("red", 0) == 1 and color.get("green", 0) == 0:
            # Esta es una fila separadora de mes
            label = row[label_col_idx].strip() if len(row) > label_col_idx else ""
            if not label:
                continue
            if year_filter and str(year_filter) not in label:
                continue
            months.append({
                "month_label": label,
                "separator_row": row_num,
                "start_row": row_num + 1,
            })

    # Calcular end_row para cada mes
    for idx, m in enumerate(months):
        if idx + 1 < len(months):
            m["end_row"] = months[idx + 1]["separator_row"] - 1
        else:
            # Último mes: hasta la última fila con datos
            m["end_row"] = 11 + len(data)

    return months

def get_month_rows(service_sheet, sheet_id: str, sheet_name: str,
                   start_row: int, end_row: int) -> list[dict]:
    """
    Retorna las filas de datos de un mes específico listas para renderizar.
    Incluye los 4 campos de trazabilidad nuevos.
    Omite filas vacías y separadores.
    """
    is_special = sheet_name in ('MANTENIMIENTO 2025', 'TRAB SOCIALES 2025')
    # Después de la inserción de trazabilidad las columnas son:
    # Normales:  A B C D E F G H  I        J     K              L              M          N
    #            No Fecha Neg NIT Fac CC Conc Val URL_DRV CUFE CHK_DOC CHK_PAGO DIFER OBS
    # Especiales: A B C D E F G H I  J        K     L              M              N          O
    last_col = "O" if is_special else "N"
    data_range = f"A{start_row}:{last_col}{end_row}"
    data = read_data(service_sheet, sheet_id, sheet_name, data_range)
    if not data:
        return []

    rows = []
    for i, raw in enumerate(data):
        row_num = start_row + i
        # Rellenar hasta la longitud máxima esperada
        padded = (raw + [""] * 15)[:15]

        if is_special:
            row = {
                "no": padded[0], "fecha": padded[1], "responsable": padded[2],
                "nombre_negocio": padded[3], "nit": padded[4], "num_factura": padded[5],
                "centro_costos": padded[6], "concepto": padded[7], "valor_legalizado": padded[8],
                "url_drive": padded[9], "cufe": padded[10],
                "check_odoo_doc": padded[11], "check_odoo_pago": padded[12],
                "diferencia": padded[13], "observaciones": padded[14],
                "row_num": row_num,
            }
        else:
            row = {
                "no": padded[0], "fecha": padded[1], "nombre_negocio": padded[2],
                "nit": padded[3], "num_factura": padded[4], "centro_costos": padded[5],
                "concepto": padded[6], "valor_legalizado": padded[7],
                "url_drive": padded[8], "cufe": padded[9],
                "check_odoo_doc": padded[10], "check_odoo_pago": padded[11],
                "diferencia": padded[12], "observaciones": padded[13],
                "row_num": row_num,
            }

        # Omitir filas sin número de factura ni valor legalizado
        if not row["num_factura"] and not row["valor_legalizado"]:
            continue

        # Obtener color de la fila para respetar verde/amarillo en la UI
        color = get_cell_background_color(service_sheet, sheet_id, sheet_name, f"A{row_num}")
        row["row_bg_color"] = color  # dict con red/green/blue 0-1
        rows.append(row)

    return rows
