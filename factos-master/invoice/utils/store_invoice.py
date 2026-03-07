import os
import shutil
from django.core.files import File
from django.db.models import Q
from invoice import models as invoice_models
from invoice.utils import download_invoice_files, process_invoice_files, read_document
from elastic_logging.logger import elastic_logger


def process_single_invoice(invoice_obj: invoice_models.Invoice):
    """Process a single invoice by extracting data from PDF and saving to database"""
    # Process the zip file
    if not invoice_obj.invoice_pdf:
        elastic_logger.warning(f"No se encontró archivo PDF para factura {invoice_obj.invoice_number}")
        return False

    # Read the PDF file and process it with Google GenAI
    pdf_file_path = invoice_obj.invoice_pdf.path
    invoice_data = read_document.get_invoice_data(pdf_file_path)
    if not invoice_data:
        elastic_logger.warning(f"No se encontraron datos de factura en PDF {pdf_file_path}")
        return False

    # Save the general information of the invoice
    invoice_general_info = invoice_data.get("general_info", {})
    ## Clean date format DD/MM/YYYY to YYYY-MM-DD
    if invoice_general_info.get("issue_date"):
        original_date = invoice_general_info["issue_date"]
        invoice_general_info["issue_date"] = invoice_general_info["issue_date"].replace('/', '-')
        # Convert to YYYY-MM-DD format
        invoice_general_info["issue_date"] = '-'.join(invoice_general_info["issue_date"].split('-')[::-1])

    if invoice_general_info.get("due_date"):
        original_due_date = invoice_general_info["due_date"]
        invoice_general_info["due_date"] = invoice_general_info["due_date"].replace('/', '-')
        # Convert to YYYY-MM-DD format
        invoice_general_info["due_date"] = '-'.join(invoice_general_info["due_date"].split('-')[::-1])

    # Save the issuer information
    invoice_issuer_info = invoice_data.get("issuer_info", {})

    # Create a new Invoice object and save it
    invoice_obj.issuer_name = invoice_issuer_info.get("name") or "-"
    invoice_obj.issuer_nit = invoice_issuer_info.get("nit") or "-"
    invoice_obj.cufe = invoice_general_info.get("cufe") or "-"
    invoice_obj.issue_date = invoice_general_info.get("issue_date")
    invoice_obj.due_date = invoice_general_info.get("due_date")
    invoice_obj.order_number = invoice_general_info.get("order_number")
    invoice_obj.invoice_number = invoice_general_info.get("invoice_number")
    invoice_obj.save()

    # Rename the PDF file with invoice number
    invoice_obj.rename_invoice_pdf_file()

    elastic_logger.info(f"Factura {invoice_obj.invoice_number} procesada con datos completos")

    # Read products from the invoice data
    products = invoice_data.get("products", [])
    elastic_logger.info(f"Processing {len(products)} products for invoice {invoice_obj.invoice_number}")

    for product_idx, product in enumerate(products, 1):
        # Clear float values to avoid issues with commas and dots
        for k, v in product.items():
            # Handle float fields
            float_quantity_fields = [
                "Cantidad",
                "Precio unitario",
                "Descuento detalle",
                "Recargo detalle",
                "IVA",
                "INC",
                "Precio unitario de venta",
            ]
            ## Replace commas with dots for float conversion
            ## i.e. "1.233,00" -> "1233.00"
            if k in float_quantity_fields:
                product[k] = (v or "0").replace('.', '').replace(',', '.')
                # Convert to float if needed
                try:
                    product[k] = float(product[k])
                except ValueError:
                    product[k] = 0.0

            # Handle percentage fields
            # NOTE: Dont join to float fields because they are not float values
            percentage_fields = [
                "%_iva",
                "%_inc",
            ]
            ## Replace commas with dots for percentage conversion
            ## i.e. "19.00" -> "19.0"
            if k in percentage_fields:
                product[k] = v or "0"
                # Convert to float if needed
                try:
                    product[k] = float(product[k])
                except ValueError:
                    product[k] = 0.0

        # Create a new Product object and save it
        product_obj = invoice_models.Product(
            invoice=invoice_obj,
            code=product.get("Código") or "-",
            description=product.get("Descripción", ""),
            unit_measurement=product.get("U/M") or "-",
            quantity=product.get("Cantidad") or 0.0,
            unit_price=product.get("Precio unitario") or 0.0,
            discount_detail=product.get("Descuento detalle") or 0.0,
            surcharge_detail=product.get("Recargo detalle") or 0.0,
            iva=product.get("IVA") or 0.0,
            iva_percentage=product.get("%_iva") or 0.0,
            inc=product.get("INC") or 0.0,
            inc_percentage=product.get("%_inc") or 0.0,
            unit_sale_price=product.get("Precio unitario de venta") or 0.0,
        )
        product_obj.save()
        elastic_logger.info(f"Product {product_idx}/{len(products)} saved: {product_obj.code} for invoice {invoice_obj.invoice_number}")

    return True


def zip_file(next_download_obj) -> tuple:
    elastic_logger.info(f"Iniciando descarga de facturas para NextDownload {next_download_obj.pk}")

    navigate_to = "https://catalogo-vpfe.dian.gov.co/Document/Received"

    invoice_type_label = dict(invoice_models.NextDownload.InvoiceType.choices).get(next_download_obj.invoice_type, "Unknown")

    invoice_dir = f"invoice_{next_download_obj.pk}_{next_download_obj.from_date}_{next_download_obj.to_date}"  # Change this to the desired download directory

    download_dir = download_invoice_files.download(
        next_download_obj.dian_link,
        navigate_to,
        next_download_obj.from_date,
        next_download_obj.to_date,
        invoice_type_label,
        invoice_dir
    )
    
    # TODO: Implement this in the future into the download_invoice_files module
    if not download_dir:
        elastic_logger.error("Fallo en descarga de archivos ZIP desde DIAN")
        raise Exception("Download failed")
    
    # Iterate download_dir to save the files into the database
    zip_name_count = 0
    total_zip_files = sum(1 for root, dirs, files in os.walk(download_dir) for file in files if file.endswith(".zip"))
    elastic_logger.info(f"Iniciando procesamiento de {total_zip_files} archivos ZIP descargados")

    for root, dirs, files in os.walk(download_dir):
        for file in files:
            if file.endswith(".zip"):
                zip_file_path = os.path.join(root, file)
                elastic_logger.info(f"Procesando archivo ZIP {zip_name_count + 1}/{total_zip_files}: {file}")
                with open(zip_file_path, 'rb') as f:
                    # Save the file to the database
                    django_file_path = File(f, name=f"{zip_name_count}.zip")
                    invoice_obj = invoice_models.Invoice(
                        next_download=next_download_obj,
                        invoice_file=django_file_path,
                        invoice_type=next_download_obj.invoice_type
                    )
                    invoice_obj.save()
                # Get PDF and XML file from the zip
                content_files = process_invoice_files.get_content_from_zip(zip_file_path)
                pdf_file_path = content_files.get("pdf_file")

                if not pdf_file_path:
                    elastic_logger.warning(f"No se encontró archivo PDF en ZIP {zip_file_path}")
                    continue

                # Save the PDF file to the database
                with open(pdf_file_path, 'rb') as f:
                    django_pdf_file_path = File(f, name=f"{zip_name_count}.pdf")
                    invoice_obj.invoice_pdf = django_pdf_file_path
                    invoice_obj.save()

                # Process and modify XML inside the ZIP using the Invoice object
                try:
                    invoice_obj = process_invoice_files.process_and_modify_invoice_xml(invoice_obj)
                    elastic_logger.info(f"Factura {zip_name_count + 1}/{total_zip_files} procesada exitosamente - ID: {invoice_obj.pk}")
                except Exception as e:
                    elastic_logger.error(f"Error procesando XML para factura {invoice_obj.pk} ({zip_name_count + 1}/{total_zip_files}): {e}")
                    
                zip_name_count += 1

    invoice_query = invoice_models.Invoice.objects.filter(
        next_download=next_download_obj,
    ).order_by('-created_at')


    if not invoice_query.exists():
        return next_download_obj, None

    next_download_obj.invoices_downloaded = True
    next_download_obj.save()

    # Delete the download directory
    shutil.rmtree(download_dir)

    elastic_logger.info(f"Proceso de descarga completado: {invoice_query.count()} facturas descargadas")
    return next_download_obj, invoice_query


def extract_invoice_data(next_download_obj=None, invoice_query=None) -> tuple:
    # List of downloaded files
    if next_download_obj and not invoice_query:
        invoice_query = invoice_models.Invoice.objects.filter(
            next_download=next_download_obj,
        ).order_by('-created_at')

    elif not next_download_obj and invoice_query:
        invoice_obj = invoice_query.first()
        next_download_obj = invoice_obj.next_download
    elif not next_download_obj and not invoice_query:
        raise ValueError("Either next_download_obj or invoice_query must be provided.")

    if not invoice_query.exists():
        elastic_logger.warning("No se encontraron facturas para procesar")
        return next_download_obj, invoice_query

    elastic_logger.info(f"Iniciando extracción de datos para {invoice_query.count()} facturas")

    invoice_query = invoice_query.filter(
        Q(issuer_name__isnull=True) |
        Q(issuer_nit__isnull=True) |
        Q(cufe__isnull=True) |
        Q(issue_date__isnull=True) |
        Q(due_date__isnull=True) |
        Q(order_number__isnull=True) |
        Q(invoice_number__isnull=True)
    )


    for i, invoice_obj_i in enumerate(invoice_query):
        try:
            elastic_logger.info(f"Procesando factura {i + 1}/{invoice_query.count()}: {invoice_obj_i.invoice_number or 'Sin número'}")
            process_single_invoice(invoice_obj_i)
        except Exception as e:
            continue

    # Check if all files have been processed
    invoice_query_processed = invoice_query.filter(invoice_processed__isnull=False)
    total_processed = invoice_query_processed.count()
    total_files = invoice_query.count()
    if total_processed == total_files:
        # All files have been processed
        next_download_obj.invoices_processed = True
        next_download_obj.save()
        elastic_logger.info(f"Data extraction completed: {total_processed}/{total_files} invoices processed successfully")

    elastic_logger.info(f"Extracción de datos finalizada: {total_processed} facturas procesadas")
    return next_download_obj, invoice_query_processed
