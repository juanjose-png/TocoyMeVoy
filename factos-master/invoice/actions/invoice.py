import os
import zipfile
from django.http import HttpResponse
from django.utils import timezone
from invoice.utils import (
    send_invoice, store_invoice,
    tasks as invoice_tasks
)



def get_zip_files_downloaded(self, request, invoice_query):
    """
    Download ZIP files from the selected NextDownload objects.
    """
    if not invoice_query.exists():
        return self.message_user(request, "No hay registros seleccionados.", level='error')
    
    zip_files = []
    for invoice in invoice_query:
        if invoice.invoice_pdf:
            zip_files.append(invoice.invoice_pdf.path)
    
    # Create zip with timestamp in the filename and total files count
    total_files = f"{len(zip_files)}_{invoice_query.count()}"
    file_name = f"invoices-{timezone.now().strftime('%Y%m%d_%H%M%S')}-{total_files}.zip"

    # Create the zip file response
    response = HttpResponse(content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{file_name}"'
    with zipfile.ZipFile(response, 'w') as zip_file:
        for file_path in zip_files:
            zip_file.write(file_path, os.path.basename(file_path))
    return response


def extract_invoice_data(self, request, invoice_query):
    """
    Store products and PDF files from the selected NextDownload objects.
    """
    if not invoice_query.exists():
        return self.message_user(request, "No hay registros seleccionados.", level='error')

    next_download_obj, invoice_query_processed = store_invoice.extract_invoice_data(invoice_query=invoice_query)

    if not invoice_query_processed.exists():
        return self.message_user(request, "No se encontraron archivos PDF o XML para procesar.", level='error')
    
    invoices_processed_ids = list(invoice_query_processed.values_list('id', flat=True))
    self.message_user(
        request,
        f"Se han procesado {len(invoices_processed_ids)} registros correctamente.",
        level='success'
    )
    for invoice_id in invoices_processed_ids:
        self.message_user(
            request,
            f"Invoice ID: {invoice_id}",
            level='success'
        )
    return next_download_obj, invoice_query_processed
    

def register_in_odoo(self, request, invoice_query):
    """
    Register the invoices in Odoo from the selected Invoice objects using Celery.
    """
    if not invoice_query.exists():
        return self.message_user(request, "No hay registros seleccionados.", level='error')

    invoice_ids = list(invoice_query.values_list('id', flat=True))

    # Trigger Celery task
    task = invoice_tasks.register_invoices_in_odoo.delay(invoice_ids)

    self.message_user(
        request,
        f"Tarea de registro en Odoo iniciada para {len(invoice_ids)} facturas. Task ID: {task.id}",
        level='success'
    )

    self.message_user(
        request,
        f"La tarea se está ejecutando en segundo plano. Puedes verificar el progreso en los logs.",
        level='info'
    )

    return task


def process_single_invoice_with_ai(self, request, invoice_query):
    """
    Process selected invoices with AI to extract data from PDFs using Celery.
    """
    if not invoice_query.exists():
        return self.message_user(request, "No hay registros seleccionados.", level='error')

    invoice_ids = list(invoice_query.values_list('id', flat=True))

    # Trigger Celery task
    task = invoice_tasks.process_invoices_with_ai.delay(invoice_ids)

    self.message_user(
        request,
        f"Tarea de procesamiento con AI iniciada para {len(invoice_ids)} facturas. Task ID: {task.id}",
        level='success'
    )

    self.message_user(
        request,
        f"La tarea se está ejecutando en segundo plano. Puedes verificar el progreso en los logs.",
        level='info'
    )

    return task