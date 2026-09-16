import os
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv

from services.gmail import get_gmail_service, get_email
from services.calendar import (
    get_calendar_service,
    get_calendar_for_period,
    find_free_slots,
)
from ai.claude import create_client, analyse_email, draft_reply

from database.database import (
    initialise_database,
    save_email,
    email_is_cached,
    get_cached_email,
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


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_event(event):
    """Turn a Google Calendar event into readable text."""

    start = event["start"].get(
        "dateTime",
        event["start"].get("date")
    )

    end = event["end"].get(
        "dateTime",
        event["end"].get("date")
    )

    summary = event.get("summary", "Untitled event")

    if "T" in start:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        return (
            f"{start_dt.strftime('%H:%M')}–"
            f"{end_dt.strftime('%H:%M')}  "
            f"{summary}"
        )

    return f"All day  —  {summary}"


def priority_icon(priority):
    """Return a simple visual indicator for priority."""

    if priority == "High":
        return "🔴"

    if priority == "Medium":
        return "🟠"

    return "🔵"


def load_emails(gmail, client):
    """Load recent emails and analyse uncached emails."""

    emails = []

    results = gmail.users().messages().list(
        userId="me",
        maxResults=20,
    ).execute()

    messages = results.get("messages", [])

    for message in messages:

        message_id = message["id"]

        if email_is_cached(message_id):

            email = get_cached_email(message_id)

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
                    "summary": "Claude is not connected.",
                }

        emails.append(email)

    return emails


# ============================================================
# HEADER
# ============================================================

st.title("🤖 Ben's Personal Assistant")
st.caption("Your personal command centre")

st.divider()


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

    st.subheader("Quick navigation")

    st.caption(
        "Your assistant currently connects to:"
    )

    st.write("📧 Gmail")
    st.write("📅 Google Calendar")
    st.write("🧠 Claude")

    st.divider()

    st.caption(
        "Future assistant features"
    )

    st.write("✉️ Email management")
    st.write("📅 Calendar management")
    st.write("🎓 Tutoring")
    st.write("💰 Finance & investments")
    st.write("📝 Tasks")
    st.write("🤖 AI command centre")


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


try:

    gmail = get_gmail_service()
    gmail_connected = True

except Exception as e:

    gmail_error = str(e)


try:

    calendar_service = get_calendar_service()
    calendar_connected = True

except Exception as e:

    calendar_error = str(e)


try:

    client = create_client(
        os.environ["ANTHROPIC_API_KEY"]
    )

    claude_connected = True

except Exception as e:

    claude_error = str(e)


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
# LOAD TODAY'S CALENDAR
# ============================================================

today = datetime.now()

day_start = today.replace(
    hour=0,
    minute=0,
    second=0,
    microsecond=0,
)

day_end = day_start + timedelta(days=1)

today_events = []

if calendar_connected:

    try:

        today_events = get_calendar_for_period(
            calendar_service,
            day_start,
            day_end,
        )

    except Exception as e:

        calendar_connected = False
        calendar_error = str(e)


# ============================================================
# EMAIL METRICS
# ============================================================

action_required = [
    email
    for email in emails
    if email.get("analysis", {}).get(
        "action_required",
        False,
    )
]

reply_needed = [
    email
    for email in emails
    if email.get("analysis", {}).get(
        "reply_needed",
        False,
    )
]

tutoring_enquiries = [
    email
    for email in emails
    if (
        email.get("analysis", {}).get("category")
        == "Tutoring"
        and email.get("analysis", {}).get(
            "action_required",
            False,
        )
    )
]


# ============================================================
# TOP METRICS
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
        "🎓 Tutoring",
        len(tutoring_enquiries),
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

with st.expander("System status"):

    status1, status2, status3 = st.columns(3)

    with status1:

        if gmail_connected:
            st.success("✓ Gmail connected")
        else:
            st.error("✗ Gmail unavailable")

            if gmail_error:
                st.caption(gmail_error)

    with status2:

        if calendar_connected:
            st.success("✓ Google Calendar connected")
        else:
            st.error("✗ Google Calendar unavailable")

            if calendar_error:
                st.caption(calendar_error)

    with status3:

        if claude_connected:
            st.success("✓ Claude connected")
        else:
            st.error("✗ Claude unavailable")

            if claude_error:
                st.caption(claude_error)


# ============================================================
# MAIN DASHBOARD
# ============================================================

left, right = st.columns([1.15, 1])


# ============================================================
# ATTENTION
# ============================================================

with left:

    st.subheader("⚠️ Requires your attention")

    if not action_required:

        st.success(
            "Nothing currently requires your attention."
        )

    else:

        for email in action_required:

            analysis = email.get(
                "analysis",
                {},
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

            icon = priority_icon(priority)

            with st.container(border=True):

                st.markdown(
                    f"### {icon} {category} — {subject}"
                )

                st.caption(
                    f"From: {email.get('sender', 'Unknown')}"
                )

                st.write(
                    analysis.get(
                        "summary",
                        "No summary available.",
                    )
                )

                if analysis.get("reply_needed"):

                    st.caption(
                        "✉️ A reply is needed"
                    )

                # ------------------------------------------------
                # EMAIL DETAILS
                # ------------------------------------------------

                with st.expander("View email"):

                    st.write(
                        email.get(
                            "body",
                            "[No email body available]",
                        )
                    )

                # ------------------------------------------------
                # DRAFT REPLY
                # ------------------------------------------------

                if analysis.get("reply_needed"):

                    if st.button(
                        "✍️ Draft reply",
                        key=f"draft_{email['id']}",
                    ):

                        if not claude_connected:

                            st.error(
                                "Claude is not connected."
                            )

                        else:

                            with st.spinner(
                                "Drafting reply..."
                            ):

                                draft = draft_reply(
                                    client,
                                    email,
                                    None,
                                )

                            st.session_state[
                                f"draft_{email['id']}"
                            ] = draft

                draft_key = f"draft_{email['id']}"

                if draft_key in st.session_state:

                    st.text_area(
                        "Draft reply",
                        value=st.session_state[draft_key],
                        height=180,
                        key=f"text_{email['id']}",
                    )

                    st.caption(
                        "⚠️ Draft only — nothing is sent automatically."
                    )


# ============================================================
# TODAY'S CALENDAR
# ============================================================

with right:

    st.subheader("📅 Today's calendar")

    if not calendar_connected:

        st.error(
            "Google Calendar is unavailable."
        )

    elif not today_events:

        st.success(
            "No events scheduled today."
        )

    else:

        for event in today_events:

            with st.container(border=True):

                st.write(
                    f"**{format_event(event)}**"
                )


# ============================================================
# TUTORING AVAILABILITY
# ============================================================

st.divider()

st.subheader("🎓 Tutoring availability")

tutoring_day = today + timedelta(
    days=(6 - today.weekday()) % 7
)

# If today is Sunday, use today.
if today.weekday() == 6:

    tutoring_day = today


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

if calendar_connected:

    try:

        free_slots = find_free_slots(
            calendar_service,
            tutoring_start,
            tutoring_end,
            lesson_minutes=60,
        )

        if free_slots:

            st.write(
                f"**{tutoring_day.strftime('%A %d %B')}**"
            )

            cols = st.columns(
                min(len(free_slots), 6)
            )

            for index, (slot_start, slot_end) in enumerate(
                free_slots
            ):

                with cols[index % len(cols)]:

                    st.info(
                        f"{slot_start.strftime('%H:%M')}"
                        f"–"
                        f"{slot_end.strftime('%H:%M')}"
                    )

        else:

            st.info(
                "No one-hour tutoring slots are currently available."
            )

    except Exception as e:

        st.error(
            f"Could not calculate tutoring availability: {e}"
        )

else:

    st.info(
        "Connect Google Calendar to calculate tutoring availability."
    )


# ============================================================
# RECENT EMAILS
# ============================================================

st.divider()

st.subheader("📧 Recent emails")

if not emails:

    st.info(
        "No emails found."
    )

else:

    for email in emails:

        analysis = email.get(
            "analysis",
            {},
        )

        category = analysis.get(
            "category",
            "Unknown",
        )

        priority = analysis.get(
            "priority",
            "Unknown",
        )

        subject = email.get(
            "subject",
            "No subject",
        )

        sender = email.get(
            "sender",
            "Unknown sender",
        )

        icon = priority_icon(priority)

        with st.expander(
            f"{icon} {category}  |  {subject}"
        ):

            st.write(
                f"**From:** {sender}"
            )

            st.write(
                f"**Date:** "
                f"{email.get('date', 'Unknown')}"
            )

            st.divider()

            st.write(
                "**Claude's summary:**"
            )

            st.write(
                analysis.get(
                    "summary",
                    "No summary available.",
                )
            )

            col_a, col_b = st.columns(2)

            with col_a:

                st.write(
                    "**Action required:** "
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
                    "**Reply needed:** "
                    + (
                        "Yes"
                        if analysis.get(
                            "reply_needed"
                        )
                        else "No"
                    )
                )

            with st.expander("Email body"):

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
    "Ben's Personal Assistant • Local development build"
)