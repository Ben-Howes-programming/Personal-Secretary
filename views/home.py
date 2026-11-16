"""
home.py
=======
Purpose : The Today page. One screen that answers "what needs me today?"
Location: views/home.py
Note    : Opening this page uses no Claude tokens. The briefing is written only
          when you press its button, and is then reused for six hours.
"""

from datetime import timedelta

import streamlit as st

import config
from ai import claude, context
from database import database as db
from database import finance, health, tasks, university
from services import calendar as cal
from services import market, training
from ui import state
from ui import theme as ui

now = state.now()
today = now.date()
greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 18 else "Good evening")
if now.hour < 5:
    greeting = "Still up"
ui.header(f"{greeting}, {config.OWNER_NAME}", now.strftime("%A %d %B %Y"))

# ------------------------------------------------------------------
# Gather (all from the database or the five-minute cache)
# ------------------------------------------------------------------
week = state.week_events()
todays_events = state.events_on(today, week)
attention = [e for e in db.list_emails(60, include_done=False) if e["analysis"]["action_required"]]
groups = tasks.group_tasks(tasks.list_tasks())
due_now = groups["Overdue"] + groups["Today"]
open_work = [a for a in university.list_assessments(only_open=True) if a.get("due")]
reviews = university.reviews_due()
sleep = training.sleep_stats(health.get_sleep(7), state.pref("sleep_target"))
worth = finance.net_worth()

load = training.weekly_load(health.get_workouts(28))
recent_km = load[-2]["run_km"] if len(load) >= 2 else 0.0      # last full week of running
plan = training.build_week_plan(state.pref("gym_days"), state.pref("run_days"), today, recent_km)
timed_plan = training.suggest_times(plan, week, config.TRAINING_WINDOW, state.pref("train_time"), state.pref("bedtime"))
session = next((day for day in timed_plan if day["date"] == today), None)

# ------------------------------------------------------------------
# Headline figures
# ------------------------------------------------------------------
next_due = open_work[0] if open_work else None
ui.kpis([
    ("emails need you", len(attention), "high priority" if any(e["analysis"]["priority"] == "High" for e in attention) else "",
     "bad"),
    ("events today", len(todays_events)),
    ("tasks due", len(due_now), f"{len(groups['Overdue'])} overdue" if groups["Overdue"] else "", "bad"),
    ("next deadline", ui.days_until(next_due["due"], today) if next_due else "none set", next_due["title"] if next_due else ""),
    ("sleep, 7-day average", f"{sleep['average']:.1f} h" if sleep["average"] else "not logged",
     f"{sleep['debt']:.1f} h short this week" if sleep["debt"] > 0.5 else "", "warn"),
    ("net worth", ui.money(worth["net"]) if worth["has_data"] else "not set"),
])

# ------------------------------------------------------------------
# Day ribbon: calendar, suggested training slot, wind-down, now
# ------------------------------------------------------------------
blocks = []
for event in todays_events:
    start, end = cal.event_to_datetime(event)
    if start and not cal.is_all_day(event):
        blocks.append({"start": max(start, state.midnight()), "end": end, "label": event.get("summary", "Event")})
if session and session.get("start"):
    blocks.append({"start": session["start"], "end": session["end"], "label": session["title"], "planned": True})
ui.day_ribbon(blocks, now, state.pref("bedtime"))

left, right = st.columns([1.15, 1], gap="large")

with left:
    ui.section("Needs you")
    if not state.any_mail():
        ui.empty("No mail account connected.", "Open Settings to connect Google.")
    elif not attention:
        ui.empty("No email needs action.", state.sync_caption())
    else:
        ui.rows([ui.row(email.get("subject") or "No subject", email["analysis"]["summary"],
                        tone={"High": "bad", "Medium": "warn"}.get(email["analysis"]["priority"]))
                 for email in attention[:5]])
        ui.muted(state.sync_caption())
    mail_col, inbox_col = st.columns(2)
    if state.any_mail() and mail_col.button("Check mail now"):
        state.sync_inbox(force=True)
        st.rerun()
    inbox_col.page_link("views/inbox.py", label="Open the inbox", icon=":material/mail:")

    ui.section("Tasks")
    if due_now:
        ui.rows([ui.row(task["title"], task["area"], ui.days_until(task["due"], today),
                        tone="bad" if task in groups["Overdue"] else "warn") for task in due_now[:6]])
    else:
        ui.empty("Nothing due today.", f"{len(groups['Upcoming'])} upcoming.")
    if reviews:
        ui.note("info", f"{len(reviews)} lecture review{'s' if len(reviews) != 1 else ''} due. Ten minutes of recall now saves an hour before the exam.")

    ui.section("Briefing")
    if st.button("Write today's briefing", help="Uses Claude once, then reuses the answer for six hours"):
        try:
            with st.spinner("Writing"):
                st.session_state["briefing"] = claude.daily_briefing(
                    context.build_context(context.SOURCES, week))
        except claude.AIError as error:
            st.error(str(error))
    if st.session_state.get("briefing"):
        st.markdown(st.session_state["briefing"])

with right:
    ui.section("Today")
    if not state.any_calendar():
        ui.empty("No calendar connected.", "Open Settings to connect Google.")
    elif not todays_events:
        ui.empty("Nothing in the calendar today.")
    else:
        ui.rows([ui.row(cal.describe_event(event), event.get("source", "")) for event in todays_events])

    ui.section("Training")
    if session and session["kind"] != "rest":
        when = (f"{session['start'].strftime('%H:%M')} to {session['end'].strftime('%H:%M')}"
                if session.get("start") else "no free slot found today")
        ui.rows([ui.row(session["title"], session["details"][0], when, tone="accent")])
    else:
        ui.empty("Rest day.", "Recovery is part of the plan.")
    st.page_link("views/health.py", label="Open the training plan", icon=":material/fitness_center:")

    ui.section("Deadlines")
    soon = [a for a in open_work if a["due"] <= (today + timedelta(days=21)).isoformat()]
    if soon:
        ui.rows([ui.row(item["title"], item["module"] or "", ui.days_until(item["due"], today),
                        tone="bad" if item["due"] <= (today + timedelta(days=3)).isoformat() else None) for item in soon[:6]])
    else:
        ui.empty("No deadlines in the next three weeks.", "Add them on the University page.")

# ------------------------------------------------------------------
# Holdings strip (cached prices, refreshed at most every 30 minutes)
# ------------------------------------------------------------------
holdings = finance.list_watchlist("holding")
if holdings:
    ui.section("Your funds")
    histories = market.get_many([item["symbol"] for item in holdings] + [market.FX_SYMBOL])
    rate = market.gbpusd_rate()
    cells = []
    for item in holdings:
        figures = market.summarise(histories[item["symbol"]], rate, item.get("currency"))
        if figures["ok"]:
            price = ui.money(figures["price_gbp"], 2) if figures["price_gbp"] is not None else f"{figures['price']:,.2f} {figures['currency'] or ''}"
            cells.append((item["symbol"].replace(".L", ""), price, f"{ui.pct(figures['day'])} today", ui.tone_of(figures["day"])))
        else:
            cells.append((item["symbol"].replace(".L", ""), "no data", figures["error"] or "", "neutral"))
    ui.kpis(cells)
