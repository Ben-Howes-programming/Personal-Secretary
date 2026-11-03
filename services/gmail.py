import base64

from services.google_auth import build_service


def get_gmail_service():
    return build_service("gmail", "v1")


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