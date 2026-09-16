import os
from datetime import datetime, timedelta

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly"
]


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
    events_result = calendar_service.events().list(
        calendarId="primary",
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
    events_result = calendar_service.events().list(
        calendarId="primary",
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


def find_free_slots(
    calendar_service,
    start_dt,
    end_dt,
    lesson_minutes=60
):
    events = get_calendar_for_period(
        calendar_service,
        start_dt,
        end_dt
    )

    busy_periods = []

    for event in events:
        start = event["start"].get(
            "dateTime",
            event["start"].get("date")
        )

        end = event["end"].get(
            "dateTime",
            event["end"].get("date")
        )

        if not start or not end:
            continue

        if "T" in start:
            event_start = datetime.fromisoformat(start)
            event_end = datetime.fromisoformat(end)
        else:
            event_start = datetime.fromisoformat(
                start + "T00:00:00"
            )
            event_end = datetime.fromisoformat(
                end + "T00:00:00"
            )

        busy_periods.append(
            (event_start, event_end)
        )

    busy_periods.sort()

    free_slots = []
    current = start_dt

    for busy_start, busy_end in busy_periods:

        if busy_start > current:
            gap_minutes = (
                busy_start - current
            ).total_seconds() / 60

            if gap_minutes >= lesson_minutes:
                free_slots.append(
                    (current, busy_start)
                )

        if busy_end > current:
            current = busy_end

    if current < end_dt:
        gap_minutes = (
            end_dt - current
        ).total_seconds() / 60

        if gap_minutes >= lesson_minutes:
            free_slots.append(
                (current, end_dt)
            )

    return free_slots


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

        if "T" in start:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)

            start_text = start_dt.strftime(
                "%a %d %b, %H:%M"
            )
            end_text = end_dt.strftime("%H:%M")

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