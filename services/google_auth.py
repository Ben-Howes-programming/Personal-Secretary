"""
google_auth.py
==============
Purpose : The single place that logs in to Google, shared by Gmail and Calendar.
Location: services/google_auth.py
Note    : A saved token is refreshed silently. The browser only opens when there is
          no token, the token was revoked, or you switched on a new permission in .env.
"""

import json

import config


def is_configured():
    """True once credentials.json (the OAuth client file from Google Cloud) is in the project folder."""
    return config.GOOGLE_CREDENTIALS_PATH.exists()


def has_token():
    """True when a saved login exists that covers every permission the app now asks for."""
    if not config.GOOGLE_TOKEN_PATH.exists():
        return False
    try:
        saved = set(json.loads(config.GOOGLE_TOKEN_PATH.read_text()).get("scopes") or [])
    except (OSError, ValueError):
        return False
    return set(config.GOOGLE_SCOPES).issubset(saved)


def get_credentials(interactive=True):
    """Return valid Google credentials, refreshing or logging in if needed.

    interactive=False never opens a browser. It raises instead, so pages can show
    a Connect button rather than surprising you with a login window.
    """
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not is_configured():
        raise FileNotFoundError("credentials.json is missing from the project folder.")

    creds = None
    if has_token():
        creds = Credentials.from_authorized_user_file(str(config.GOOGLE_TOKEN_PATH), config.GOOGLE_SCOPES)

    if creds and creds.valid:
        return creds

    # Expired but refreshable: no browser needed
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None   # refresh token revoked, so a fresh login is needed

    if not creds or not creds.valid:
        if not interactive:
            raise PermissionError("Google is not connected yet.")
        flow = InstalledAppFlow.from_client_secrets_file(str(config.GOOGLE_CREDENTIALS_PATH), config.GOOGLE_SCOPES)
        creds = flow.run_local_server(port=0)

    config.GOOGLE_TOKEN_PATH.write_text(creds.to_json())
    return creds


def build_service(name, version, interactive=True):
    """Example: build_service("gmail", "v1") or build_service("calendar", "v3")."""
    from googleapiclient.discovery import build
    return build(name, version, credentials=get_credentials(interactive), cache_discovery=False)
