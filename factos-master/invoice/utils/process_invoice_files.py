import os
import tempfile
import shutil
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
from django.core.files import File
from invoice.utils.format_xml_invoice_document import FormatXMLDocument

def get_content_from_zip(zip_path: str) -> dict[str, str | None]:
    # Función para extraer el contenido de un archivo ZIP y devolver las rutas de los archivos extraídos

    # Crear un directorio con el mismo nombre del archivo ZIP (sin extensión)
    output_dir = os.path.splitext(zip_path)[0]
    os.makedirs(output_dir, exist_ok=True)

    # Extraer todos los archivos del ZIP al directorio creado
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(output_dir)

    content_files: dict[str, str | None] = {
        'output_dir': output_dir,
        'xml_file': None,
        'pdf_file': None,
    }
    # The structure of content_files is:
    # - *.pdf
    # - *.xml

    # Get the xml file
    for file_name in os.listdir(output_dir):
        if file_name.endswith('.xml'):
            content_files['xml_file'] = os.path.join(output_dir, file_name)
        elif file_name.endswith('.pdf'):
            content_files['pdf_file'] = os.path.join(output_dir, file_name)
    
    return content_files


def transform_file_to_csv(xml_path: str) -> str:
    # Función para leer un XML de factura electrónica DIAN y exportarlo a un CSV, limpiando campos vacíos y extrayendo todos los datos necesarios
    tree = ET.parse(xml_path)
    root = tree.getroot()

    ns = {
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
    }

    description_node = root.find('.//cbc:Description', namespaces=ns)

    try:
        inner_root = ET.fromstring(description_node.text) if description_node and description_node.text else root
    except ET.ParseError:
        inner_root = root

    def safe_findtext(element, path, namespaces=None, default_message="no encontrado"):
        found = element.findtext(path, namespaces=namespaces)
        return found.strip() if found and found.strip() not in ["0", ""] else default_message
    
    def clean_purchase_order(found_orden_compra):
        if found_orden_compra and type(found_orden_compra) is not str:
            text = found_orden_compra.text
        else:
            text = found_orden_compra
        

        # Solo se debe extraer el formato P seguido de números. Si tiene otros caracteres se debe limpiar
        purchase_order_code_list = list(text)
        purchase_order_code = ""
        for char in purchase_order_code_list:
            if char.isdigit() or char == 'P':
                purchase_order_code += char
            else:
                break
        return purchase_order_code.strip() if purchase_order_code else text

    def safe_find(element, path, namespaces=None, attribute=None, default_message="no encontrado"):
        found = element.find(path, namespaces=namespaces)
        if found is not None:
            value = found.attrib.get(attribute) if attribute else found.text
            return value.strip() if value and value.strip() not in ["0", ""] else default_message
        return default_message

    def to_numeric(value):
        try:
            return float(value.replace(",", ""))
        except (ValueError, AttributeError):
            return value

    def safe_observaciones(element, path, namespaces, default_message="no encontrado"):
        observaciones = element.find(path, namespaces=namespaces)
        if observaciones is not None and observaciones.text is not None and observaciones.text.strip() not in ["0", ""]:
            return observaciones.text.strip()
        return default_message

    def validate_nit(nit_value):
        if nit_value.isdigit():
            return nit_value
        else:
            return "NIT inválido"

    datos_generales = {
        'NumeroFactura': safe_findtext(inner_root, 'cbc:ID', ns),
        'FechaEmision': safe_findtext(inner_root, 'cbc:IssueDate', ns),
        'HoraEmision': safe_findtext(inner_root, 'cbc:IssueTime', ns),
        'FechaVencimiento': safe_findtext(inner_root, 'cbc:DueDate', ns),
        'Moneda': safe_findtext(inner_root, 'cbc:DocumentCurrencyCode', ns),
        'Subtotal': to_numeric(safe_findtext(inner_root, 'cac:LegalMonetaryTotal/cbc:LineExtensionAmount', ns)),
        'TotalImpuestos': to_numeric(safe_findtext(inner_root, 'cac:TaxTotal/cbc:TaxAmount', ns)),
        'TotalFactura': to_numeric(safe_findtext(inner_root, 'cac:LegalMonetaryTotal/cbc:PayableAmount', ns)),
        'Observaciones': safe_observaciones(inner_root, 'cbc:Note', ns)
    }

    proveedor_path = 'cac:AccountingSupplierParty/cac:Party'
    datos_proveedor = {
        'ProveedorNombre': safe_findtext(inner_root, f'{proveedor_path}/cac:PartyName/cbc:Name', ns),
        'ProveedorNIT': safe_findtext(inner_root, f'{proveedor_path}/cac:PartyIdentification/cbc:ID', ns),
        'ProveedorCorreo': safe_findtext(inner_root, f'{proveedor_path}/cac:Contact/cbc:ElectronicMail', ns),
    }

    # Buscar NIT real del proveedor en CompanyID si existe
    company_id = inner_root.find(f'{proveedor_path}/cac:PartyLegalEntity/cbc:CompanyID', namespaces=ns)
    if company_id is not None and company_id.text and company_id.text.strip() not in ["0", ""]:
        datos_proveedor['ProveedorNIT'] = validate_nit(company_id.text.strip())
    else:
        datos_proveedor['ProveedorNIT'] = validate_nit(datos_proveedor['ProveedorNIT'])

    # Obtener la orden de compra
    found_orden_compra = safe_findtext(inner_root, 'cac:OrderReference/cbc:ID', ns)
    orden_compra = {'OrdenCompra': clean_purchase_order(found_orden_compra)}

    datos_adicionales = {}
    for dato in inner_root.findall('.//DatoAdicional'):
        nombre = dato.attrib.get('name', '')
        valor = dato.text.strip() if dato.text and dato.text.strip() not in ["0", ""] else None
        if valor:
            datos_adicionales[nombre] = valor

    lineas = []

    for linea in inner_root.findall('cac:InvoiceLine', namespaces=ns):
        detalle = {
            'LineaID': safe_findtext(linea, 'cbc:ID', ns),
            'Cantidad': to_numeric(safe_findtext(linea, 'cbc:InvoicedQuantity', ns)),
            'Unidad': safe_find(linea, 'cbc:InvoicedQuantity', ns, attribute='unitCode'),
            'ValorTotalLinea': to_numeric(safe_findtext(linea, 'cbc:LineExtensionAmount', ns)),
            'DescripcionItem': safe_findtext(linea, 'cac:Item/cbc:Description', ns),
            'CodigoItem': safe_findtext(linea, 'cac:Item/cac:SellersItemIdentification/cbc:ID', ns),
            'PrecioUnitario': to_numeric(safe_findtext(linea, 'cac:Price/cbc:PriceAmount', ns)),
            'IVA_Linea': to_numeric(safe_findtext(linea, 'cac:TaxTotal/cbc:TaxAmount', ns)),
            'DescuentoLinea': to_numeric(safe_findtext(linea, 'cac:AllowanceCharge/cbc:Amount', ns))
        }

        detalle.update(datos_generales)
        detalle.update(datos_proveedor)
        detalle.update(orden_compra)
        detalle.update(datos_adicionales)
        lineas.append(detalle)

    df = pd.DataFrame(lineas)

    columnas_principales = [
        'NumeroFactura', 'FechaEmision', 'HoraEmision', 'FechaVencimiento', 'OrdenCompra', 'Moneda',
        'Subtotal', 'TotalImpuestos', 'TotalFactura', 'Observaciones',
        'ProveedorNombre', 'ProveedorNIT', 'ProveedorCorreo',
        'LineaID', 'Cantidad', 'Unidad', 'DescripcionItem', 'CodigoItem', 'PrecioUnitario', 'ValorTotalLinea', 'IVA_Linea', 'DescuentoLinea'
    ]
    columnas_final = columnas_principales + [col for col in df.columns if col not in columnas_principales]
    df = df[columnas_final]


    # Create CSV path
    csv_path = xml_path.replace('.xml', '.csv')
    # Save DataFrame to CSV
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')

    print(f"Archivo CSV generado exitosamente en: {csv_path}")

    return csv_path


def transform_file_to_csv_fake(xml_path):
    csv_path = xml_path.replace('.xml', '.csv')
    # Save DataFrame to CSV
    df = pd.DataFrame([{
        'NumeroFactura': '123456',
        'FechaEmision': '2023-01-01',
        'HoraEmision': '12:00:00',
        'FechaVencimiento': '2023-01-02',
        'OrdenCompra': 'OC123456',
        'Moneda': 'COP',
        'Subtotal': 100000,
        'TotalImpuestos': 19000,
        'TotalFactura': 119000,
        'Observaciones': 'N/A',
        'ProveedorNombre': 'Proveedor S.A.S',
        'ProveedorNIT': '123456789',
        'ProveedorCorreo': 'abc@example.com',
        'LineaID': '1',
        'Cantidad': 1,
        'Unidad': 'NIU',
        'DescripcionItem': 'Producto A',
        'CodigoItem': 'PROD001',
        'PrecioUnitario': 100000,
        'ValorTotalLinea': 100000,
        'IVA_Linea': 19000,
        'DescuentoLinea': 0
    }])
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"Archivo CSV generado exitosamente en: {csv_path}")
    return csv_path

def process_and_modify_invoice_xml(invoice_obj):
    """
    Processes an Invoice object, modifies its XML and updates the object with the modified ZIP.
    
    Args:
        invoice_obj: Django Invoice object with invoice_file (ZIP)
    
    Returns:
        Invoice: Updated object with modified ZIP
    """
    if not invoice_obj.invoice_file:
        raise ValueError("Invoice object must have an invoice_file (ZIP)")
    
    # Create temporary file from Django FileField
    temp_zip_path = None
    try:
        # Create temporary file for the original ZIP
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            temp_zip_path = temp_file.name
            
            # Copy content from Django FileField to temporary file
            invoice_obj.invoice_file.seek(0)
            temp_file.write(invoice_obj.invoice_file.read())
            temp_file.flush()
        
        # 1. Extract content from ZIP
        content_files = get_content_from_zip(temp_zip_path)
        xml_file_path = content_files.get('xml_file')
        pdf_file_path = content_files.get('pdf_file')
        output_dir = content_files.get('output_dir')
        
        if not xml_file_path:
            raise ValueError(f"No XML file found in ZIP: {invoice_obj.invoice_file.name}")
        
        # 2. Modify the XML object using the FormatXMLDocument
        format_xml_document = FormatXMLDocument()
        format_xml_document.process_invoice_xml(xml_file_path)
        
        # 3. Create new ZIP with the modified XML
        modified_zip_path = temp_zip_path.replace('.zip', '_modified.zip')
        
        with zipfile.ZipFile(modified_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            # Add modified XML
            xml_filename = os.path.basename(xml_file_path)
            zip_ref.write(xml_file_path, xml_filename)
            
            # Add PDF if it exists
            if pdf_file_path and os.path.exists(pdf_file_path):
                pdf_filename = os.path.basename(pdf_file_path)
                zip_ref.write(pdf_file_path, pdf_filename)
        
        # 4. Update Invoice object with modified ZIP
        with open(modified_zip_path, 'rb') as modified_file:
            original_name = invoice_obj.invoice_file.name
            # Remove path before the last "/" if it exists
            if '/' in original_name:
                original_name = original_name.split('/')[-1]
            modified_name = original_name.replace('.zip', '_modified.zip')
            
            # Create Django File object and save to Invoice
            django_file = File(modified_file, name=os.path.basename(modified_name))
            invoice_obj.invoice_file.save(modified_name, django_file, save=True)
        
        # 5. Clean up temporary directories and files
        if output_dir and os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        
        if os.path.exists(modified_zip_path):
            os.unlink(modified_zip_path)
            
        return invoice_obj
        
    finally:
        # Clean up temporary original ZIP file
        if temp_zip_path and os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)


