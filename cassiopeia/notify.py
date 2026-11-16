"""
notify.py
=========
Purpose : The only ways Cassiopeia can reach you: a Mac notification, an iMessage to
          your own number, and an email to your own Gmail address.
Location: cassiopeia/notify.py
Used by : cassiopeia/briefing.py, cassiopeia/brain.py, cassiopeia/server.py
Safety  : There is no recipient argument anywhere in this file, on purpose. Texts go to
          config.OWNER_PHONE and emails go to the address of the signed-in Gmail account.
          Every attempt is recorded in the cass_outbox table.
"""

import base64
import platform
import subprocess
from email.message import EmailMessage

import config
from cassiopeia import store

IS_MAC = platform.system() == "Darwin"

# The message and number are passed as arguments, never pasted into the script text,
# so nothing inside a message can be run as AppleScript.
IMESSAGE_SCRIPT = '''on run argv
    tell application "Messages"
        set theService to 1st account whose service type = iMessage
        send (item 2 of argv) to participant (item 1 of argv) of theService
    end tell
end run'''

NOTIFY_SCRIPT = '''on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run'''


def _osascript(script, *arguments):
    done = subprocess.run(["osascript", "-e", script, *arguments], capture_output=True, text=True, timeout=30)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip()[:300] or "osascript failed")


def mac_notification(title, body):
    """A banner in the corner of the screen. Returns (ok, detail)."""
    if not IS_MAC:
        return False, "Notifications need macOS."
    try:
        _osascript(NOTIFY_SCRIPT, title, body[:240])
        return True, "shown"
    except Exception as problem:
        return False, str(problem)


def text_me(body):
    """iMessage to your own phone. Returns (ok, detail)."""
    body = (body or "").strip()
    if not body:
        return False, "Nothing to send."
    if not config.ENABLE_IMESSAGE:
        status, detail = "off", "Texting is switched off. Set ENABLE_IMESSAGE=true in .env."
    elif not config.OWNER_PHONE:
        status, detail = "off", "No phone number. Set OWNER_PHONE in .env."
    elif not IS_MAC:
        status, detail = "off", "iMessage needs the Messages app on macOS."
    else:
        try:
            _osascript(IMESSAGE_SCRIPT, config.OWNER_PHONE, body[:1500])
            status, detail = "sent", "Sent by iMessage."
        except Exception as problem:
            status, detail = "failed", f"Messages refused: {problem}"
    store.log_outbox("text", body, status, detail)
    return status == "sent", detail


def email_me(subject, body):
    """Email to your own Gmail address, from that same address. Returns (ok, detail)."""
    if not config.ENABLE_EMAIL_TO_SELF:
        status, detail = "off", "Email to yourself is switched off. Set ENABLE_EMAIL_TO_SELF=true in .env."
    else:
        try:
            from services import gmail, google_auth
            if not (google_auth.is_configured() and google_auth.has_token()):
                raise RuntimeError("Google is not connected.")
            service = gmail.get_gmail_service(interactive=False)
            me = gmail.account_address(service)          # the only address this function can reach
            message = EmailMessage()
            message["To"], message["From"] = me, me
            message["Subject"] = f"[{config.APP_NAME}] {subject}"[:150]
            message.set_content(body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            status, detail = "sent", "Emailed to your own address."
        except Exception as problem:
            status, detail = "failed", f"Email failed: {str(problem)[:200]}"
    store.log_outbox("email", f"{subject}\n\n{body}", status, detail)
    return status == "sent", detail
