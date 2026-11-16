"""
events.py
=========
Purpose : One list of events from every calendar (Google, Outlook, iCloud) plus the
          events Cassiopeia planned for you locally. No Streamlit needed.
Location: cassiopeia/events.py
Used by : cassiopeia/briefing.py, cassiopeia/brain.py, cassiopeia/server.py
Note    : Every event uses Google's shape, as the rest of the project does.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
from cassiopeia import store
from database import database as db
from services import calendar as cal

ZONE = ZoneInfo(config.TIMEZONE)


def now():
    return datetime.now(ZONE)


def midnight(offset_days=0):
    return now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset_days)


def _local_events(start, end):
    """Events you asked Cassiopeia to plan, converted to Google's shape."""
    converted = []
    for row in store.events_between(start.replace(tzinfo=None).isoformat(), end.replace(tzinfo=None).isoformat()):
        begins = datetime.fromisoformat(row["start_iso"]).replace(tzinfo=ZONE)
        finishes = (datetime.fromisoformat(row["end_iso"]).replace(tzinfo=ZONE) if row["end_iso"]
                    else begins + timedelta(hours=1))
        converted.append({"summary": row["title"], "description": row["notes"], "source": "Cassiopeia",
                          "local_id": row["id"], "start": {"dateTime": begins.isoformat()},
                          "end": {"dateTime": finishes.isoformat()}})
    return converted


def _remote_events(start, end):
    """Events from connected accounts. A broken account adds an error, never a crash."""
    found, errors = [], []
    try:
        from services import google_auth
        if google_auth.is_configured() and google_auth.has_token():
            service = cal.get_calendar_service(interactive=False)   # never opens a browser from a background job
            found += cal.get_calendar_for_period(service, start, end)
    except Exception as problem:
        errors.append(f"Google Calendar: {str(problem)[:140]}")
    for name, module in (("Outlook", "microsoft"), ("iCloud", "apple")):
        try:
            service = __import__(f"services.{module}", fromlist=[module])
            connected = service.is_connected if module == "microsoft" else service.calendar_configured
            if connected():
                found += service.list_events(start, end)
        except Exception as problem:
            errors.append(f"{name}: {str(problem)[:140]}")
    return found, errors


def between(start, end, force=False):
    """(events, errors) between two datetimes, soonest first. Remote calendars are cached 5 minutes."""
    key = f"cass_events:{start.isoformat()}:{end.isoformat()}"
    cached = None if force else db.cache_get(key)
    if cached is None:
        remote, errors = _remote_events(start, end)
        db.cache_set(key, {"events": remote, "errors": errors}, 300)
    else:
        remote, errors = cached["events"], cached["errors"]
    merged = remote + _local_events(start, end)
    merged.sort(key=lambda event: cal.event_to_datetime(event)[0] or start)
    return merged, errors


def upcoming(days=7):
    return between(midnight(), midnight(days))


def lines(event_list, limit=12):
    """'Tuesday 17 November: 09:15 to 10:05  Vector calculus lecture' for prompts and messages."""
    return [f"{cal.event_day(event)}: {cal.describe_event(event)}" for event in event_list[:limit]]


def parse_when(text):
    """Accept '2026-11-20T14:00', '2026-11-20 14:00' or '2026-11-20'. Returns naive ISO text or None."""
    text = (text or "").strip().replace(" ", "T")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment.replace(tzinfo=None, microsecond=0).isoformat()
