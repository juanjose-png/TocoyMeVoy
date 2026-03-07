from rest_framework import serializers
from invoice import models as invoice_models
from invoice.utils import tasks as invoice_tasks



class NextDownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = invoice_models.NextDownload
        fields = [
            'id',
            'invoices_downloaded',
            'invoices_processed',
            'invoices_registered',
            'invoices_notification',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SaveLinkSerializer(serializers.Serializer):
    dian_link = serializers.CharField(required=True, help_text="Link to the invoice file")

    def validate(self, attrs):
        
        # Buscar NextDownload
        # TODO: Check the possibility of multiple NextDownload objects
        self.next_download_obj = invoice_models.NextDownload.objects.filter(
            processing_status=invoice_models.NextDownload.ProcessingStatus.NOT_STARTED,
            invoices_downloaded=False,
            invoices_processed=False,
            invoices_registered=False,
            invoices_notification=False,
        ).order_by('created_at').first()

        # Check if the object exists
        if not self.next_download_obj:
            raise serializers.ValidationError({"error": "No NextDownload object found"})

        return super().validate(attrs)


    def create(self, validated_data):
        dian_link = validated_data.get('dian_link')

        # Clean the link
        dian_link = dian_link.replace("&amp;", "&")

        self.next_download_obj.dian_link = dian_link
        self.next_download_obj.save()

        self.celery_task_obj = invoice_tasks.read_and_process_invoice.delay(next_download_id=self.next_download_obj.id)


    def to_representation(self, instance):
        return {
            "task_id": self.celery_task_obj.id,
            "status": "Task created successfully",
            "message": "The task to process the invoice has been created and is running in the background."
        }
    