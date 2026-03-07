import os
from django.core.files.storage import default_storage
from django.db import models
from django.conf import settings

class AccountMove(models.Model):
    move_id = models.CharField(primary_key=True)
    invoice = models.ManyToManyField('Invoice')

class NextDownload(models.Model):
    """
    Model to track the next download time.
    """

    class InvoiceType(models.TextChoices):
        ELECTRONIC_INVOICE = "electronic_invoice", "Factura electronica de venta"
        RECEIVED_INVOICE = "received_invoice", "Recibidos"
        SENT_INVOICE = "sent_invoice", "Enviados"
        # NOTE: Add more invoice types as needed

    class ProcessingStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"


    dian_link = models.CharField(
        max_length=255,
        blank=True,
        help_text="Link received from the DIAN into the email",
    )
    from_date = models.DateField(
        help_text="Date from which the invoice will be downloaded",
    )
    to_date = models.DateField(
        help_text="Date until which the invoice will be downloaded",
    )
    invoice_type = models.CharField(
        max_length=50,
        default=InvoiceType.ELECTRONIC_INVOICE,
        choices=InvoiceType.choices,
        help_text="Type of invoice to download"
    )
    processing_status = models.CharField(
        max_length=20,
        default=ProcessingStatus.NOT_STARTED,
        choices=ProcessingStatus.choices,
        help_text="Status of the invoice processing"
    )
    invoices_downloaded = models.BooleanField(
        default=False,
        help_text="Indicates if the invoice has been downloaded"
    )
    invoices_processed = models.BooleanField(
        default=False,
        help_text="Indicates if the invoice has been processed"
    )
    invoices_registered = models.BooleanField(
        default=False,
        help_text="Indicates if the invoice has been registered in Odoo"
    )
    invoices_notification = models.BooleanField(
        default=False,
        help_text="Indicates if the invoice has been notified to the user"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

class Invoice(models.Model):
    """
    Model to track the invoice downloaded.
    """

    class Status(models.TextChoices):
        REGISTERED_COMPLETE = 'registered_complete'
        REGISTERED_BUT_NOT_MOVE_ID = 'registered_but_not_move_id'
        REGISTERED_BUT_NOT_ATTACHMENT = 'registered_but_not_attachment'
        PROBLEM_NOT_IN_ODOO = 'problem_not_in_odoo'
        PROBLEM_PARTNER_NOT_CREATED = 'problem_partner_not_created'
        PROBLEM_WITH_FACTOS = 'problem_with_factos'
        PROBLEM_WITH_ODOO = 'problem_in_odoo'

    next_download = models.ForeignKey(
        NextDownload,
        on_delete=models.CASCADE,
        related_name="invoices",
        help_text="NextDownload object to which the invoice belongs",
    )
    cufe = models.CharField(
        max_length=150,
        help_text="CUFE of the invoice downloaded",
        blank=True,
        null=True,
    )
    invoice_number = models.CharField(
        max_length=100,
        help_text="Number of the invoice downloaded",
        blank=True,
        null=True,
    )
    issuer_name = models.CharField(
        max_length=100,
        help_text="Name of the entity that issued the invoice",
        blank=True,
        null=True,
    )
    issuer_nit = models.CharField(
        max_length=50,
        help_text="NIT of the entity that issued the invoice",
        blank=True,
        null=True,
    )
    issue_date = models.DateField(
        help_text="Date of the invoice downloaded",
        blank=True,
        null=True,
    )
    due_date = models.DateField(
        help_text="Due date of the invoice downloaded",
        blank=True,
        null=True,
    )
    # NOTE: It is possible to have multiple purchase orders for the same invoice
    # so we store it as a CharField separated by commas
    order_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Purchase order number of the invoice downloaded",
    )
    invoice_file = models.FileField(
        upload_to="invoices/",
        help_text="File of the invoice downloaded",
    )
    invoice_pdf = models.FileField(
        upload_to="invoices/pdf/",
        help_text="File of the invoice downloaded in PDF",
    )
    invoice_processed = models.FileField(
        upload_to="invoices/processed/",
        help_text="File of the invoice processed like CSV",
        null=True,
        blank=True,
    )
    registered_in_odoo = models.BooleanField(
        default=False,
        help_text="Indicates if the invoice has been registered in Odoo",
    )
    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.PROBLEM_NOT_IN_ODOO
    )
    rx_odoo_invoice = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON field to store the invoice created in Odoo",
    )
    rx_odoo_invoice_error = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if the invoice could not be registered in Odoo",
    )
    invoice_type = models.CharField(
        max_length=50,
        default=NextDownload.InvoiceType.ELECTRONIC_INVOICE,
        choices=NextDownload.InvoiceType.choices,
        help_text="Type of invoice to download"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def rename_invoice_pdf_file(self):
        """
        Rename the invoice PDF file to include the invoice number and issue date.
        """
        if self.invoice_pdf and self.invoice_number and self.issue_date:
            old_path = self.invoice_pdf.path
            new_filename = f"{self.invoice_number}_{self.issue_date}.pdf"
            new_path = os.path.join(os.path.dirname(old_path), new_filename)

            if not default_storage.exists(old_path):
                return  # File does not exist

            self.invoice_pdf.name = f"invoices/pdf/{new_filename}"

            os.rename(old_path, new_path)
            
            self.save()

    @property
    def in_odoo(self):
        return "registered" in self.status.lower()

    @property
    def invoice_urls_in_odoo(self):
        """Get the res_id from the action object."""
        # Invoice ID
        list_urls = []
        odoo_host = settings.CONFIG_ODOO['HOST']
        for account_move_obj in self.accountmove_set.all():
            list_urls.append(f"{odoo_host}/web#id={account_move_obj.move_id}&model=account.move&view_type=form")
        return list_urls


class Product(models.Model):
    """
    Model to track the products of the invoice.
    """

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="products",
        help_text="Invoice to which the product belongs",
    )
    code = models.CharField(
        max_length=100,
        blank=True,
        help_text="Código",
    )
    description = models.TextField(
        blank=True,
        help_text="Descripción",
    )
    unit_measurement = models.CharField(
        max_length=50,
        blank=True,
        help_text="Unidad de medida del producto (U/M)",
    )
    quantity = models.FloatField(
        default=0.00,
        help_text="Cantidad",
    )
    unit_price = models.FloatField(
        default=0.00,
        help_text="Precio unitario",
    )
    discount_detail = models.FloatField(
        default=0.00,
        help_text="Descuento detalle",
    )
    surcharge_detail = models.FloatField(
        default=0.00,
        help_text="Recargo detalle",
    )
    iva = models.FloatField(
        default=0.00,
        help_text="Valor IVA",
    )
    iva_percentage = models.FloatField(
        default=0.00,
        help_text="Porcentaje IVA",
    )
    inc = models.FloatField(
        default=0.00,
        help_text="Valor INC",
    )
    inc_percentage = models.FloatField(
        default=0.00,
        help_text="Porcentaje INC",
    )
    unit_sale_price = models.FloatField(
        default=0.00,
        help_text="Precio unitario de venta",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = "Producto"
        verbose_name_plural = "Productos"