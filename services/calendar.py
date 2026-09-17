import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly"
]

UK_TIMEZONE = ZoneInfo("Europe/London")


def get_calendar_service():
    credentials = None

    if os.path.exists("token.json"):
        credentials = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json",
            SCOPES
        )

        credentials = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(credentials.to_json())

    return build(
        "calendar",
        "v3",
        credentials=credentials
    )


def get_upcoming_events(calendar_service, max_results=10):
    now = datetime.now(UK_TIMEZONE)

    events_result = calendar_service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


def get_calendar_for_period(
    calendar_service,
    start_dt,
    end_dt
):
    """
    Return all calendar events overlapping a period.
    """

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(
            tzinfo=UK_TIMEZONE
        )

    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(
            tzinfo=UK_TIMEZONE
        )

    events_result = calendar_service.events().list(
        calendarId="primary",
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


def event_to_datetime(event):
    """
    Convert a Google Calendar event start/end value
    into a timezone-aware datetime.
    """

    start = event["start"].get(
        "dateTime",
        event["start"].get("date")
    )

    end = event["end"].get(
        "dateTime",
        event["end"].get("date")
    )

    if not start or not end:
        return None, None

    if "T" in start:

        event_start = datetime.fromisoformat(
            start
        )

        event_end = datetime.fromisoformat(
            end
        )

        if event_start.tzinfo is None:
            event_start = event_start.replace(
                tzinfo=UK_TIMEZONE
            )

        if event_end.tzinfo is None:
            event_end = event_end.replace(
                tzinfo=UK_TIMEZONE
            )

    else:
        # Google all-day events use an exclusive
        # end date. Treat them as UK-local dates.
        event_start = datetime.fromisoformat(
            start
        ).replace(
            tzinfo=UK_TIMEZONE
        )

        event_end = datetime.fromisoformat(
            end
        ).replace(
            tzinfo=UK_TIMEZONE
        )

    return event_start, event_end


def find_free_slots(
    calendar_service,
    start_dt,
    end_dt,
    lesson_minutes=60
):
    """
    Find individual available lesson slots.

    For example, if 12:00–18:00 is completely free
    and lesson_minutes is 60, return:

        12:00–13:00
        13:00–14:00
        14:00–15:00
        15:00–16:00
        16:00–17:00
        17:00–18:00

    Calendar events are treated as unavailable time.
    """

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(
            tzinfo=UK_TIMEZONE
        )

    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(
            tzinfo=UK_TIMEZONE
        )

    events = get_calendar_for_period(
        calendar_service,
        start_dt,
        end_dt
    )

    busy_periods = []

    for event in events:

        event_start, event_end = (
            event_to_datetime(event)
        )

        if event_start is None:
            continue

        # Ignore events completely outside our
        # requested period.
        if event_end <= start_dt:
            continue

        if event_start >= end_dt:
            continue

        # Clip events to our requested period.
        event_start = max(
            event_start,
            start_dt
        )

        event_end = min(
            event_end,
            end_dt
        )

        busy_periods.append(
            (event_start, event_end)
        )

    # Sort events chronologically.
    busy_periods.sort(
        key=lambda period: period[0]
    )

    # Merge overlapping events.
    merged_busy = []

    for busy_start, busy_end in busy_periods:

        if not merged_busy:

            merged_busy.append(
                [busy_start, busy_end]
            )

            continue

        previous_start, previous_end = (
            merged_busy[-1]
        )

        if busy_start <= previous_end:

            merged_busy[-1][1] = max(
                previous_end,
                busy_end
            )

        else:

            merged_busy.append(
                [busy_start, busy_end]
            )

    # Work out the free ranges.
    free_ranges = []

    current = start_dt

    for busy_start, busy_end in merged_busy:

        if busy_start > current:

            free_ranges.append(
                (current, busy_start)
            )

        if busy_end > current:

            current = busy_end

    if current < end_dt:

        free_ranges.append(
            (current, end_dt)
        )

    # Turn free ranges into actual lesson slots.
    lesson_delta = timedelta(
        minutes=lesson_minutes
    )

    lesson_slots = []

    for free_start, free_end in free_ranges:

        slot_start = free_start

        while (
            slot_start + lesson_delta
            <= free_end
        ):

            slot_end = (
                slot_start
                + lesson_delta
            )

            lesson_slots.append(
                (slot_start, slot_end)
            )

            slot_start = slot_end

    return lesson_slots


def format_calendar_events(events):
    formatted = []

    for event in events:

        start = event["start"].get(
            "dateTime",
            event["start"].get("date")
        )

        end = event["end"].get(
            "dateTime",
            event["end"].get("date")
        )

        if not start:
            continue

        if "T" in start:

            start_dt = datetime.fromisoformat(
                start
            )

            end_dt = datetime.fromisoformat(
                end
            )

            start_text = start_dt.strftime(
                "%a %d %b, %H:%M"
            )

            end_text = end_dt.strftime(
                "%H:%M"
            )

            formatted.append(
                f"{start_text}–{end_text} — "
                f"{event.get('summary', 'Untitled')}"
            )

        else:

            formatted.append(
                f"{start} — "
                f"{event.get('summary', 'Untitled')}"
            )

    return formatted