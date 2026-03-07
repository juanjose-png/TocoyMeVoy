from django.utils import timezone
from factos.celery import app
from emails_reader.utils import manage_emails



@app.task()
def email_save_in_db(max_results: int = 100):
    """
    Celery task to save emails in the database.
    
    Args:
        max_results (int): Maximum number of emails to fetch.
        
    Returns:
        list: List of saved email IDs.
    """
    today = timezone.now()
    date_from = today.date().strftime("%Y-%m-%d")

    email_saved =  manage_emails.save_in_db(date_from=date_from, date_to="", max_results=max_results)

    return list(map(lambda x: {"id": x.id, "from": x.from_email, "snippet": x.snippet}, email_saved) if email_saved else [])