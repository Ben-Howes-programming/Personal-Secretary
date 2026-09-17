import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

from services.gmail import (
    get_gmail_service,
    get_email,
)

from services.calendar import (
    get_calendar_service,
    get_calendar_for_period,
    find_free_slots,
)

from ai.claude import (
    create_client,
    analyse_email,
    draft_reply,
)

from database.database import (
    initialise_database,
    save_email,
    email_is_cached,
    get_cached_email,
    update_draft_reply,
)


# ============================================================
# SETUP
# ============================================================

load_dotenv()

st.set_page_config(
    page_title="Ben's Personal Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialise_database()

LONDON = ZoneInfo("Europe/London")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def priority_icon(priority):
    if priority == "High":
        return "🔴"

    if priority == "Medium":
        return "🟠"

    if priority == "Low":
        return "🔵"

    return "⚪"


def format_event(event):
    start = event["start"].get(
        "dateTime",
        event["start"].get("date")
    )

    end = event["end"].get(
        "dateTime",
        event["end"].get("date")
    )

    summary = event.get(
        "summary",
        "Untitled event"
    )

    if not start:
        return f"All day — {summary}"

    if "T" in start:

        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        return (
            f"{start_dt.strftime('%H:%M')}–"
            f"{end_dt.strftime('%H:%M')}  "
            f"{summary}"
        )

    return f"All day — {summary}"


def format_event_date(event):
    start = event["start"].get(
        "dateTime",
        event["start"].get("date")
    )

    if "T" in start:

        start_dt = datetime.fromisoformat(start)

        return start_dt.strftime(
            "%A %d %B"
        )

    date_dt = datetime.fromisoformat(start)

    return date_dt.strftime(
        "%A %d %B"
    )


def sender_name(sender):
    if not sender:
        return "Unknown sender"

    if "<" in sender:
        return sender.split("<")[0].strip().strip('"')

    return sender


def load_emails(gmail, client):
    """
    Load recent emails.

    Cached emails are read from SQLite.

    New emails are analysed by Claude.

    Older cached emails that lack availability
    information are re-analysed when appropriate.
    """

    emails = []

    results = gmail.users().messages().list(
        userId="me",
        maxResults=20,
    ).execute()

    messages = results.get(
        "messages",
        []
    )

    for message in messages:

        message_id = message["id"]

        if email_is_cached(message_id):

            email = get_cached_email(
                message_id
            )

            analysis = email.get(
                "analysis",
                {}
            )

            # Older database records did not contain
            # availability information.
            #
            # Re-analyse tutoring/reply emails so the
            # new functionality can understand them.
            if (
                client
                and analysis.get("reply_needed")
                and email.get("analysis_version", 1) <= 3
            ):

                analysis = analyse_email(
                    client,
                    email,
                )

                email["analysis"] = analysis

                # Discard any draft produced using the
                # old analysis.
                email["draft_reply"] = None

                save_email(email)

        else:

            email = get_email(
                gmail,
                message_id,
            )

            email["id"] = message_id

            if client:

                analysis = analyse_email(
                    client,
                    email,
                )

                email["analysis"] = analysis

                save_email(email)

            else:

                email["analysis"] = {
                    "category": "Unknown",
                    "priority": "Unknown",
                    "action_required": False,
                    "reply_needed": False,
                    "availability_request": False,
                    "requested_day": None,
                    "requested_start": None,
                    "requested_end": None,
                    "summary": (
                        "Claude is not connected."
                    ),
                }

        emails.append(email)

    return emails


def get_next_sunday(now):
    days_until_sunday = (
        6 - now.weekday()
    ) % 7

    return (
        now
        + timedelta(days=days_until_sunday)
    )


def calculate_tutoring_availability(
    calendar_service,
    now,
):
    if not calendar_service:
        return [], None

    tutoring_day = get_next_sunday(now)

    tutoring_start = tutoring_day.replace(
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )

    tutoring_end = tutoring_day.replace(
        hour=18,
        minute=0,
        second=0,
        microsecond=0,
    )

    free_slots = find_free_slots(
        calendar_service,
        tutoring_start,
        tutoring_end,
        lesson_minutes=60,
    )

    return free_slots, tutoring_day


def availability_for_email(
    email,
    free_slots,
):
    analysis = email.get(
        "analysis",
        {}
    )

    if not analysis.get(
        "availability_request",
        False,
    ):
        return None

    requested_day = analysis.get(
        "requested_day"
    )

    # At the moment our tutoring availability
    # calculation is for Sunday.
    #
    # If Claude identifies Sunday, use it.
    if requested_day == "Sunday":
        return free_slots

    return None


# ============================================================
# HEADER
# ============================================================

st.title(
    "🤖 Ben's Personal Assistant"
)

st.caption(
    "Your personal command centre"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("Assistant")

    if st.button(
        "🔄 Refresh",
        use_container_width=True,
    ):

        st.cache_resource.clear()

        st.rerun()

    st.divider()

    st.subheader(
        "Connected services"
    )

    st.write("📧 Gmail")
    st.write("📅 Google Calendar")
    st.write("🧠 Claude")

    st.divider()

    st.subheader(
        "Assistant roadmap"
    )

    st.write("✓ Email triage")
    st.write("✓ Calendar awareness")
    st.write("✓ Tutoring availability")
    st.write("✓ AI reply drafts")

    st.write("⬜ Calendar management")
    st.write("⬜ Task management")
    st.write("⬜ Multiple calendars")
    st.write("⬜ Tutoring workflow")
    st.write("⬜ Finance & investments")
    st.write("⬜ Natural-language command centre")


# ============================================================
# CONNECT SERVICES
# ============================================================

gmail = None
calendar_service = None
client = None

gmail_connected = False
calendar_connected = False
claude_connected = False

gmail_error = None
calendar_error = None
claude_error = None


# Gmail

try:

    gmail = get_gmail_service()

    gmail_connected = True

except Exception as e:

    gmail_error = str(e)


# Calendar

try:

    calendar_service = get_calendar_service()

    calendar_connected = True

except Exception as e:

    calendar_error = str(e)


# Claude

try:

    api_key = os.environ.get(
        "ANTHROPIC_API_KEY"
    )

    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set."
        )

    client = create_client(
        api_key
    )

    claude_connected = True

except Exception as e:

    claude_error = str(e)


# ============================================================
# CURRENT TIME
# ============================================================

now = datetime.now(
    LONDON
)


# ============================================================
# LOAD EMAILS
# ============================================================

emails = []

if gmail_connected:

    try:

        emails = load_emails(
            gmail,
            client,
        )

    except Exception as e:

        gmail_connected = False

        gmail_error = str(e)


# ============================================================
# LOAD CALENDAR
# ============================================================

today_start = now.replace(
    hour=0,
    minute=0,
    second=0,
    microsecond=0,
)

tomorrow_start = (
    today_start
    + timedelta(days=1)
)

week_end = (
    today_start
    + timedelta(days=7)
)

today_events = []
week_events = []

if calendar_connected:

    try:

        today_events = get_calendar_for_period(
            calendar_service,
            today_start,
            tomorrow_start,
        )

        week_events = get_calendar_for_period(
            calendar_service,
            today_start,
            week_end,
        )

    except Exception as e:

        calendar_connected = False

        calendar_error = str(e)


# ============================================================
# TUTORING AVAILABILITY
# ============================================================

free_slots = []
tutoring_day = None

if calendar_connected:

    try:

        free_slots, tutoring_day = (
            calculate_tutoring_availability(
                calendar_service,
                now,
            )
        )

    except Exception:

        free_slots = []
        tutoring_day = None


# ============================================================
# EMAIL METRICS
# ============================================================

action_required = [
    email
    for email in emails
    if email.get(
        "analysis",
        {}
    ).get(
        "action_required",
        False,
    )
]


reply_needed = [
    email
    for email in emails
    if email.get(
        "analysis",
        {}
    ).get(
        "reply_needed",
        False,
    )
]


tutoring_enquiries = [
    email
    for email in action_required
    if email.get(
        "analysis",
        {}
    ).get(
        "category"
    ) == "Tutoring"
]


high_priority = [
    email
    for email in action_required
    if email.get(
        "analysis",
        {}
    ).get(
        "priority"
    ) == "High"
]


# ============================================================
# BRIEFING
# ============================================================

st.divider()

if high_priority:

    st.warning(
        f"🔴 You have {len(high_priority)} "
        f"high-priority item"
        f"{'s' if len(high_priority) != 1 else ''} "
        f"requiring attention."
    )

elif action_required:

    st.info(
        f"You have {len(action_required)} "
        f"email"
        f"{'s' if len(action_required) != 1 else ''} "
        f"requiring attention."
    )

else:

    st.success(
        "✓ Nothing currently requires your attention."
    )


# ============================================================
# METRICS
# ============================================================

col1, col2, col3, col4 = st.columns(4)

with col1:

    st.metric(
        "📧 Emails checked",
        len(emails),
    )

with col2:

    st.metric(
        "⚠️ Need attention",
        len(action_required),
    )

with col3:

    st.metric(
        "✉️ Replies needed",
        len(reply_needed),
    )

with col4:

    st.metric(
        "📅 Events today",
        len(today_events),
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

with st.expander(
    "System status"
):

    status1, status2, status3 = st.columns(3)

    with status1:

        if gmail_connected:
            st.success(
                "✓ Gmail connected"
            )
        else:
            st.error(
                "✗ Gmail unavailable"
            )

            if gmail_error:
                st.caption(
                    gmail_error
                )

    with status2:

        if calendar_connected:
            st.success(
                "✓ Google Calendar connected"
            )
        else:
            st.error(
                "✗ Google Calendar unavailable"
            )

            if calendar_error:
                st.caption(
                    calendar_error
                )

    with status3:

        if claude_connected:
            st.success(
                "✓ Claude connected"
            )
        else:
            st.error(
                "✗ Claude unavailable"
            )

            if claude_error:
                st.caption(
                    claude_error
                )


# ============================================================
# MAIN DASHBOARD
# ============================================================

left, right = st.columns(
    [1.2, 1]
)


# ============================================================
# ATTENTION
# ============================================================

with left:

    st.subheader(
        "⚠️ Requires your attention"
    )

    if not action_required:

        st.success(
            "Nothing currently requires action."
        )

    else:

        for email in action_required:

            analysis = email.get(
                "analysis",
                {}
            )

            priority = analysis.get(
                "priority",
                "Unknown",
            )

            category = analysis.get(
                "category",
                "Other",
            )

            subject = email.get(
                "subject",
                "No subject",
            )

            icon = priority_icon(
                priority
            )

            with st.container(
                border=True
            ):

                st.markdown(
                    f"### {icon} {subject}"
                )

                st.caption(
                    f"{category} • "
                    f"{priority} priority • "
                    f"{sender_name(email.get('sender'))}"
                )

                st.write(
                    analysis.get(
                        "summary",
                        "No summary available.",
                    )
                )

                if analysis.get(
                    "reply_needed"
                ):

                    st.caption(
                        "✉️ A reply is needed"
                    )

                if analysis.get(
                    "availability_request"
                ):

                    requested_day = analysis.get(
                        "requested_day"
                    )

                    requested_start = analysis.get(
                        "requested_start"
                    )

                    requested_end = analysis.get(
                        "requested_end"
                    )

                    if requested_day:

                        st.info(
                            "📅 Availability requested: "
                            f"{requested_day}"
                            + (
                                f" {requested_start}–"
                                f"{requested_end}"
                                if requested_start
                                and requested_end
                                else ""
                            )
                        )

                with st.expander(
                    "View email"
                ):

                    st.caption(
                        email.get(
                            "date",
                            "Unknown date",
                        )
                    )

                    st.write(
                        email.get(
                            "body",
                            "[No email body available]",
                        )
                    )

                # ----------------------------------------
                # DRAFT
                # ----------------------------------------

                if analysis.get(
                    "reply_needed"
                ):

                    existing_draft = email.get(
                        "draft_reply"
                    )

                    if existing_draft:

                        st.write(
                            "**AI draft reply**"
                        )

                        edited_draft = st.text_area(
                            "Review and edit before sending",
                            value=existing_draft,
                            height=180,
                            key=f"existing_{email['id']}",
                        )

                        if st.button(
                            "💾 Save draft",
                            key=f"save_{email['id']}",
                        ):

                            update_draft_reply(
                                email["id"],
                                edited_draft,
                            )

                            email[
                                "draft_reply"
                            ] = edited_draft

                            st.success(
                                "Draft saved."
                            )

                    else:

                        if st.button(
                            "✍️ Draft reply",
                            key=f"draft_{email['id']}",
                        ):

                            if not claude_connected:

                                st.error(
                                    "Claude is not connected."
                                )

                            else:

                                availability = (
                                    availability_for_email(
                                        email,
                                        free_slots,
                                    )
                                )

                                with st.spinner(
                                    "Claude is drafting a reply..."
                                ):

                                    draft = draft_reply(
                                        client,
                                        email,
                                        availability,
                                    )

                                email[
                                    "draft_reply"
                                ] = draft

                                save_email(
                                    email
                                )

                                st.rerun()


# ============================================================
# TODAY
# ============================================================

with right:

    st.subheader(
        "📅 Today"
    )

    if not calendar_connected:

        st.error(
            "Calendar unavailable."
        )

    elif not today_events:

        st.success(
            "No events scheduled today."
        )

    else:

        for event in today_events:

            with st.container(
                border=True
            ):

                st.write(
                    f"**{format_event(event)}**"
                )


# ============================================================
# TUTORING
# ============================================================

st.divider()

st.subheader(
    "🎓 Tutoring"
)
st.caption(
    "Available one-hour tutoring slots"
)

if tutoring_day:

    st.caption(
        tutoring_day.strftime(
            "%A %d %B %Y"
        )
        + " • 12:00–18:00"
    )

if not calendar_connected:

    st.info(
        "Connect Google Calendar to calculate availability."
    )

elif not free_slots:

    st.warning(
        "No one-hour tutoring slots are available."
    )

else:

    availability_cols = st.columns(
        min(
            len(free_slots),
            6
        )
    )

    for index, (
        slot_start,
        slot_end,
    ) in enumerate(free_slots):

        with availability_cols[
            index % len(availability_cols)
        ]:

            st.info(
                f"**{slot_start.strftime('%H:%M')}"
                f"–"
                f"{slot_end.strftime('%H:%M')}**"
            )


# ============================================================
# UPCOMING CALENDAR
# ============================================================

st.divider()

st.subheader(
    "🗓️ Next 7 days"
)

if not week_events:

    st.caption(
        "No upcoming calendar events."
    )

else:

    current_date = None

    for event in week_events:

        event_date = format_event_date(
            event
        )

        if event_date != current_date:

            st.markdown(
                f"**{event_date}**"
            )

            current_date = event_date

        st.write(
            f"• {format_event(event)}"
        )


# ============================================================
# INBOX
# ============================================================

st.divider()

st.subheader(
    "📧 Inbox"
)

if not emails:

    st.info(
        "No emails found."
    )

else:

    filter_col1, filter_col2 = st.columns(
        [1, 2]
    )

    with filter_col1:

        filter_option = st.selectbox(
            "Filter",
            [
                "All emails",
                "Needs attention",
                "Replies needed",
                "High priority",
                "Tutoring",
            ],
        )

    with filter_col2:

        search = st.text_input(
            "Search",
            placeholder=(
                "Search sender or subject..."
            ),
        )


    filtered_emails = emails


    if filter_option == "Needs attention":

        filtered_emails = [
            email
            for email in filtered_emails
            if email.get(
                "analysis",
                {}
            ).get(
                "action_required",
                False,
            )
        ]


    elif filter_option == "Replies needed":

        filtered_emails = [
            email
            for email in filtered_emails
            if email.get(
                "analysis",
                {}
            ).get(
                "reply_needed",
                False,
            )
        ]


    elif filter_option == "High priority":

        filtered_emails = [
            email
            for email in filtered_emails
            if email.get(
                "analysis",
                {}
            ).get(
                "priority"
            ) == "High"
        ]


    elif filter_option == "Tutoring":

        filtered_emails = [
            email
            for email in filtered_emails
            if email.get(
                "analysis",
                {}
            ).get(
                "category"
            ) == "Tutoring"
        ]


    if search:

        search_lower = search.lower()

        filtered_emails = [
            email
            for email in filtered_emails
            if (
                search_lower
                in email.get(
                    "subject",
                    ""
                ).lower()
                or
                search_lower
                in email.get(
                    "sender",
                    ""
                ).lower()
            )
        ]


    st.caption(
        f"Showing {len(filtered_emails)} "
        f"of {len(emails)} emails"
    )


    for email in filtered_emails:

        analysis = email.get(
            "analysis",
            {}
        )

        priority = analysis.get(
            "priority",
            "Unknown",
        )

        category = analysis.get(
            "category",
            "Unknown",
        )

        subject = email.get(
            "subject",
            "No subject",
        )

        icon = priority_icon(
            priority
        )

        with st.expander(
            f"{icon} {category} | {subject}"
        ):

            st.write(
                f"**From:** "
                f"{email.get('sender', 'Unknown')}"
            )

            st.write(
                f"**Date:** "
                f"{email.get('date', 'Unknown')}"
            )

            st.divider()

            st.write(
                "**Claude's summary**"
            )

            st.write(
                analysis.get(
                    "summary",
                    "No summary available.",
                )
            )

            col_a, col_b, col_c = st.columns(3)

            with col_a:

                st.write(
                    "**Action:** "
                    + (
                        "Yes"
                        if analysis.get(
                            "action_required"
                        )
                        else "No"
                    )
                )

            with col_b:

                st.write(
                    "**Reply:** "
                    + (
                        "Yes"
                        if analysis.get(
                            "reply_needed"
                        )
                        else "No"
                    )
                )

            with col_c:

                st.write(
                    "**Priority:** "
                    f"{priority}"
                )

            if email.get(
                "draft_reply"
            ):

                st.divider()

                st.write(
                    "**Saved draft**"
                )

                edited_draft = st.text_area(
                    "Draft",
                    value=email[
                        "draft_reply"
                    ],
                    height=160,
                    key=f"inbox_draft_{email['id']}",
                )

                if st.button(
                    "💾 Save changes",
                    key=f"inbox_save_{email['id']}",
                ):

                    update_draft_reply(
                        email["id"],
                        edited_draft,
                    )

                    st.success(
                        "Draft saved."
                    )

            with st.expander(
                "Original email"
            ):

                st.write(
                    email.get(
                        "body",
                        "[No email body available]",
                    )
                )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Ben's Personal Assistant • v0.5"
)