from django.contrib import admin, messages
from invoice import models as invoice_models
from invoice.actions import (
    invoice as invoice_actions,
    next_download as new_download_actions
)
from invoice.list_filters import invoice as invoice_list_filters
from invoice.odoo import support_document
from invoice.utils.tasks import search_and_get_dian_link
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from rangefilter.filters import (
    DateRangeFilterBuilder,
)

@admin.register(invoice_models.NextDownload)
class NextDownloadAdmin(admin.ModelAdmin):
    """
    Admin view for the NextDownload model.
    """

    class InvoiceInline(admin.TabularInline):
        """
        Inline admin view for the Invoice model.
        """
        # set inline title
        verbose_name = "Factura descargada"
        verbose_name_plural = "Facturas descargadas"
        model = invoice_models.Invoice
        extra = 0
        readonly_fields = ('created_at', 'updated_at',)
        fields = ('invoice_number', 'issuer_name', 'issuer_nit', 'issue_date', 'due_date', 'order_number', 'invoice_file', 'invoice_pdf', 'registered_in_odoo', 'cufe', 'rx_odoo_invoice', 'rx_odoo_invoice_error', 'created_at', 'updated_at')
        show_change_link = True

    # Inline

    inlines = [InvoiceInline]

    # Admin configuration
    list_display = (
        'id',
        'dian_link',
        'from_date',
        'to_date',
        'invoice_type',
        'processing_status',
        'invoices_downloaded',
        'invoices_processed',
        'invoices_registered',
        'invoices_notification',
        'created_at',
        'updated_at',
    )
    list_filter = ('invoice_type', 'processing_status')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    fieldsets = (
        (None, {
            'fields': (
                ('dian_link',),
                ('from_date', 'to_date', 'invoice_type'),
                'processing_status', 'invoices_downloaded', 'invoices_processed', 'invoices_registered', 'invoices_notification'
            )
        }),
        ('Fechas de creación y actualización del proceso de descarga, procesamiento y registro', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # Actions

    actions = ['go_to_dian_page', 'search_dian_link', 'download_invoices', 'extract_invoice_data', 'register_in_odoo']

    def go_to_dian_page(self, request, queryset):
        """
        Ir a la página de DIAN en una nueva pestaña.
        """
        dian_link = "https://catalogo-vpfe.dian.gov.co/User/CompanyLogin"

        # Validate if the queryset has only one object
        if queryset.count() > 1:
            self.message_user(request, "Por favor selecciona solo un registro.")
            return
        
        # Get the first object from the queryset
        next_download_obj = queryset.first()
    
        return HttpResponseRedirect(next_download_obj.dian_link or dian_link)
    
    go_to_dian_page.short_description = "Ir a la página DIAN"

    def search_dian_link(self, request, queryset):
        """
        Search the DIAN link in the Email model in django
        No specific item selection required.
        """
        try:
            task = search_and_get_dian_link.delay()
            
            messages.success(
                request, 
                f"Tarea de obtención de link de la DIAN iniciada usando el modelo Email en Django. Task ID: {task.id}"
            )
        except Exception as e:
            messages.error(
                request, 
                f"Error al obtener el link de la DIAN del modelo Email en Django: {str(e)}"
            )

    search_dian_link.short_description = "Buscar link de la DIAN"

    def download_invoices(self, request, queryset):
        """
        Download invoices from the selected NextDownload objects.
        """
        if not queryset.exists():
            self.message_user(request, "No hay registros seleccionados.", level='error')
            return

        new_download_actions.download_invoices(self, request, queryset)


    def extract_invoice_data(self, request, queryset):
        """
        Store CSV and PDF files from the selected NextDownload objects.
        """
        if not queryset.exists():
            self.message_user(request, "No hay registros seleccionados.", level='error')
            return

        new_download_actions.extract_invoice_data(self, request, queryset)

    def register_in_odoo(self, request, queryset):
        """
        Register the invoices in Odoo from the selected NextDownload objects.
        """
        if not queryset.exists():
            self.message_user(request, "No hay registros seleccionados.", level='error')
            return

        new_download_actions.register_in_odoo(self, request, queryset)


@admin.register(invoice_models.Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """
    Admin view for the Invoice model.
    """

    class ProductInline(admin.TabularInline):
        """
        Inline admin view for the Product model.
        """
        # set inline title
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        model = invoice_models.Product
        extra = 0
        readonly_fields = ('created_at', 'updated_at',)
        fields = ('code', 'description', 'unit_measurement', 'quantity', 'unit_price', 'discount_detail', 'surcharge_detail', 'iva', 'iva_percentage', 'inc', 'inc_percentage', 'unit_sale_price', 'created_at', 'updated_at')
        show_change_link = True

    # Inline
    inlines = [ProductInline]

    # Admin configuration
    list_display = (
        'id',
        'next_download',
        'in_odoo',
        'status',
        'invoice_number',
        'issuer_name',
        'issuer_nit',
        'issue_date',
        'due_date',
        'order_number',
        'invoice_file',
        'invoice_pdf',
        'purchase_order_url_links',
        'cufe',
        'invoice_type',
        'created_at',
    )
    list_filter = (
        'invoice_type',
        'status',
        invoice_list_filters.FromDateFilter,
        invoice_list_filters.ToDateFilter,
        ("created_at", DateRangeFilterBuilder(title="Fecha de descarga")),
    )
    search_fields = (
        'invoice_number',
        'issuer_name',
        'issuer_nit',
        'order_number',
        'cufe',
    )
    raw_id_fields = ('next_download',)
    readonly_fields = ('created_at', 'updated_at',)
    ordering = ('-created_at',)
    fieldsets = (
        (None, {
            'fields': (
                ('next_download', 'invoice_type'),
                ('invoice_number', 'issue_date', 'due_date'),
                ('issuer_name', 'issuer_nit'),
                ('order_number',),
            )
        }),
        ('Archivos de la factura', {
            'fields': (
                ('invoice_file'),
                ('invoice_pdf',),
                ('invoice_processed',),
            ),
            'classes': ('collapse',),
        }),
        ('Odoo', {
            'fields': (
                ('registered_in_odoo', 'rx_odoo_invoice', 'rx_odoo_invoice_error'),
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # Actions

    actions = ['get_zip_files_downloaded', 'extract_invoice_data', 'process_single_invoice_with_ai', 'register_in_odoo']

    def get_zip_files_downloaded(self, request, queryset):
        """
        Download ZIP files from the selected Invoice objects.
        """
        return invoice_actions.get_zip_files_downloaded(self, request, queryset)
    
    def extract_invoice_data(self, request, queryset):
        """
        Store products and PDF files from the selected Invoice objects.
        """
        return invoice_actions.extract_invoice_data(self, request, queryset)

    def process_single_invoice_with_ai(self, request, queryset):
        """
        Process selected invoices with AI to extract data from PDFs.
        """
        return invoice_actions.process_single_invoice_with_ai(self, request, queryset)

    def register_in_odoo(self, request, queryset):
        """
        Register the invoices in Odoo from the selected Invoice objects.
        """
        return invoice_actions.register_in_odoo(self, request, queryset)

    # Displays

    def in_odoo(self, obj):
        return obj.in_odoo
    in_odoo.boolean = True
    in_odoo.short_description = 'En Odoo'

    def purchase_order_url_links(self, obj):
        # Display the invoice file as a link
        list_urls: list = obj.invoice_urls_in_odoo

        html_links = []

        if list_urls:
            for url in list_urls:
                html_links.append(f'<a href="{url}" target="_blank">Ver en Odoo</a>')

        return mark_safe('<br>'.join(html_links)) if html_links else "No hay enlaces disponibles"
            


@admin.register(invoice_models.Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Admin view for the Product model.
    """
    list_display = (
        'id',
        'invoice',
        'code',
        'description',
        'unit_measurement',
        'quantity',
        'unit_price',
        'discount_detail',
        'surcharge_detail',
        'iva',
        'iva_percentage',
        'inc',
        'inc_percentage',
        'unit_sale_price',
    )
    raw_id_fields = ('invoice',)
    readonly_fields = ('created_at', 'updated_at',)
    ordering = ('-created_at',)
    fieldsets = (
        (None, {
            'fields': (
                ('invoice',),
                ('code', 'description'),
                ('unit_measurement',),
                ('quantity',),
                ('unit_price',),
                ('discount_detail',),
                ('surcharge_detail',),
                ('iva',),
                ('iva_percentage',),
                ('inc',),
                ('inc_percentage',),
                ('unit_sale_price',),
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )