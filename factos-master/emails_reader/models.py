from django.db import models


class Email(models.Model):
    """
    Model to store email information.
    """
    id = models.CharField(
        primary_key=True,
        max_length=255,
        unique=True,
        help_text="Unique identifier for the email in Gmail"
    )
    from_email = models.CharField(
        max_length=255,
        help_text="Email address of the sender"
    )
    thread_id = models.CharField(
        max_length=255,
        help_text="Thread ID for the email conversation"
    )
    label_ids = models.JSONField(
        default=list,
        help_text="List of label IDs associated with the email"
    )
    snippet = models.TextField(
        help_text="Short snippet of the email content"
    )
    payload = models.JSONField(
        help_text="Payload of the email containing headers and body"
    )
    size_estimate = models.IntegerField(
        help_text="Estimated size of the email in bytes"
    )
    history_id = models.CharField(
        max_length=255,
        help_text="History ID for tracking changes to the email"
    )
    internal_date = models.DateTimeField(
        help_text="Internal date of the email in milliseconds since epoch"
    )

    def __str__(self):
        return f"{self.id} - {self.from_email}"


class EmailAttachment(models.Model):
    """
    Model to store email attachments.
    """
    class MimeType(models.TextChoices):
        PDF = 'application/x-pdf', 'PDF'
        IMAGE_JPEG = 'image/jpeg', 'JPEG'
        IMAGE_PNG = 'image/png', 'PNG'
        ZIP = 'application/zip', 'ZIP'
    attachment_id = models.CharField(
        primary_key=True,
        max_length=255,
        help_text="Unique identifier for the attachment"
    )
    email = models.ForeignKey(
        Email,
        on_delete=models.CASCADE,
        related_name="attachments",
        help_text="Email to which the attachment belongs"
    )
    file = models.FileField(
        upload_to="email_attachments/",
        help_text="Attachment file"
    )
    filename = models.CharField(
        max_length=255,
        help_text="Name of the attachment file"
    )
    content_type = models.CharField(
        max_length=50,
        choices=MimeType.choices,
        help_text="MIME type of the attachment"
    )
    size = models.IntegerField(
        help_text="Size of the attachment in bytes"
    )

    def __str__(self):
        return f"{self.filename} - {self.email.id}"
