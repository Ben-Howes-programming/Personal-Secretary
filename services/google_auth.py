"""
google_auth.py
==============
Purpose : The single place that logs in to Google, shared by Gmail and Calendar.
Location: services/google_auth.py
Fixes   : an expired token is now refreshed silently instead of reopening the browser.
"""

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config


def get_credentials():
    """Return valid Google credentials, refreshing or logging in if needed."""
    creds = None

    # 1. Load the saved token if there is one
    if config.GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(config.GOOGLE_TOKEN_PATH), config.GOOGLE_SCOPES
        )

    # 2. Token still good: use it
    if creds and creds.valid:
        return creds

    # 3. Token expired but refreshable: refresh without any browser
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None   # refresh token revoked, so fall through to a fresh login

    # 4. Otherwise do the full browser login
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.GOOGLE_CREDENTIALS_PATH), config.GOOGLE_SCOPES
        )
        creds = flow.run_local_server(port=0)

    config.GOOGLE_TOKEN_PATH.write_text(creds.to_json())
    return creds


def build_service(name, version):
    """Example: build_service("gmail", "v1") or build_service("calendar", "v3")."""
    return build(name, version, credentials=get_credentials())