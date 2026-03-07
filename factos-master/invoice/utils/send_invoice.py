from invoice.odoo import support_document
from invoice import models as invoice_models
from elastic_logging.logger import elastic_logger



def odoo(next_download_obj=None, invoice_query_processed=None):
    elastic_logger.info("Starting Odoo invoice registration process")

    if next_download_obj and not invoice_query_processed:
        invoice_query_processed = invoice_models.Invoice.objects.filter(
            next_download=next_download_obj,
            invoice_processed__isnull=False,
            registered_in_odoo=False,
        ).order_by('-created_at')
    elif not next_download_obj and invoice_query_processed:
        invoice_obj = invoice_query_processed.first()
        next_download_obj = invoice_obj.next_download
    elif not next_download_obj and not invoice_query_processed:
        raise ValueError("Either next_download_obj or invoice_query_processed must be provided.")
    
    if not invoice_query_processed.exists():
        elastic_logger.warning("No invoices found to process for Odoo registration")
        raise ValueError("No invoices found to process for Odoo registration.")

    elastic_logger.info(f"Found {invoice_query_processed.count()} invoices to register in Odoo")

    # Process the CSV files and upload to Odoo
    processed_count = 0
    total_count = invoice_query_processed.count()
    for idx, invoice_obj_j in enumerate(invoice_query_processed, 1):
        invoice_id = invoice_obj_j.invoice_number or f"ID-{invoice_obj_j.pk}"
        elastic_logger.info(f"Registering invoice {idx}/{total_count} in Odoo: {invoice_id}")

        osd_class_obj = support_document.OdooSupportDocument.create(
            invoice_obj=invoice_obj_j,
        )
        success = osd_class_obj.create_invoice()

        if success:
            processed_count += 1
            elastic_logger.info(f"Successfully registered invoice {invoice_id} in Odoo")
        else:
            elastic_logger.warning(f"Failed to register invoice {invoice_id} in Odoo")

    # Check if all files have been processed
    invoice_query_sent = invoice_query_processed.filter(registered_in_odoo=True)
    total_invoices = invoice_query_processed.count()
    registered_invoices = invoice_query_sent.count()

    elastic_logger.info(f"Odoo registration completed: {registered_invoices}/{total_invoices} invoices registered")

    if total_invoices == registered_invoices:
        # All files have been processed
        next_download_obj.invoices_registered = True
        next_download_obj.save()
        elastic_logger.info(f"All invoices registered successfully for next_download: {next_download_obj.id}")
    else:
        elastic_logger.warning(f"Not all invoices registered: {registered_invoices}/{total_invoices} for next_download: {next_download_obj.id}")

    return next_download_obj, invoice_query_sent