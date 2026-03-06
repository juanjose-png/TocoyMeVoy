from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, Employee, Invoice, InvoiceSession


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
        "value", "was_corrected", "status", "created_at",
    ]
    list_filter = ["status", "was_corrected", "is_pdf", "created_at"]
    search_fields = ["cellphone", "business_name", "nit", "invoice_number"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    readonly_fields = [
        "cellphone", "employee", "invoice_date", "business_name", "nit",
        "invoice_number", "original_value", "value", "was_corrected",
        "cost_center", "concept", "file_path", "is_pdf",
        "sheet_row", "sheet_record_id", "status", "created_at", "updated_at",
    ]


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
