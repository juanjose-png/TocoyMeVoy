import base64
import re
from django.utils import timezone
from emails_reader import models as emails_models


def get_dian_link_from_email(email_obj: emails_models.Email) -> str:
    """
    Extracts the DIAN link from the decoded email body.

    Args:
        email_obj (emails_models.Email): The email object containing the payload.

    Returns:
        str: The extracted DIAN link.
    """

    payload = email_obj.payload
    parts = payload.get("parts", [])

    decoded_body = ""
    if not parts:
        decoded_body = payload.get("body", {}).get("data", "")
    else:
        for part in parts:
            if part.get("mimeType") != "text/html":
                continue

            decoded_body = part.get("body", {}).get("data", "")
            if decoded_body:
                break

    html = base64.urlsafe_b64decode(decoded_body.encode("UTF-8")).decode("UTF-8") if decoded_body else ""
    if not html:
        return ""

    # Use regex to find the DIAN link in the HTML conten
    pattern = r'https://catalogo-vpfe\.dian\.gov\.co/User/AuthToken\?[^"\' >]+'
    match = re.search(pattern, html)
    
    if match:
        return match.group(0)
    
    return ""


def search_and_get_dian_link(
        date_from: str="",
        date_to: str="",
    ) -> str:
    """Searches for the latest email from DIAN within the specified date range and retrieves the DIAN link.
    Args:
        date_from (str): The start date for the search in 'YYYY-MM-DD' format.
        date_to (str): The end date for the search in 'YYYY-MM-DD' format.

    Returns:
        str: The DIAN link if found, otherwise "".
    """
    
    # Prepare the filter for date range
    dates = {}
    if not date_from and not date_to:
        # If no dates are provided, we will search for the latest email
        today = timezone.now()
        dates["internal_date__date__gte"] = today.date()
    else:
        if date_from:
            dates['internal_date__date__gte'] = date_from
        if date_to:
            dates['internal_date__date__lte'] = date_to

    # Get the lastest email object before date_from
    email_obj = emails_models.Email.objects.filter(
        **dates
    ).filter(
        from_email__icontains="facturacionelectronica@dian.gov.co"
    ).order_by('-internal_date').first()

    if not email_obj:
        print("No email found from DIAN before the specified date.")
        return ""
    
    dian_link = get_dian_link_from_email(email_obj)
    if not dian_link:
        print("No DIAN link found in the email.")
        return ""
    
    # Clean the link
    dian_link = dian_link.replace("&amp;", "&")

    return dian_link

