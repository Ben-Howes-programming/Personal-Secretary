import os
import base64
import json
import sqlite3

from datetime import datetime, timedelta

from database.database import (
    initialise_database,
    save_email,
    email_is_cached,
    get_cached_email
)

from dotenv import load_dotenv
from anthropic import Anthropic
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


# ============================================================
# CONFIGURATION
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

DB_FILE = "secretary.db"
MAX_EMAILS = 20
DEFAULT_LESSON_MINUTES = 60

DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


# ============================================================
# GOOGLE SERVICES
# ============================================================

def get_google_services():
    credentials = None

    if os.path.exists("token.json"):
        credentials = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES,
        )

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json",
            SCOPES,
        )

        credentials = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(credentials.to_json())

    gmail = build(
        "gmail",
        "v1",
        credentials=credentials,
    )

    calendar = build(
        "calendar",
        "v3",
        credentials=credentials,
    )

    return gmail, calendar


# ============================================================
# GMAIL
# ============================================================

def decode_base64(data):
    return base64.urlsafe_b64decode(data).decode(
        "utf-8",
        errors="replace",
    )


def get_email_body(payload):
    # Simple message with a body directly on the payload.
    body_data = payload.get("body", {}).get("data")

    if body_data:
        return decode_base64(body_data)

    # Multipart messages.
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")

            if data:
                return decode_base64(data)

        # Some emails contain nested multipart sections.
        if part.get("parts"):
            nested_body = get_email_body(part)

            if nested_body != "[No plain-text body found]":
                return nested_body

    return "[No plain-text body found]"


def get_email(gmail, message_id):
    email = gmail.users().messages().get(
        userId="me",
        id=message_id,
        format="full",
    ).execute()

    headers = email["payload"]["headers"]
    email_info = {}

    for header in headers:
        email_info[header["name"]] = header["value"]

    return {
        "sender": email_info.get("From", "Unknown"),
        "subject": email_info.get("Subject", "No subject"),
        "date": email_info.get("Date", "Unknown"),
        "body": get_email_body(email["payload"]),
    }


# ============================================================
# CLAUDE EMAIL ANALYSIS
# ============================================================

def clean_json_response(text):
    text = text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "", 1)
        text = text.replace("```", "", 1)
        text = text.strip()

    return text


def analyse_email(client, email):
    today = datetime.now().astimezone().strftime(
        "%A, %d %B %Y"
    )

    prompt = f"""
You are a careful personal secretary analysing an email for Ben.

Your job is to help Ben identify emails that genuinely require his attention.
Do not treat an email as requiring action merely because it contains information.

TODAY'S DATE
{today}

EMAIL
From: {email['sender']}
Subject: {email['subject']}
Date: {email['date']}

Body:
{email['body']}

Return ONLY valid JSON with exactly these nine fields:

{{
    "category": "Tutoring",
    "priority": "Medium",
    "action_required": true,
    "reply_needed": true,
    "availability_request": true,
    "requested_day": "Sunday",
    "requested_start": "12:00",
    "requested_end": "17:00",
    "summary": "Someone is asking whether Ben is available for a GCSE Physics lesson on Sunday afternoon."
}}

CATEGORY
Choose exactly one:

University
Tutoring
Personal
Finance
Shopping
Newsletter
Marketing
Work
Travel
Other

PRIORITY

High:
The email is genuinely important or time-sensitive and should probably
be dealt with soon.

Medium:
The email requires some attention but is not urgent.

Low:
The email is useful information but does not need prompt attention.

ACTION REQUIRED

Set this to true ONLY when Ben actually needs to do something.

Examples:
- Someone asks Ben a question → true
- Someone asks Ben to confirm something → true
- A university deadline requires work → true
- A receipt arrives → false
- A newsletter arrives → false
- Marketing arrives → false
- An automated notification that requires no response → false

REPLY NEEDED

Set this to true ONLY when Ben would reasonably be expected
to reply to the sender.

Examples:
- Someone asks Ben a direct question → true
- Someone asks Ben to confirm something → true
- A parent enquires about a tutoring lesson → true
- A university announces a deadline → false
- A receipt arrives → false
- A newsletter arrives → false
- Marketing email → false

If action_required is false, reply_needed must also be false.

AVAILABILITY REQUEST

Set this to true ONLY when the sender is asking about Ben's availability
for a particular date or time period.

Examples:
- "Are you free Sunday afternoon?" → true
- "Can you do Tuesday at 4pm?" → true
- "Would you be available sometime next week?" → true
- "Thanks for confirming Sunday's lesson." → false
- "Here are the details for Sunday's lesson." → false
- "Your lecture is cancelled." → false

If the email does not ask about Ben's availability, set this to false.

REQUESTED TIME

When availability_request is true, identify the requested period.

requested_day:
Give the day mentioned by the sender, such as "Sunday" or "Tuesday".
If no specific day is given, use null.

requested_start:
Give the requested start time in 24-hour HH:MM format.
For broad periods use:
- morning: 09:00
- afternoon: 12:00
- evening: 17:00

requested_end:
Give the requested end time in 24-hour HH:MM format.
For broad periods use:
- morning: 12:00
- afternoon: 17:00
- evening: 21:00

If the sender gives an exact time, use that time and assume a one-hour
period unless the email specifies a duration.

If you cannot determine the requested period, use null.

Do not guess a specific date when the email is ambiguous.

SUMMARY

Summarise the important information in no more than three sentences.
Focus on what Ben actually needs to know or do.

Do not include markdown.
Do not include ```json.
Return only the JSON object.
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    for block in message.content:
        if block.type == "text":
            raw_text = block.text
            cleaned_text = clean_json_response(raw_text)

            try:
                analysis = json.loads(cleaned_text)

                # Basic validation/defaults so a malformed analysis
                # does not break the rest of the programme.
                analysis.setdefault("action_required", False)
                analysis.setdefault("reply_needed", False)
                analysis.setdefault("availability_request", False)

                if not analysis["action_required"]:
                    analysis["reply_needed"] = False

                return analysis

            except json.JSONDecodeError:
                return {
                    "error": "Claude returned invalid JSON",
                    "raw_response": raw_text,
                    "action_required": False,
                    "reply_needed": False,
                    "availability_request": False,
                    "summary": "The email could not be analysed.",
                }

    return {
        "error": "Claude returned no text response",
        "action_required": False,
        "reply_needed": False,
        "availability_request": False,
        "summary": "The email could not be analysed.",
    }

# ============================================================
# CALENDAR
# ============================================================

def get_upcoming_events(calendar_service, max_results=10):
    now = datetime.now().astimezone()

    events_result = calendar_service.events().list(
        calendarId="primary",
        maxResults=max_results,
        timeMin=now.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return events_result.get("items", [])


def format_calendar_events(events):
    formatted = []

    for event in events:
        start = event["start"].get(
            "dateTime",
            event["start"].get("date"),
        )

        end = event["end"].get(
            "dateTime",
            event["end"].get("date"),
        )

        if not start:
            continue

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


def get_calendar_for_period(calendar_service, start_dt, end_dt):
    events_result = calendar_service.events().list(
        calendarId="primary",
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return events_result.get("items", [])


def get_next_occurrence(day_name):
    today = datetime.now().astimezone()

    if day_name not in DAY_NAMES:
        return None

    target_weekday = DAY_NAMES.index(day_name)

    days_ahead = (
        target_weekday - today.weekday()
    ) % 7

    # "Sunday" in an email received on Sunday means the upcoming
    # Sunday rather than a time already partly passed.
    if days_ahead == 0:
        days_ahead = 7

    return today + timedelta(days=days_ahead)


def parse_time(time_text):
    if not time_text:
        return None

    try:
        hour = int(time_text[:2])
        minute = int(time_text[3:5])

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        return hour, minute

    except (ValueError, TypeError):
        return None


def get_availability_for_request(calendar_service, analysis):
    requested_day = analysis.get("requested_day")
    requested_start = analysis.get("requested_start")
    requested_end = analysis.get("requested_end")

    if not requested_day:
        return None

    start_time = parse_time(requested_start)
    end_time = parse_time(requested_end)

    if not start_time or not end_time:
        return None

    requested_date = get_next_occurrence(requested_day)

    if requested_date is None:
        return None

    start_dt = requested_date.replace(
        hour=start_time[0],
        minute=start_time[1],
        second=0,
        microsecond=0,
    )

    end_dt = requested_date.replace(
        hour=end_time[0],
        minute=end_time[1],
        second=0,
        microsecond=0,
    )

    if end_dt <= start_dt:
        return None

    events = get_calendar_for_period(
        calendar_service,
        start_dt,
        end_dt,
    )

    return {
        "date": requested_date.strftime(
            "%A %d %B %Y"
        ),
        "start": requested_start,
        "end": requested_end,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "events": events,
    }


def find_free_slots(
    calendar_service,
    start_dt,
    end_dt,
    lesson_minutes=DEFAULT_LESSON_MINUTES,
):
    events = get_calendar_for_period(
        calendar_service,
        start_dt,
        end_dt,
    )

    busy_periods = []

    for event in events:
        start = event["start"].get("dateTime")
        end = event["end"].get("dateTime")

        # Ignore all-day events here for now. They are not represented
        # as a timed period by Google Calendar.
        if not start or not end:
            continue

        event_start = datetime.fromisoformat(start)
        event_end = datetime.fromisoformat(end)

        # Clip events to the requested window.
        event_start = max(event_start, start_dt)
        event_end = min(event_end, end_dt)

        if event_start < event_end:
            busy_periods.append(
                (event_start, event_end)
            )

    busy_periods.sort(key=lambda period: period[0])

    # Merge overlapping calendar events.
    merged_busy = []

    for event_start, event_end in busy_periods:
        if not merged_busy:
            merged_busy.append(
                [event_start, event_end]
            )
            continue

        previous_start, previous_end = merged_busy[-1]

        if event_start <= previous_end:
            merged_busy[-1][1] = max(
                previous_end,
                event_end,
            )
        else:
            merged_busy.append(
                [event_start, event_end]
            )

    free_slots = []
    current_time = start_dt
    lesson_delta = timedelta(minutes=lesson_minutes)

    for event_start, event_end in merged_busy:
        if event_start - current_time >= lesson_delta:
            free_slots.append(
                (current_time, event_start)
            )

        if event_end > current_time:
            current_time = event_end

    if end_dt - current_time >= lesson_delta:
        free_slots.append(
            (current_time, end_dt)
        )

    return free_slots


def get_requested_free_slots(
    calendar_service,
    availability,
    lesson_minutes=DEFAULT_LESSON_MINUTES,
):
    if not availability:
        return []

    return find_free_slots(
        calendar_service,
        availability["start_dt"],
        availability["end_dt"],
        lesson_minutes=lesson_minutes,
    )


def describe_calendar_availability(availability):
    if not availability:
        return "No calendar availability information was found."

    events = availability["events"]

    if not events:
        return (
            f"Ben has no calendar events between "
            f"{availability['start']} and {availability['end']} "
            f"on {availability['date']}."
        )

    lines = [
        f"Calendar events on {availability['date']} "
        f"between {availability['start']} and {availability['end']}:"
    ]

    for event in events:
        start = event["start"].get("dateTime")
        end = event["end"].get("dateTime")

        if start and end:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)

            lines.append(
                f"- {start_dt.strftime('%H:%M')}–"
                f"{end_dt.strftime('%H:%M')}: "
                f"{event.get('summary', 'Untitled')}"
            )
        elif event["start"].get("date"):
            lines.append(
                f"- All day: "
                f"{event.get('summary', 'Untitled')}"
            )

    return "\n".join(lines)


def describe_free_slots(free_slots):
    if not free_slots:
        return "No one-hour tutoring slots are available."

    lines = []

    for start, end in free_slots:
        lines.append(
            f"- {start.strftime('%H:%M')}–"
            f"{end.strftime('%H:%M')}"
        )

    return "\n".join(lines)


# ============================================================
# EMAIL DRAFTING
# ============================================================

def draft_reply(
    client,
    email,
    availability=None,
    free_slots=None,
):
    calendar_context = "No calendar availability was checked."

    if availability:
        calendar_context = (
            f"Requested period: {availability['date']}, "
            f"{availability['start']}–{availability['end']}.\n"
            f"Calendar events:\n"
            f"{describe_calendar_availability(availability)}\n\n"
            f"One-hour tutoring slots:\n"
            f"{describe_free_slots(free_slots or [])}"
        )

    prompt = f"""
You are drafting an email reply on behalf of Ben.

Write a natural, concise and polite reply to the email below.

EMAIL
From: {email['sender']}
Subject: {email['subject']}

Body:
{email['body']}

CALENDAR INFORMATION
{calendar_context}

IMPORTANT RULES:

- Write only the reply itself.
- Do not include analysis or explanations.
- Do not invent facts, commitments, dates, prices or availability.
- Use the calendar information as the source of truth for availability.
- If one-hour tutoring slots are listed, you may offer those slots.
- Do not claim Ben is available at a time that is not listed as a free slot.
- If no free slots are listed, do not say that Ben is available.
- If the requested period was not successfully interpreted, use a
  sensible placeholder such as [availability] rather than guessing.
- If the email asks for information that Ben has not provided, use a
  sensible placeholder rather than making it up.
- Match the level of formality of the original email.
- Keep the reply concise.
- Do not mention the calendar or this instruction.
- Sign off exactly as:

Best,
Ben
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    for block in message.content:
        if block.type == "text":
            return block.text.strip()

    return "[Claude returned no draft]"


# ============================================================
# BRIEFING
# ============================================================

def create_briefing(emails):
    priority_order = {
        "High": 1,
        "Medium": 2,
        "Low": 3,
    }

    action_required = []
    no_action_required = []

    for email in emails:
        analysis = email.get("analysis", {})

        if analysis.get("action_required"):
            action_required.append(email)
        else:
            no_action_required.append(email)

    action_required.sort(
        key=lambda email: priority_order.get(
            email.get("analysis", {}).get("priority"),
            99,
        )
    )

    print("\n")
    print("=" * 70)
    print("BEN'S INBOX BRIEFING")
    print("=" * 70)

    print(f"\n{len(emails)} emails checked")
    print(f"{len(action_required)} require your attention")

    if action_required:
        print("\n" + "!" * 70)
        print("REQUIRES YOUR ATTENTION")
        print("!" * 70)

        for email in action_required:
            analysis = email["analysis"]

            priority = analysis.get(
                "priority",
                "Unknown",
            )

            print(
                f"\n[{priority.upper()}] "
                f"{analysis.get('category', 'Unknown')}"
            )

            print(f"From: {email['sender']}")
            print(f"Subject: {email['subject']}")
            print(
                f"→ {analysis.get('summary', 'No summary')}"
            )

    if no_action_required:
        print("\n" + "-" * 70)
        print("NO ACTION REQUIRED")
        print("-" * 70)

        for email in no_action_required:
            analysis = email["analysis"]

            print(
                f"\n{analysis.get('category', 'Unknown')} — "
                f"{email['subject']}"
            )

            print(
                f"→ {analysis.get('summary', 'No summary')}"
            )

    print("\n" + "=" * 70)


# ============================================================
# MAIN
# ============================================================

def process_email(
    client,
    gmail,
    calendar_service,
    message_id,
    free_slots_for_sunday,
):
    # --------------------------------------------------------
    # Cached email
    # --------------------------------------------------------

    if email_is_cached(message_id):
        print(f"Using cached analysis: {message_id}")

        email = get_cached_email(message_id)

        if email is None:
            return None

        analysis = email["analysis"]

        # Older database rows did not store the requested time.
        # Reanalyse only when we need that information.
        if (
            analysis.get("availability_request")
            and (
                not analysis.get("requested_day")
                or not analysis.get("requested_start")
                or not analysis.get("requested_end")
            )
        ):
            print(
                f"Reanalysing availability request: "
                f"{email['subject']}"
            )

            analysis = analyse_email(
                client,
                email,
            )

            email["analysis"] = analysis
            email["draft_reply"] = None
            save_email(email)

        if analysis.get("reply_needed"):
            availability = None
            requested_free_slots = None

            if analysis.get("availability_request"):
                availability = get_availability_for_request(
                    calendar_service,
                    analysis,
                )

                if availability:
                    requested_free_slots = (
                        get_requested_free_slots(
                            calendar_service,
                            availability,
                        )
                    )

                    print("\nCALENDAR AVAILABILITY:")
                    print("-" * 70)
                    print(
                        f"{availability['date']}"
                    )
                    print(
                        f"Requested period: "
                        f"{availability['start']}–"
                        f"{availability['end']}"
                    )
                    print(
                        f"\nOne-hour tutoring slots:"
                    )
                    print(
                        describe_free_slots(
                            requested_free_slots
                        )
                    )
                    print("-" * 70)

            draft = draft_reply(
                client,
                email,
                availability,
                requested_free_slots,
            )

            email["draft_reply"] = draft
            save_email(email)

            print("\nDRAFT REPLY:")
            print("-" * 70)
            print(draft)
            print("-" * 70)

        return email

    # --------------------------------------------------------
    # New email
    # --------------------------------------------------------

    email = get_email(
        gmail,
        message_id,
    )

    print(
        f"Analysing: {email['subject']}"
    )

    analysis = analyse_email(
        client,
        email,
    )

    print("\nDEBUG — CLAUDE ANALYSIS:")
    print(
        json.dumps(
            analysis,
            indent=2,
        )
    )

    email["id"] = message_id
    email["analysis"] = analysis

    save_email(email)

    if analysis.get("reply_needed"):
        availability = None
        requested_free_slots = None

        if analysis.get("availability_request"):
            availability = get_availability_for_request(
                calendar_service,
                analysis,
            )

            if availability:
                requested_free_slots = (
                    get_requested_free_slots(
                        calendar_service,
                        availability,
                    )
                )

                print("\nCALENDAR AVAILABILITY:")
                print("-" * 70)
                print(
                    f"{availability['date']}"
                )
                print(
                    f"Requested period: "
                    f"{availability['start']}–"
                    f"{availability['end']}"
                )
                print(
                    "\nOne-hour tutoring slots:"
                )
                print(
                    describe_free_slots(
                        requested_free_slots
                    )
                )
                print("-" * 70)

        draft = draft_reply(
            client,
            email,
            availability,
            requested_free_slots,
        )

        email["draft_reply"] = draft
        save_email(email)

        print("\nDRAFT REPLY:")
        print("-" * 70)
        print(draft)
        print("-" * 70)

    return email


def main():
    load_dotenv()

    client = Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"]
    )

    initialise_database()

    gmail, calendar_service = get_google_services()

    # --------------------------------------------------------
    # Upcoming calendar
    # --------------------------------------------------------

    print("\nCALENDAR TEST")
    print("=" * 70)

    events = get_upcoming_events(
        calendar_service
    )

    formatted_events = format_calendar_events(
        events
    )

    if not formatted_events:
        print("No upcoming events found.")
    else:
        for event in formatted_events:
            print(event)

    # --------------------------------------------------------
    # Sunday afternoon test / tutoring availability
    # --------------------------------------------------------

    today = datetime.now().astimezone()

    days_until_sunday = (
        6 - today.weekday()
    ) % 7

    if days_until_sunday == 0:
        days_until_sunday = 7

    sunday = today + timedelta(
        days=days_until_sunday
    )

    sunday_start = sunday.replace(
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )

    sunday_end = sunday.replace(
        hour=18,
        minute=0,
        second=0,
        microsecond=0,
    )

    events = get_calendar_for_period(
        calendar_service,
        sunday_start,
        sunday_end,
    )

    print("\nSUNDAY AFTERNOON")
    print("=" * 70)

    if not events:
        print(
            "No events scheduled between "
            "12:00 and 18:00."
        )
    else:
        for event in events:
            start = event["start"].get(
                "dateTime",
                event["start"].get("date"),
            )

            end = event["end"].get(
                "dateTime",
                event["end"].get("date"),
            )

            print(
                f"{start} – {end} — "
                f"{event.get('summary', 'Untitled')}"
            )

    free_slots_for_sunday = find_free_slots(
        calendar_service,
        sunday_start,
        sunday_end,
        lesson_minutes=DEFAULT_LESSON_MINUTES,
    )

    print("\nFREE TUTORING SLOTS")
    print("=" * 70)

    if not free_slots_for_sunday:
        print("No one-hour slots available.")
    else:
        for slot_start, slot_end in free_slots_for_sunday:
            print(
                f"{slot_start.strftime('%H:%M')}–"
                f"{slot_end.strftime('%H:%M')}"
            )

    # --------------------------------------------------------
    # Gmail
    # --------------------------------------------------------

    results = gmail.users().messages().list(
        userId="me",
        maxResults=MAX_EMAILS,
    ).execute()

    messages = results.get(
        "messages",
        [],
    )

    emails = []

    for message in messages:
        email = process_email(
            client,
            gmail,
            calendar_service,
            message["id"],
            free_slots_for_sunday,
        )

        if email:
            emails.append(email)

    create_briefing(emails)


if __name__ == "__main__":
    main()
