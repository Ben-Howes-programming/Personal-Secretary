"""
state.py
========
Purpose : Shared, cached access to the outside world for every page: Google
          services, merged calendar events, the inbox sync, and your preferences.
Location: ui/state.py
Used by : app.py and every file in views/
Note    : Results are cached for five minutes, so moving between pages does not
          call Google again. The Refresh button in the sidebar clears the cache.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

import config
from database import database as db
from services import apple, google_auth, inbox, microsoft
from services import calendar as cal
from services import gmail

ZONE = ZoneInfo(config.TIMEZONE)

PREFERENCE_DEFAULTS = {
    "bedtime": config.BEDTIME_TARGET, "sleep_target": config.SLEEP_TARGET_HOURS,
    "gym_days": config.GYM_DAYS_PER_WEEK, "run_days": config.RUN_DAYS_PER_WEEK,
    "train_time": "evening", "speak_replies": False, "overdraft_clear_by": "2029-07-01",
}


def now():
    return datetime.now(ZONE)


def pref(key):
    """A preference you set in the app, falling back to the default in config.py."""
    return db.get_setting(f"pref_{key}", PREFERENCE_DEFAULTS.get(key))


def set_pref(key, value):
    db.set_setting(f"pref_{key}", value)


# ------------------------------------------------------------------
# Google
# ------------------------------------------------------------------
def google_ready():
    return google_auth.is_configured() and google_auth.has_token()


@st.cache_resource(show_spinner=False)
def _gmail_service():
    return gmail.get_gmail_service(interactive=False)


@st.cache_resource(show_spinner=False)
def _calendar_service():
    return cal.get_calendar_service(interactive=False)


def gmail_service():
    """The Gmail connection, or None when Google is not connected."""
    if not google_ready():
        return None
    try:
        return _gmail_service()
    except Exception as error:
        st.session_state["google_error"] = str(error)
        return None


def calendar_service():
    if not google_ready():
        return None
    try:
        return _calendar_service()
    except Exception as error:
        st.session_state["google_error"] = str(error)
        return None


def connect_google():
    """Opens the Google sign-in page in your browser. Called by the Connect button."""
    google_auth.get_credentials(interactive=True)
    st.cache_resource.clear()
    st.cache_data.clear()


# ------------------------------------------------------------------
# Calendar events from every connected account
# ------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def _events(start_iso, end_iso):
    start, end = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)
    events, errors = [], []
    service = calendar_service()
    if service is not None:
        try:
            events += cal.get_calendar_for_period(service, start, end)
        except Exception as error:
            errors.append(f"Google Calendar: {str(error)[:160]}")
    for name, connected, fetch in (("Outlook", microsoft.is_connected, microsoft.list_events),
                                   ("iCloud", apple.calendar_configured, apple.list_events)):
        try:
            if connected():
                events += fetch(start, end)
        except Exception as error:
            errors.append(f"{name}: {str(error)[:160]}")
    events.sort(key=lambda event: cal.event_to_datetime(event)[0] or start)
    return events, errors


def events_between(start, end):
    """Events between two datetimes, merged across accounts. Returns (events, errors)."""
    return _events(start.isoformat(), end.isoformat())


def midnight(offset_days=0):
    return now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset_days)


def week_events():
    return events_between(midnight(), midnight(7))[0]


def events_on(day, events):
    """The subset of `events` that touch a given date."""
    start = datetime(day.year, day.month, day.day, tzinfo=ZONE)
    end = start + timedelta(days=1)
    chosen = []
    for event in events:
        event_start, event_end = cal.event_to_datetime(event)
        if event_start and event_start < end and event_end > start:
            chosen.append(event)
    return chosen


def any_calendar():
    return google_ready() or microsoft.is_connected() or apple.calendar_configured()


# ------------------------------------------------------------------
# Inbox
# ------------------------------------------------------------------
def any_mail():
    return google_ready() or microsoft.is_connected() or apple.mail_configured()


def sync_inbox(force=False):
    """Fetch and analyse new mail if the last sync is old enough, or always when forced."""
    if not any_mail():
        return None
    age = inbox.minutes_since_sync()
    if not force and age is not None and age < config.AUTO_SYNC_MINUTES:
        return None
    with st.spinner("Checking mail"):
        return inbox.sync(gmail_service())


def sync_caption():
    age = inbox.minutes_since_sync()
    if age is None:
        return "Mail has not been checked yet."
    stats = db.get_setting("last_sync_stats", {}) or {}
    waiting = f", {stats.get('pending')} waiting for analysis" if stats.get("pending") else ""
    when = "just now" if age < 1 else (f"{age:.0f} min ago" if age < 90 else f"{age / 60:.0f} h ago")
    return f"Mail checked {when}{waiting}."
