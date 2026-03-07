from factos.celery import app
from invoice import models as invoice_models
from invoice.utils import send_invoice, store_invoice
from invoice.utils import process_dian_email
from elastic_logging.logger import elastic_logger
import json

@app.task(queue='invoice_processing')
def read_and_process_invoice(next_download_id: str=None):
    next_download_obj = invoice_models.NextDownload.objects.get(id=next_download_id)

    elastic_logger.info(f"Starting invoice processing workflow for NextDownload {next_download_id}")
    elastic_logger.info(f"Date range: {next_download_obj.from_date} to {next_download_obj.to_date}")

    # Start processing the invoices
    next_download_obj.processing_status = invoice_models.NextDownload.ProcessingStatus.IN_PROGRESS
    next_download_obj.save()

    task_result = {
        "next_download_id": next_download_obj.id, # type: ignore
        "invoice_downloaded": None,
        "invoices_processed": None,
        "invoices_registered": None,
        "message": "Invoices processed successfully."
    }

    # Call your function to save the link
    try:
        elastic_logger.info("Step 1/3: Starting ZIP file download and storage")
        next_download_obj, invoice_query = store_invoice.zip_file(next_download_obj)

        task_result["invoice_downloaded"] = list(invoice_query.values_list('id', flat=True))

        elastic_logger.info("Step 2/3: Starting invoice data extraction")
        next_download_obj, invoice_query_processed = store_invoice.extract_invoice_data(next_download_obj, invoice_query)

        task_result["invoices_processed"] = list(invoice_query_processed.values_list('id', flat=True))

        elastic_logger.info("Step 3/3: Starting Odoo registration")
        next_download_obj, invoice_query_sent = send_invoice.odoo(next_download_obj, invoice_query_processed)

        task_result["invoices_registered"] = list(invoice_query_sent.values_list('id', flat=True))

        # TODO: Notify the user about the invoices
        # next_download_obj.invoices_notification = True
        # next_download_obj.save()

        next_download_obj.processing_status = invoice_models.NextDownload.ProcessingStatus.COMPLETED
        next_download_obj.save()
        elastic_logger.info(f"Invoice processing workflow completed successfully for NextDownload {next_download_id}")

    except Exception as e:
        del task_result["message"]
        task_result["message"] = f"Error processing invoices: {str(e)}"
        task_result["error"] = str(e)
        raise Exception(json.dumps(task_result))
    
    return task_result


@app.task()
def search_and_get_dian_link(date_from: str = None, date_to: str = None) -> dict:
    """
    Celery task to search for a DIAN link in emails and return it.
    
    Args:
        date_from (str): Start date for filtering emails.
        date_to (str): End date for filtering emails.
        
    Returns:
        str: The DIAN link if found, otherwise an empty string.
    """
    # 1. Get a DIAN link from the emails
    dian_link = process_dian_email.search_and_get_dian_link(date_from=date_from, date_to=date_to)

    # 2. Get a NewtDownload object with the DIAN link
    next_download_obj = invoice_models.NextDownload.objects.filter(
        processing_status=invoice_models.NextDownload.ProcessingStatus.NOT_STARTED,
        invoices_downloaded=False,
        invoices_processed=False,
        invoices_registered=False,
        invoices_notification=False,
        dian_link=""
    ).order_by('created_at').first()

    # If no NextDownload object is found, raise an error
    if not next_download_obj:
        return {
            "dian_link": dian_link,
            "next_download_id": None,
            "result": "No NextDownload object found with the specified criteria."
        }
    
    if not dian_link:
        return {
            "dian_link": dian_link,
            "next_download_id": next_download_obj.id,
            "result": "No DIAN link found in the emails."
        }


    next_download_obj.dian_link = dian_link
    next_download_obj.save()

    return {
        "dian_link": dian_link,
        "next_download_id": next_download_obj.id,
        "result": "DIAN link found and NextDownload object updated."
    }


@app.task(queue='invoice_processing')
def process_invoices_with_ai(invoice_ids: list):
    """
    Process selected invoices with AI to extract data from PDFs.

    Args:
        invoice_ids (list): List of invoice IDs to process

    Returns:
        dict: Processing results with counts and details
    """
    elastic_logger.info(f"Starting AI processing for {len(invoice_ids)} invoices")

    processed_count = 0
    failed_count = 0
    processed_ids = []
    error_details = []

    for invoice_id in invoice_ids:
        try:
            invoice = invoice_models.Invoice.objects.get(id=invoice_id)
            elastic_logger.info(f"Processing invoice {invoice.invoice_number or invoice_id} with AI")

            success = store_invoice.process_single_invoice(invoice)
            if success:
                processed_count += 1
                processed_ids.append(invoice_id)
                elastic_logger.info(f"Successfully processed invoice {invoice.invoice_number or invoice_id}")
            else:
                failed_count += 1
                error_details.append(f"Invoice {invoice.invoice_number or invoice_id}: Processing returned False")
        except Exception as e:
            failed_count += 1
            error_msg = f"Invoice {invoice_id}: {str(e)}"
            error_details.append(error_msg)
            elastic_logger.error(f"Error processing invoice {invoice_id}: {str(e)}")

    result = {
        "processed_count": processed_count,
        "failed_count": failed_count,
        "processed_ids": processed_ids,
        "error_details": error_details,
        "message": f"AI processing completed: {processed_count} successful, {failed_count} failed"
    }

    elastic_logger.info(f"AI processing task completed: {result['message']}")
    return result


@app.task(queue='invoice_processing')
def register_invoices_in_odoo(invoice_ids: list):
    """
    Register selected invoices in Odoo.

    Args:
        invoice_ids (list): List of invoice IDs to register

    Returns:
        dict: Registration results with counts and details
    """
    elastic_logger.info(f"Starting Odoo registration for {len(invoice_ids)} invoices")

    # Create queryset from invoice IDs
    invoice_query = invoice_models.Invoice.objects.filter(id__in=invoice_ids)

    try:
        next_download_obj, invoice_query_sent = send_invoice.odoo(invoice_query_processed=invoice_query)

        registered_count = invoice_query_sent.count() if invoice_query_sent else 0
        failed_count = len(invoice_ids) - registered_count

        registered_ids = list(invoice_query_sent.values_list('id', flat=True)) if invoice_query_sent else []

        result = {
            "registered_count": registered_count,
            "failed_count": failed_count,
            "registered_ids": registered_ids,
            "next_download_id": next_download_obj.id if next_download_obj else None,
            "message": f"Odoo registration completed: {registered_count} successful, {failed_count} failed"
        }

        elastic_logger.info(f"Odoo registration task completed: {result['message']}")
        return result

    except Exception as e:
        error_msg = f"Error in Odoo registration: {str(e)}"
        elastic_logger.error(error_msg)
        return {
            "registered_count": 0,
            "failed_count": len(invoice_ids),
            "registered_ids": [],
            "next_download_id": None,
            "error": error_msg,
            "message": "Odoo registration failed"
        }