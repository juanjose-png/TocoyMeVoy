import os
import pandas as pd
import base64
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_credentials():
  """Shows basic usage of the Gmail API.
  Lists the user's Gmail labels.
  """
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  token_path = settings.BASE_DIR / "token.json"
  credencials_path = settings.BASE_DIR / "credentials.json"

  if os.path.exists(token_path):
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          credencials_path, SCOPES
      )
      creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open(token_path, "w") as token:
      token.write(creds.to_json())

  return creds
  

def list_emails(creds, date_from=None, date_to=None, max_results=10, message_id_to_skip=None):
    """Lists the user's Gmail messages.

    Args:
        creds: The credentials to use for the Gmail API.
        date_from: Optional; filter messages after this date (YYYY/MM/DD).
        date_to: Optional; filter messages before this date (YYYY/MM/DD).
        max_results: Optional; maximum number of results to return.
        message_id_to_skip: Optional; ID of the message to skip in the results. It is needed to perform incremental updates.
    
    Returns:
        A pandas DataFrame containing the messages.
    """

    # Initialize message_id_to_skip if not provided
    message_id_to_skip = message_id_to_skip or []


    try:
        # Call the Gmail API
        service = build("gmail", "v1", credentials=creds)
        results = service.users()
        # Get first 10 messages
        query = "in:inbox"
        if date_from:
          query += f" after:{date_from}" if not date_to else f" after:{date_from} before:{date_to}"
        elif date_to:
          query += f" before:{date_to}" if not date_from else f" after:{date_from} before:{date_to}"
           
        messages = (
            results.messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
            .get("messages", [])
        )

        data = []
        for message in messages:
            # Skip the message if it matches the ID to skip
            if message['id'] == message_id_to_skip:
                continue

            # Get the full message details
            msg = service.users().messages().get(userId="me", id=message["id"]).execute()
            data.append(msg)


        return pd.DataFrame(data)

    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f"An error occurred: {error}")


def extract_attachments(message):
    """Extracts attachments from a Gmail message.

    Args:
        message: The Gmail message object.
    
    Returns:
        A list of dictionaries containing attachment details.
    """
    attachments = []
    if "payload" in message and "parts" in message["payload"]:
        for part in message["payload"]["parts"]:
            if part.get("filename") and part.get("body", {}).get("attachmentId"):
                attachments.append({
                    "filename": part["filename"],
                    "attachmentId": part["body"]["attachmentId"],
                    "mimeType": part.get("mimeType"),
                    "size": part.get("body", {}).get("size")
                })
    return attachments


def download_attachment(creds, msg_id, attachment_id):
    """Downloads an attachment from a Gmail message.

    Args:
        service: The Gmail API service instance.
        user_id: The user's email address or "me".
        msg_id: The ID of the message containing the attachment.
        attachment_id: The ID of the attachment to download.
    
    Returns:
        The content of the downloaded attachment.
    """
    try:
        service = build("gmail", "v1", credentials=creds)
        results = service.users()

        attachment = (
            results.messages()
            .attachments()
            .get(userId="me", messageId=msg_id, id=attachment_id)
            .execute()
        )
        return base64.urlsafe_b64decode(attachment["data"].encode("UTF-8"))
    except HttpError as error:
        print(f"An error occurred while downloading the attachment: {error}")

