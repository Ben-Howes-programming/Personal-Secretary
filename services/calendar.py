"""
calendar.py
===========
Purpose : Read Google Calendar, work out free time, and (only if switched on) add events.
Location: services/calendar.py
Used by : ui/state.py, views/calendar_view.py, views/tutoring.py, views/health.py, ai/context.py
Note    : Events from Outlook and iCloud are converted to the same shape as Google's,
          so every function here works on all three.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
from services.google_auth import build_service

UK_TIMEZONE = ZoneInfo(config.TIMEZONE)
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_calendar_service(interactive=True):
    return build_service("calendar", "v3", interactive)


# ------------------------------------------------------------------
# Reading
# ------------------------------------------------------------------
def _aware(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=UK_TIMEZONE)


def get_calendar_for_period(calendar_service, start_dt, end_dt, calendar_id="primary"):
    """All events overlapping a period, earliest first."""
    result = calendar_service.events().list(
        calendarId=calendar_id, timeMin=_aware(start_dt).isoformat(), timeMax=_aware(end_dt).isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=250,
    ).execute()
    events = result.get("items", [])
    for event in events:
        event.setdefault("source", "Google")
    return events


def event_to_datetime(event):
    """Start and end of an event as timezone-aware datetimes. All-day events use UK midnight."""
    start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
    end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date"))
    if not start or not end:
        return None, None
    try:
        start_dt, end_dt = datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        return None, None
    return _aware(start_dt).astimezone(UK_TIMEZONE), _aware(end_dt).astimezone(UK_TIMEZONE)


def is_all_day(event):
    return "dateTime" not in event.get("start", {})


def describe_event(event):
    """'09:15 to 10:05  Vector calculus lecture' or 'All day  Reading week'."""
    summary = event.get("summary", "Untitled event")
    start, end = event_to_datetime(event)
    if start is None or is_all_day(event):
        return f"All day  {summary}"
    return f"{start.strftime('%H:%M')} to {end.strftime('%H:%M')}  {summary}"


def event_day(event):
    start, _end = event_to_datetime(event)
    return start.strftime("%A %d %B") if start else "Unknown day"


def blocks_time(event):
    """All-day events and events marked 'Free' do not stop you booking something else."""
    if event.get("transparency") == "transparent":
        return False
    return not is_all_day(event)


# ------------------------------------------------------------------
# Free time
# ------------------------------------------------------------------
def free_ranges(events, start_dt, end_dt):
    """Gaps between busy events inside a window, as (start, end) pairs."""
    start_dt, end_dt = _aware(start_dt), _aware(end_dt)
    busy = []
    for event in events:
        if not blocks_time(event):
            continue
        event_start, event_end = event_to_datetime(event)
        if event_start is None or event_end <= start_dt or event_start >= end_dt:
            continue
        busy.append((max(event_start, start_dt), min(event_end, end_dt)))
    busy.sort()

    ranges, cursor = [], start_dt
    for busy_start, busy_end in busy:
        if busy_start > cursor:
            ranges.append((cursor, busy_start))
        cursor = max(cursor, busy_end)
    if cursor < end_dt:
        ranges.append((cursor, end_dt))
    return ranges


def free_slots_from_events(events, start_dt, end_dt, lesson_minutes=60):
    """Back-to-back slots of a fixed length that fit in the free gaps."""
    length = timedelta(minutes=lesson_minutes)
    slots = []
    for free_start, free_end in free_ranges(events, start_dt, end_dt):
        slot_start = free_start
        while slot_start + length <= free_end:
            slots.append((slot_start, slot_start + length))
            slot_start += length
    return slots


def find_free_slots(calendar_service, start_dt, end_dt, lesson_minutes=60):
    """Same as free_slots_from_events, but fetches the events from Google first."""
    events = get_calendar_for_period(calendar_service, start_dt, end_dt)
    return free_slots_from_events(events, start_dt, end_dt, lesson_minutes)


def parse_time(text):
    """'12:00' gives (12, 0). Returns None if the text is missing or invalid."""
    try:
        hour, minute = int(text[:2]), int(text[3:5])
    except (TypeError, ValueError):
        return None
    return (hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def at(day, hhmm):
    """Combine a date (or datetime) with an 'HH:MM' string into an aware datetime."""
    hour, minute = parse_time(hhmm) or (0, 0)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UK_TIMEZONE)


def get_next_occurrence(day_name, now=None):
    """Next date for a weekday name. Today's weekday means a week from today."""
    if day_name not in DAY_NAMES:
        return None
    now = now or datetime.now(UK_TIMEZONE)
    days_ahead = (DAY_NAMES.index(day_name) - now.weekday()) % 7 or 7
    return now + timedelta(days=days_ahead)


def requested_window(analysis, now=None):
    """The (start, end) an email asked about, from Claude's analysis. None if unclear."""
    day = analysis.get("requested_day")
    start_time, end_time = parse_time(analysis.get("requested_start")), parse_time(analysis.get("requested_end"))
    target = get_next_occurrence(day, now) if day else None
    if not (target and start_time and end_time):
        return None
    start_dt = at(target, analysis["requested_start"])
    end_dt = at(target, analysis["requested_end"])
    return (start_dt, end_dt) if end_dt > start_dt else None


def next_weekday(weekday, now=None):
    """Date of the next given weekday (Monday is 0). Today counts."""
    now = now or datetime.now(UK_TIMEZONE)
    return now + timedelta(days=(weekday - now.weekday()) % 7)


# ------------------------------------------------------------------
# Writing (off unless ENABLE_CALENDAR_WRITE=true in .env)
# ------------------------------------------------------------------
def create_event(calendar_service, summary, start_dt, end_dt, description=""):
    if not config.ENABLE_CALENDAR_WRITE:
        raise PermissionError("Calendar writing is switched off. Set ENABLE_CALENDAR_WRITE=true in .env.")
    body = {
        "summary": summary, "description": description,
        "start": {"dateTime": _aware(start_dt).isoformat(), "timeZone": config.TIMEZONE},
        "end": {"dateTime": _aware(end_dt).isoformat(), "timeZone": config.TIMEZONE},
    }
    return calendar_service.events().insert(calendarId="primary", body=body).execute()
