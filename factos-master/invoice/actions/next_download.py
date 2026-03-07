from invoice.utils import (
    send_invoice, store_invoice,
    tasks as invoice_tasks
)



def download_invoices(self, request, next_download_query):
    for next_download_obj in next_download_query:
        celery_task_obj = invoice_tasks.read_and_process_invoice.delay(next_download_id=next_download_obj.id)

        self.message_user(
            request, 
            f"Se ha iniciado el proceso de descarga de facturas: Task[{celery_task_obj.id}] - NextDownloadID[{next_download_obj.id}]",
            level='success'
        )


def extract_invoice_data(self, request, next_download_query):

    invoices_processed_ids = []
    invoice_with_error_ids = []
    for next_download_obj in next_download_query:
        try:
            next_download_obj, invoice_query_processed = store_invoice.extract_invoice_data(next_download_obj)
            invoices_processed_ids.append({
                'next_download_id': next_download_obj.id,
                'invoices_processed': str(list(invoice_query_processed.values_list('id', flat=True))),
            })
        except Exception as e:
            invoice_with_error_ids.append({
                'next_download_id': next_download_obj.id,
                'error': str(e),
            })
            continue

    self.message_user(request, 
                      f"Se han procesado {len(invoices_processed_ids)} registros correctamente.",
                      level='success')
    
    if invoices_processed_ids:
        for processed in invoices_processed_ids:
            self.message_user(request, 
                              f"NextDownload ID: {processed['next_download_id']} - Invoice IDs: {processed['invoices_processed']}",
                              level='success')


    if invoice_with_error_ids:
        self.message_user(request, 
                          f"Se han encontrado errores en {len(invoice_with_error_ids)} registros.",
                          level='error')
        for error in invoice_with_error_ids:
            self.message_user(request, 
                              f"NextDownload ID: {error['next_download_id']} - Invoice IDs: {error['error']}",
                              level='error')
            

def register_in_odoo(self, request, next_download_query):
    invoices_registered_ids = []
    invoice_with_error_ids = []
    for next_download_obj in next_download_query:
        try:
            next_download_obj, invoice_query_sent = send_invoice.odoo(next_download_obj)
            invoices_registered = invoice_query_sent.values_list('id', flat=True)
            invoices_registered_ids.append({
                'next_download_id': next_download_obj.id,
                'invoices_registered': str(list(invoices_registered)),
            })
        except Exception as e:
            invoice_with_error_ids.append({
                'next_download_id': next_download_obj.id,
                'error': str(e),
            })
            continue
    
    if invoices_registered_ids:
        self.message_user(request, 
                        f"Se han registrado {len(invoices_registered_ids)} registros en Odoo correctamente.",
                        level='success')
        for registered in invoices_registered_ids:
            self.message_user(request, 
                              f"NextDownload ID: {registered['next_download_id']} - Invoice IDs: {registered['invoices_registered']}",
                              level='success')

    if invoice_with_error_ids:
        self.message_user(request, 
                          f"Se han encontrado errores en {len(invoice_with_error_ids)} registros.",
                          level='error')
        for error in invoice_with_error_ids:
            self.message_user(request, 
                              f"NextDownload ID: {error['next_download_id']} - Error: {error['error']}",
                              level='error')