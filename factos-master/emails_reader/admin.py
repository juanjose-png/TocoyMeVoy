from django.contrib import admin
from django.contrib import messages
from .models import Email, EmailAttachment
from .tasks import email_save_in_db


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ('id', 'from_email', 'thread_id', 'snippet', 'size_estimate', 'history_id', 'internal_date')
    search_fields = ('id', 'from_email', 'thread_id', 'snippet', 'history_id')
    list_filter = ('internal_date',)
    readonly_fields = ('id',)
    actions = ["sync_emails_from_gmail"]
    list_display_links = ('id', 'from_email')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.exclude(id__exact='').exclude(id__isnull=True)

    def sync_emails_from_gmail(modeladmin, request, queryset):
        """
            Action to sync emails from Gmail.
            No specific item selection required.
        """
        try:
            task = email_save_in_db.delay()
            
            messages.success(
                request, 
                f"Tarea de sincronización de emails iniciada. Task ID: {task.id}"
            )
        except Exception as e:
            messages.error(
                request, 
                f"Error al iniciar la sincronización de emails: {str(e)}"
            )

    sync_emails_from_gmail.short_description = "Sincronizar emails desde Gmail"

@admin.register(EmailAttachment)
class EmailAttachmentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'email', 'content_type', 'size')
    search_fields = ('filename', 'email__id')
    list_filter = ('content_type',)
    readonly_fields = ('file',)


