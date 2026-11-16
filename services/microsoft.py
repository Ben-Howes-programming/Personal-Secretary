"""
microsoft.py
============
Purpose : Optional Outlook mail and calendar through Microsoft Graph (read-only).
Location: services/microsoft.py
Used by : services/inbox.py, ui/state.py, views/settings.py
Status  : Written against the Microsoft Graph v1.0 and MSAL documentation but NOT yet
          run against a live account. Treat the first connection as a test.
Setup   : 1. pip install msal
          2. Register an app at https://entra.microsoft.com (App registrations, New
             registration, "Accounts in any organizational directory and personal
             Microsoft accounts", then Authentication, "Allow public client flows" = Yes).
          3. Put the Application (client) ID in .env as MS_CLIENT_ID.
          4. Open Settings in the app and press Connect Outlook.
Note    : A university account may refuse until the university's IT admin approves
          the app. A personal outlook.com account works without that step.
"""

import time
from datetime import timezone

import config

GRAPH = "https://graph.microsoft.com/v1.0"
_app = None


def is_configured():
    return bool(config.MS_CLIENT_ID)


def _msal_app():
    """The MSAL client with a token cache saved to ms_token.json."""
    global _app
    import msal
    if _app is None:
        cache = msal.SerializableTokenCache()
        if config.MS_TOKEN_PATH.exists():
            cache.deserialize(config.MS_TOKEN_PATH.read_text())
        _app = msal.PublicClientApplication(
            config.MS_CLIENT_ID, authority=f"https://login.microsoftonline.com/{config.MS_TENANT}", token_cache=cache)
    return _app


def _save_cache():
    cache = _msal_app().token_cache
    if cache.has_state_changed:
        config.MS_TOKEN_PATH.write_text(cache.serialize())


def _token():
    """A valid access token from the saved login, or None if you need to connect again."""
    if not is_configured():
        return None
    try:
        app = _msal_app()
    except ImportError:
        return None
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(config.MS_SCOPES, account=accounts[0])
    _save_cache()
    return result.get("access_token") if result else None


def is_connected():
    try:
        return _token() is not None
    except Exception:
        return False


def start_login():
    """Step 1 of sign-in. Returns a dict with 'user_code' and 'verification_uri' to show you."""
    flow = _msal_app().initiate_device_flow(scopes=config.MS_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(flow.get("error_description", "Could not start the Microsoft sign-in."))
    return flow


def finish_login(flow, wait_seconds=20):
    """Step 2: call after you have entered the code in the browser. Returns True on success."""
    flow["expires_at"] = min(flow.get("expires_at", time.time() + wait_seconds), time.time() + wait_seconds)
    result = _msal_app().acquire_token_by_device_flow(flow)
    _save_cache()
    return "access_token" in result


def _get(path, params=None, headers=None):
    import requests
    token = _token()
    if not token:
        raise PermissionError("Outlook is not connected.")
    response = requests.get(GRAPH + path, params=params, timeout=20,
                            headers={"Authorization": f"Bearer {token}", **(headers or {})})
    response.raise_for_status()
    return response.json()


def list_messages(limit=25):
    """Recent inbox mail in the same shape as services/gmail.get_email."""
    from datetime import datetime
    data = _get("/me/mailFolders/inbox/messages",
                params={"$top": limit, "$orderby": "receivedDateTime desc",
                        "$select": "id,subject,from,receivedDateTime,bodyPreview,body,conversationId"},
                headers={"Prefer": 'outlook.body-content-type="text"'})
    emails = []
    for item in data.get("value", []):
        sender = (item.get("from") or {}).get("emailAddress") or {}
        received = item.get("receivedDateTime", "")
        try:
            stamp = datetime.fromisoformat(received.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        except ValueError:
            stamp = None
        emails.append({
            "id": "ms:" + item["id"], "provider": "outlook", "thread_id": item.get("conversationId"),
            "sender": f"{sender.get('name', '')} <{sender.get('address', '')}>".strip(),
            "subject": item.get("subject") or "No subject", "date": received, "received_ts": stamp,
            "body": (item.get("body") or {}).get("content", ""), "snippet": item.get("bodyPreview", ""),
            "labels": [], "list_unsubscribe": False,
        })
    return emails


def list_events(start_dt, end_dt):
    """Calendar events in Google's shape, so services/calendar.py can use them unchanged."""
    data = _get("/me/calendarView",
                params={"startDateTime": start_dt.isoformat(), "endDateTime": end_dt.isoformat(),
                        "$orderby": "start/dateTime", "$top": 100,
                        "$select": "subject,start,end,isAllDay,showAs"},
                headers={"Prefer": f'outlook.timezone="{config.TIMEZONE}"'})
    events = []
    for item in data.get("value", []):
        start, end = item["start"]["dateTime"][:19], item["end"]["dateTime"][:19]
        if item.get("isAllDay"):
            shaped = {"start": {"date": start[:10]}, "end": {"date": end[:10]}}
        else:
            shaped = {"start": {"dateTime": start}, "end": {"dateTime": end}}
        shaped.update(summary=item.get("subject") or "Untitled event", source="Outlook")
        if item.get("showAs") == "free":
            shaped["transparency"] = "transparent"
        events.append(shaped)
    return events
