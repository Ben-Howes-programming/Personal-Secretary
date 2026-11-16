"""
tutoring.py
===========
Purpose : Your free lesson slots and the tutoring enquiries waiting for a reply.
Location: views/tutoring.py
Note    : The lesson day, window and length are set in config.py (TUTORING_*).
"""

from datetime import timedelta

import streamlit as st

import config
from database import database as db
from services import calendar as cal
from ui import emails as email_ui
from ui import state
from ui import theme as ui

ui.header("Tutoring", "Open lesson slots and the enquiries to answer.")

day_name = cal.DAY_NAMES[config.TUTORING_WEEKDAY]
enquiries = [e for e in db.list_emails(120, include_done=False) if e["analysis"]["category"] == "Tutoring"]

ui.section(f"Free slots on the next two {day_name}s")
if not state.any_calendar():
    ui.empty("No calendar connected.", "Connect Google in Settings to see your free slots.")
else:
    first = cal.next_weekday(config.TUTORING_WEEKDAY, state.now())
    columns = st.columns(2)
    for column, day in zip(columns, (first, first + timedelta(days=7))):
        start, end = cal.at(day, config.TUTORING_WINDOW[0]), cal.at(day, config.TUTORING_WINDOW[1])
        events, _errors = state.events_between(start, end)
        slots = [slot for slot in cal.free_slots_from_events(events, start, end, config.TUTORING_LESSON_MINUTES)
                 if slot[0] > state.now()]
        with column:
            st.markdown(f"**{day.strftime('%A %d %B')}**, {config.TUTORING_WINDOW[0]} to {config.TUTORING_WINDOW[1]}")
            if slots:
                ui.rows([ui.row(f"{a.strftime('%H:%M')} to {b.strftime('%H:%M')}", "", "free", tone="good") for a, b in slots])
                st.code(", ".join(f"{a.strftime('%H:%M')}" for a, _b in slots), language=None)
            else:
                ui.empty("Fully booked.")
    ui.muted("The line under each day is ready to copy into a message.")

ui.section(f"Enquiries ({len(enquiries)})")
if not enquiries:
    ui.empty("No open tutoring enquiries.", "They appear here when an email is filed as Tutoring.")
for email in enquiries:
    email_ui.render(email, prefix="tutor")
