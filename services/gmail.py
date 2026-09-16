import os
import base64

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly"
]


def get_gmail_service():
    credentials = None

    if os.path.exists("token.json"):
        credentials = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json",
            SCOPES
        )

        credentials = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(credentials.to_json())

    return build(
        "gmail",
        "v1",
        credentials=credentials
    )


def get_email_body(payload):
    if payload.get("body", {}).get("data"):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data).decode("utf-8")

    for part in payload.get("parts", []):
        if part["mimeType"] == "text/plain":
            data = part.get("body", {}).get("data")

            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8")

    return "[No plain-text body found]"


def get_email(gmail, message_id):
    email = gmail.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    headers = email["payload"]["headers"]

    email_info = {}

    for header in headers:
        email_info[header["name"]] = header["value"]

    body = get_email_body(email["payload"])

    return {
        "sender": email_info.get("From", "Unknown"),
        "subject": email_info.get("Subject", "No subject"),
        "date": email_info.get("Date", "Unknown"),
        "body": body
    }