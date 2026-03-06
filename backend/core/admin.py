from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import CustomUser, Employee, Invoice, InvoiceSession, PettyReload
from .services.pettyflow_service import PettyFlowService
from django.contrib import messages

# ... (Previous code remains the same)

@admin.register(PettyReload)
class PettyReloadAdmin(admin.ModelAdmin):
    list_display = ["reference", "employee", "amount_requested", "state", "date_request"]
    list_filter = ["state", "date_request", "employee"]
    search_fields = ["reference", "employee__sheet_name", "observations"]
    readonly_fields = ["reference", "date_request", "created_at", "updated_at"]
    actions = ["approve_requests", "execute_reloads", "cancel_requests"]

    def save_model(self, request, obj, form, change):
        if not change:  # On creation
            day_check = PettyFlowService.check_request_day()
            if day_check['warning']:
                messages.warning(request, day_check['message'])
            
            # Auto-notify if visitador
            PettyFlowService.notify_discord_visitador(obj.employee.sheet_name, obj.amount_requested)
            
        super().save_model(request, obj, form, change)

    @admin.action(description="Aprobar solicitudes seleccionadas")
    def approve_requests(self, request, queryset):
        for obj in queryset.filter(state="draft"):
            allowed, message = PettyFlowService.validate_budget(obj.employee.sheet_name, obj.amount_requested)
            if not allowed:
                self.message_user(request, f"Error en {obj.reference}: {message}", messages.ERROR)
                continue
            
            if message: # Warning message
                self.message_user(request, f"Aviso en {obj.reference}: {message}", messages.WARNING)
                
            obj.state = "approved"
            obj.save()
        self.message_user(request, "Solicitudes aprobadas correctamente.")

    @admin.action(description="Ejecutar reloads seleccionados")
    def execute_reloads(self, request, queryset):
        success_count = 0
        for obj in queryset.filter(state="approved"):
            if PettyFlowService.sync_to_google_sheets(obj):
                obj.state = "executed"
                obj.save()
                success_count += 1
            else:
                self.message_user(request, f"Error sincronizando {obj.reference}", messages.ERROR)
        
        if success_count:
            self.message_user(request, f"Se ejecutaron {success_count} reloads correctamente.")

    @admin.action(description="Cancelar solicitudes seleccionadas")
    def cancel_requests(self, request, queryset):
        queryset.filter(state__in=["draft", "approved"]).update(state="cancel")
        self.message_user(request, "Solicitudes canceladas.")


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display  = ["email", "is_staff", "is_active"]
    ordering      = ["email"]
    search_fields = ["email"]

    fieldsets = (
        (None,       {"fields": ("email", "password")}),
        ("Permisos", {"fields": ("is_staff", "is_active", "is_superuser", "groups", "user_permissions")}),
        ("Fechas",   {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields":  ("email", "password1", "password2", "is_staff", "is_active"),
        }),
    )


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "id", "cellphone", "business_name", "invoice_number",
        "value", "was_corrected", "status", "created_at", "url_soporte",
    ]
    list_filter = ["status", "was_corrected", "is_pdf", "created_at"]
    search_fields = ["cellphone", "business_name", "nit", "invoice_number"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    readonly_fields = [
        "cellphone", "employee", "invoice_date", "business_name", "nit",
        "invoice_number", "original_value", "value", "was_corrected",
        "cost_center", "concept", "file_path", "is_pdf",
        "sheet_row", "sheet_record_id", "drive_folder_id",
        "status", "created_at", "updated_at",
    ]

    @admin.display(description="URL Soporte")
    def url_soporte(self, obj):
        if obj.drive_folder_id:
            url = f"https://drive.google.com/drive/folders/{obj.drive_folder_id}"
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">📂 Ver soporte</a>',
                url,
            )
        return "Sin soporte"


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["cellphone", "sheet_name", "is_active", "updated_at"]
    list_display_links = ["cellphone"]
    list_editable = ["is_active"]
    search_fields = ["cellphone", "sheet_name"]
    list_filter = ["is_active"]


@admin.register(InvoiceSession)
class InvoiceSessionAdmin(admin.ModelAdmin):
    list_display = ["cellphone", "state", "current_invoice", "invoice_id", "last_row", "updated_at"]
    list_filter = ["state"]
    date_hierarchy = "updated_at"
    ordering = ["-updated_at"]
    readonly_fields = [
        "cellphone",
        "state",
        "current_invoice",
        "last_row",
        "last_id",
        "invoice_id",
        "cost_center",
        "created_at",
        "updated_at",
    ]
