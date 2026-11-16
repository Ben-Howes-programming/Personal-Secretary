"""
gmail.py
========
Purpose : Read Gmail, and (only if you switch it on) save a reply into Gmail Drafts.
Location: services/gmail.py
Used by : services/inbox.py, views/inbox.py
Note    : The app never sends email. ENABLE_GMAIL_DRAFTS only creates a draft for
          you to check and send yourself inside Gmail.
"""

import base64
import re
from email.message import EmailMessage
from email.utils import parseaddr

from services.google_auth import build_service


def get_gmail_service(interactive=True):
    return build_service("gmail", "v1", interactive)


def html_to_text(html):
    """Readable text from an HTML email."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html)
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def get_email_body(payload):
    """Walk every part of the message. Prefer plain text, fall back to HTML."""
    plain, html = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and not part.get("filename"):
            if mime == "text/plain":
                plain.append(_decode(data))
            elif mime == "text/html":
                html.append(_decode(data))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    if html:
        return html_to_text("\n".join(html))
    return "[No readable body found]"


def list_message_ids(gmail, query="in:inbox", max_results=25):
    result = gmail.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    return [message["id"] for message in result.get("messages", [])]


def get_email(gmail, message_id):
    """One message as a plain dictionary the rest of the app understands."""
    message = gmail.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in message["payload"].get("headers", [])}
    return {
        "id": message_id,
        "provider": "gmail",
        "thread_id": message.get("threadId"),
        "sender": headers.get("from", "Unknown"),
        "subject": headers.get("subject", "No subject"),
        "date": headers.get("date", "Unknown"),
        "received_ts": int(message.get("internalDate", 0)) / 1000 or None,
        "body": get_email_body(message["payload"]),
        "snippet": message.get("snippet", ""),
        "labels": message.get("labelIds", []),
        "list_unsubscribe": "list-unsubscribe" in headers,
        "message_id_header": headers.get("message-id"),
    }


def account_address(gmail):
    return gmail.users().getProfile(userId="me").execute().get("emailAddress")


def create_draft(gmail, email, reply_text):
    """Save a reply in Gmail Drafts, threaded under the original. Needs ENABLE_GMAIL_DRAFTS."""
    message = EmailMessage()
    message["To"] = parseaddr(email.get("sender") or "")[1]
    subject = email.get("subject") or ""
    message["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    message.set_content(reply_text)
    body = {"message": {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}}
    if email.get("thread_id"):
        body["message"]["threadId"] = email["thread_id"]
    return gmail.users().drafts().create(userId="me", body=body).execute()
