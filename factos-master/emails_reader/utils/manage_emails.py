from datetime import datetime
from django.core.files.base import ContentFile
from django.utils import timezone
from emails_reader import models as email_models
from emails_reader.utils import read_gmail


def get_from(payload: dict) -> str:
    """
    Extracts the 'From' email address from the payload.
    
    Args:
        payload (dict): The email payload containing headers.
        
    Returns:
        str: The 'From' email address or an empty string if not found.
    """
    headers = payload.get("headers", [])
    for header in headers:
        if header.get("name") == "From":
            return header.get("value", "")
    return ""


def save_in_db(date_from: str, date_to: str, max_results: int) -> list:

    # Filter emails with date_from or date_to or both
    if not date_from and not date_to:
        email_query = email_models.Email.objects.all()
    elif date_from and not date_to:
        email_query = email_models.Email.objects.filter(internal_date__gte=date_from)
    elif not date_from and date_to:
        email_query = email_models.Email.objects.filter(internal_date__lte=date_to)
    else:
        email_query = email_models.Email.objects.filter(
            internal_date__gte=date_from,
            internal_date__lte=date_to
        )

    if email_query.exists():
        # If there are emails to skip, we will use their IDs
        email_ids = list(email_query.values_list('id', flat=True))
    else:
        # If no emails exist, we can skip the ID check
        email_ids = []

    # If there are no emails to skip, we can proceed with the full fetch
    creds = read_gmail.get_credentials()
    df = read_gmail.list_emails(creds, date_from=date_from, date_to=date_to, max_results=max_results, message_id_to_skip=email_ids)

    email_saved: list = []
    for index, row in df.iterrows():
        internal_date = timezone.make_aware(
            datetime.fromtimestamp(int(row.get("internalDate", 0)) / 1000),
            timezone.get_default_timezone()
        )
    
        # Get or create an Email object
        email_obj, created = email_models.Email.objects.get_or_create(
            id=row.get("id"),
            defaults={
                "from_email": get_from(row.get("payload", {})),
                "thread_id": row.get("threadId"),
                "label_ids": row.get("labelIds", []),
                "snippet": row.get("snippet"),
                "payload": row.get("payload", {}),
                "size_estimate": row.get("sizeEstimate"),
                "history_id": row.get("historyId"),
                "internal_date": internal_date
            }
        )
        
        # If the email was created, we add it to the saved list
        if created:
            email_saved.append(email_obj)


        # Save attachments if they exist
        attachments = read_gmail.extract_attachments(row)
        for attachment in attachments:
            # Download the attachment content and save in model
            attachment_content = read_gmail.download_attachment(creds, row['id'], attachment['attachmentId'])
            # Create temporary file or use a file storage system
            # Here we assume attachment_content is a bytes-like object
            if not attachment_content:
                print(f"Attachment {attachment['filename']} could not be downloaded.")
                continue
            
            django_file = ContentFile(attachment_content, name=attachment['filename'])

            email_attachment_obj, created = email_models.EmailAttachment.objects.get_or_create(
                attachment_id=attachment['attachmentId'],
                email=email_obj,
                defaults={
                    "file": django_file,
                    "filename": attachment['filename'],
                    "content_type": attachment['mimeType'],
                    "size": attachment['size']
                }
            )

    return email_saved
