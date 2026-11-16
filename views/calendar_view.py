"""
calendar_view.py
================
Purpose : Your agenda across Google, Outlook and iCloud, plus a free-time finder.
Location: views/calendar_view.py
Note    : Adding events is off until you set ENABLE_CALENDAR_WRITE=true in .env.
"""

from datetime import datetime, time, timedelta

import streamlit as st

import config
from services import calendar as cal
from ui import state
from ui import theme as ui

ui.header("Calendar", "Everything you have agreed to, and where the gaps are.")

if not state.any_calendar():
    ui.note("info", "No calendar is connected yet. Open Settings and press Connect Google.")
    st.stop()

span = st.segmented_control("Range", ["Today", "7 days", "14 days", "30 days"], default="7 days", key="cal_span") or "7 days"
days = {"Today": 1, "7 days": 7, "14 days": 14, "30 days": 30}[span]
events, errors = state.events_between(state.midnight(), state.midnight(days))
for problem in errors:
    st.warning(problem)

timed = [e for e in events if not cal.is_all_day(e)]
busy_hours = sum((cal.event_to_datetime(e)[1] - cal.event_to_datetime(e)[0]).total_seconds() for e in timed) / 3600
ui.kpis([("events", len(events)), ("hours booked", f"{busy_hours:.0f}"),
         ("average per day", f"{busy_hours / days:.1f} h")])

agenda, finder = st.columns([1.3, 1], gap="large")

with agenda:
    ui.section("Agenda")
    if not events:
        ui.empty("Nothing scheduled in this range.")
    current = None
    lines = []
    for event in events:
        day = cal.event_day(event)
        if day != current:
            if lines:
                ui.rows(lines)
                lines = []
            st.markdown(f"**{day}**")
            current = day
        lines.append(ui.row(cal.describe_event(event), "", event.get("source", "")))
    if lines:
        ui.rows(lines)

with finder:
    ui.section("Find free time")
    day = st.date_input("Day", value=state.now().date(), key="free_day")
    start_col, end_col = st.columns(2)
    window_start = start_col.time_input("From", value=time(9, 0), key="free_from")
    window_end = end_col.time_input("To", value=time(18, 0), key="free_to")
    minutes = st.select_slider("Slot length (minutes)", [30, 45, 60, 90, 120], value=60, key="free_len")
    start_dt = datetime.combine(day, window_start, tzinfo=state.ZONE)
    end_dt = datetime.combine(day, window_end, tzinfo=state.ZONE)
    if end_dt <= start_dt:
        ui.note("warn", "The end time must be after the start time.")
    else:
        day_events, _errors = state.events_between(start_dt.replace(hour=0, minute=0), start_dt.replace(hour=0, minute=0) + timedelta(days=1))
        gaps = cal.free_ranges(day_events, start_dt, end_dt)
        slots = cal.free_slots_from_events(day_events, start_dt, end_dt, minutes)
        if gaps:
            ui.rows([ui.row(f"{a.strftime('%H:%M')} to {b.strftime('%H:%M')}", "", f"{(b - a).total_seconds() / 3600:.1f} h free")
                     for a, b in gaps])
            ui.muted(f"{len(slots)} slot{'s' if len(slots) != 1 else ''} of {minutes} minutes fit.")
        else:
            ui.empty("No free time in that window.")

    ui.section("Add an event")
    if not config.ENABLE_CALENDAR_WRITE:
        ui.muted("Read-only. To let the app add events, set ENABLE_CALENDAR_WRITE=true in .env, delete token.json, and connect Google again.")
    else:
        with st.form("new_event", clear_on_submit=True):
            title = st.text_input("Title")
            when = st.date_input("Date", value=state.now().date())
            a, b = st.columns(2)
            begins = a.time_input("Starts", value=time(18, 0))
            length = b.number_input("Minutes", 15, 480, 60, step=15)
            if ui.submit("Add to Google Calendar", type="primary") and title:
                begin_dt = datetime.combine(when, begins, tzinfo=state.ZONE)
                try:
                    cal.create_event(state.calendar_service(), title, begin_dt, begin_dt + timedelta(minutes=length))
                    st.cache_data.clear()
                    st.toast("Event added")
                except Exception as error:
                    st.error(f"Google refused the event: {error}")
