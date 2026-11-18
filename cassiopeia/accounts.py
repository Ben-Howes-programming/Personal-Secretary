"""
accounts.py
===========
Purpose : Connect Google (Gmail and Calendar) from the Cassiopeia window, and report
          the state of every connection, so the classic dashboard is no longer needed.
Location: cassiopeia/accounts.py
Used by : cassiopeia/server.py
How     : Pressing Connect opens Google's sign-in page in your browser. Cassiopeia waits in
          the background for you to finish, then saves token.json. Nothing here prints or
          returns a token.
"""

import json
import threading
import time

import config
from database import database as db

_login = {"state": "idle", "detail": "", "started": 0.0}     # shared between the request and the login thread
_lock = threading.Lock()

SCOPE_NAMES = {
    "https://www.googleapis.com/auth/gmail.readonly": "read Gmail",
    "https://www.googleapis.com/auth/gmail.compose": "save Gmail drafts",
    "https://www.googleapis.com/auth/gmail.send": "email you",
    "https://www.googleapis.com/auth/calendar.readonly": "read Calendar",
    "https://www.googleapis.com/auth/calendar.events": "add Calendar events",
}


def _saved_scopes():
    try:
        return json.loads(config.GOOGLE_TOKEN_PATH.read_text()).get("scopes") or []
    except (OSError, ValueError):
        return []


def google_status():
    """What the Control page shows. Never includes the token itself."""
    from services import google_auth
    saved = _saved_scopes()
    missing = [SCOPE_NAMES.get(s, s) for s in config.GOOGLE_SCOPES if s not in saved]
    if not google_auth.is_configured():
        state, advice = "no client file", "credentials.json is missing. See SETUP_GUIDE.md, step on Google Cloud."
    elif not saved:
        state, advice = "not connected", "Press Connect Google and sign in."
    elif missing:
        state, advice = "needs more permission", "A setting in .env needs: " + ", ".join(missing) + ". Press Reconnect."
    else:
        state, advice = "connected", ""
    with _lock:
        login = dict(_login)
    return {"state": state, "advice": advice, "can": [SCOPE_NAMES.get(s, s) for s in saved],
            "missing": missing, "login": login, "last_sync_minutes": _minutes_since_sync()}


def _minutes_since_sync():
    last = db.get_setting("last_sync")
    return None if not last else round((time.time() - last) / 60)


def _run_login():
    from services import google_auth
    try:
        if config.GOOGLE_TOKEN_PATH.exists() and not google_auth.has_token():
            # The saved login lacks a permission now needed: keep it as a backup and start fresh
            config.GOOGLE_TOKEN_PATH.rename(config.GOOGLE_TOKEN_PATH.with_name("token.previous.json"))
        google_auth.get_credentials(interactive=True)      # opens the browser and waits for you
        result = ("done", "Connected. Gmail and Calendar will refresh on the next check.")
        db.cache_clear("cass_events:")
    except Exception as problem:
        backup = config.GOOGLE_TOKEN_PATH.with_name("token.previous.json")
        if backup.exists() and not config.GOOGLE_TOKEN_PATH.exists():
            backup.rename(config.GOOGLE_TOKEN_PATH)        # put the old login back so nothing is lost
        result = ("failed", f"Sign-in did not finish, the previous login was kept: {str(problem)[:200]}")
    with _lock:
        _login.update(state=result[0], detail=result[1])


def connect_google(force=False):
    """Start a sign-in in the background. force=True signs in again even if already connected."""
    with _lock:
        if _login["state"] == "waiting" and time.time() - _login["started"] < 300:
            return {"started": False, "detail": "A sign-in is already open in your browser."}
        if force and config.GOOGLE_TOKEN_PATH.exists():
            config.GOOGLE_TOKEN_PATH.rename(config.GOOGLE_TOKEN_PATH.with_name("token.previous.json"))
        _login.update(state="waiting", detail="Finish signing in in the browser window that opened.", started=time.time())
    threading.Thread(target=_run_login, name="google-login", daemon=True).start()
    return {"started": True, "detail": _login["detail"]}
