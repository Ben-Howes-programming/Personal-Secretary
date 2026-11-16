"""
health.py
=========
Purpose : Sleep, training and nutrition patterns, a weekly plan for gym and
          running that fits around your calendar, and Apple Health import.
Location: views/health.py
Tokens  : The analysis and the plan are worked out by rules in services/training.py,
          so they are free. Only the optional weekly review uses Claude.
Note    : General training guidance, not medical advice.
"""

from datetime import time, timedelta

import streamlit as st

import config
from ai import claude
from database import health
from services import apple, training
from services import calendar as cal
from ui import state
from ui import theme as ui

today = state.now().date()
gym_days, run_days = int(state.pref("gym_days")), int(state.pref("run_days"))
ui.header("Health", "Sleep, strength and running, read together.")

sleep_rows = health.get_sleep(30)
week_sleep = training.sleep_stats([row for row in sleep_rows if row["date"] >= (today - timedelta(days=7)).isoformat()],
                                  state.pref("sleep_target"))
workouts = health.get_workouts(70)
load = training.weekly_load(workouts)
this_week = load[-1] if load else {"strength": 0, "runs": 0, "run_km": 0.0}
ratio = training.run_load_ratio(load)
body_rows = health.get_body(30)
weight = health.latest_weight()
protein_range = training.protein_target(weight, config.PROTEIN_G_PER_KG)
protein_days = [row["protein_g"] for row in body_rows[-7:] if row.get("protein_g")]
protein_avg = sum(protein_days) / len(protein_days) if protein_days else None

ui.kpis([
    ("sleep, 7-day average", f"{week_sleep['average']:.1f} h" if week_sleep["average"] else "not logged",
     f"{week_sleep['debt']:.1f} h short this week" if week_sleep["debt"] > 0.5 else "", "warn"),
    ("usual bedtime", week_sleep["average_bedtime"] or "not logged", f"target {state.pref('bedtime')}"),
    ("strength this week", f"{this_week['strength']} of {gym_days}"),
    ("runs this week", f"{this_week['runs']} of {run_days}", f"{this_week['run_km']:.1f} km"),
    ("protein, 7-day average", f"{protein_avg:.0f} g" if protein_avg else "not logged",
     f"range {protein_range[0]} to {protein_range[1]} g" if protein_range else "log your weight for a range"),
])

overview, log, plan_tab, progress, importer = st.tabs(["Patterns", "Log", "Weekly plan", "Progress", "Apple Health"])

# ------------------------------------------------------------------
with overview:
    ui.section("What the numbers say")
    for tone, text in training.insights(week_sleep, load, ratio, protein_avg, protein_range, (gym_days, run_days)):
        ui.note(tone, text)

    if st.button("Write a weekly review", help="Uses Claude once a day at most for the same numbers"):
        summary = (f"Sleep: {week_sleep}. This week: {this_week}. Running load ratio: {ratio}. "
                   f"Protein average: {protein_avg}, target range: {protein_range}. "
                   f"Plan: {gym_days} strength and {run_days} runs a week. Goal: build muscle and general fitness.")
        try:
            with st.spinner("Reviewing"):
                st.session_state["health_review"] = claude.health_review(summary)
        except claude.AIError as error:
            st.error(str(error))
    if st.session_state.get("health_review"):
        st.markdown(st.session_state["health_review"])

    left, right = st.columns(2, gap="large")
    with left:
        ui.section("Hours slept")
        ui.line_chart([{"date": row["date"], "value": row["hours"]} for row in sleep_rows if row.get("hours")],
                      y_title="Hours", number_format=".1f", height=230)
    with right:
        ui.section("Sessions each week")
        ui.bar_chart([{"label": week["week"][5:], "value": week[kind], "series": name}
                      for week in load[-8:] for kind, name in (("strength", "Strength"), ("runs", "Runs"))],
                     y_title="Sessions", order=["Strength", "Runs"], number_format=".0f", height=230)

# ------------------------------------------------------------------
with log:
    sleep_col, body_col = st.columns(2, gap="large")
    with sleep_col:
        with st.form("sleep_form", clear_on_submit=True):
            st.markdown("**Last night**")
            night = st.date_input("Woke up on", value=today)
            a, b = st.columns(2)
            bed = a.time_input("Went to bed", value=time(23, 30), step=300)
            wake = b.time_input("Woke up", value=time(7, 30), step=300)
            quality = st.slider("How rested do you feel?", 1, 5, 3)
            if ui.submit("Save sleep", type="primary"):
                health.log_sleep(night.isoformat(), bed.strftime("%H:%M"), wake.strftime("%H:%M"), quality)
                st.rerun()
    with body_col:
        with st.form("body_form", clear_on_submit=True):
            st.markdown("**Today's numbers** (leave blank what you did not measure)")
            a, b, c = st.columns(3)
            new_weight = a.number_input("Weight (kg)", value=None, min_value=30.0, max_value=200.0, step=0.1)
            protein = b.number_input("Protein (g)", value=None, min_value=0.0, max_value=400.0, step=5.0)
            energy = c.number_input("Energy 1 to 5", value=None, min_value=1, max_value=5, step=1)
            if ui.submit("Save numbers", type="primary"):
                health.log_body(today.isoformat(), new_weight, protein, energy)
                st.rerun()

    workout_col, lift_col = st.columns(2, gap="large")
    with workout_col:
        with st.form("workout_form", clear_on_submit=True):
            st.markdown("**A session**")
            a, b = st.columns(2)
            on = a.date_input("Date", value=today, key="workout_date")
            kind = b.selectbox("Type", ["strength", "run", "other"])
            title = st.text_input("What was it?", placeholder="Upper A, easy run, football")
            c, d, e = st.columns(3)
            minutes = c.number_input("Minutes", value=60, min_value=0, step=5)
            distance = d.number_input("Distance (km)", value=None, min_value=0.0, step=0.5)
            effort = e.number_input("Effort 1 to 10", value=None, min_value=1, max_value=10, step=1)
            if ui.submit("Save session", type="primary"):
                health.log_workout(on.isoformat(), kind, title, minutes, distance, effort)
                st.rerun()
    with lift_col:
        with st.form("lift_form", clear_on_submit=True):
            st.markdown("**A lift** (your heaviest working set)")
            known = health.list_exercises()
            exercise = st.selectbox("Exercise", known, index=None, placeholder="Choose or type a new one", accept_new_options=True) \
                if known else st.text_input("Exercise", placeholder="Bench press")
            a, b, c = st.columns(3)
            lifted = a.number_input("Weight (kg)", value=None, min_value=0.0, step=2.5, key="lift_weight")
            reps = b.number_input("Reps", value=8, min_value=1, max_value=50)
            sets = c.number_input("Sets", value=3, min_value=1, max_value=12)
            if ui.submit("Save lift", type="primary") and exercise and lifted:
                health.log_lift(today.isoformat(), exercise, lifted, reps, sets)
                st.rerun()

    recent = workouts[-8:][::-1]
    if recent:
        ui.section("Recent sessions")
        ui.table([{"Date": w["date"], "Type": w["kind"], "Session": w["title"], "Minutes": w["duration_min"],
                   "km": w["distance_km"], "Effort": w["rpe"], "From": w["source"]} for w in recent])

# ------------------------------------------------------------------
with plan_tab:
    a, b, c, d = st.columns(4)
    new_gym = a.selectbox("Gym days", [3, 4], index=1 if gym_days >= 4 else 0)
    new_runs = b.selectbox("Runs", [0, 1, 2, 3], index=min(run_days, 3))
    new_time = c.selectbox("Prefer to train in the", ["morning", "midday", "evening"],
                           index=["morning", "midday", "evening"].index(state.pref("train_time")))
    which = d.selectbox("Week", ["This week", "Next week"])
    if (new_gym, new_runs, new_time) != (gym_days, run_days, state.pref("train_time")):
        state.set_pref("gym_days", new_gym)
        state.set_pref("run_days", new_runs)
        state.set_pref("train_time", new_time)
        st.rerun()

    monday = training.week_start(today) + timedelta(days=7 if which == "Next week" else 0)
    events, _errors = state.events_between(cal.at(monday, "00:00"), cal.at(monday + timedelta(days=7), "00:00"))
    last_full_week = load[-2]["run_km"] if len(load) >= 2 else (load[-1]["run_km"] if load else 0.0)
    plan = training.suggest_times(training.build_week_plan(gym_days, run_days, monday, last_full_week), events,
                                  config.TRAINING_WINDOW, state.pref("train_time"), state.pref("bedtime"))

    if not state.any_calendar():
        ui.note("info", "Connect a calendar in Settings and each session gets a time that fits around your lectures.")
    for day in plan:
        is_today = day["date"] == today
        when = ""
        if day["kind"] != "rest":
            when = (f"{day['start'].strftime('%H:%M')} to {day['end'].strftime('%H:%M')}" if day.get("start")
                    else "no free slot in your training window")
        heading = f"{day['date'].strftime('%A %d %b')}: {day['title']}" + (f", {when}" if when else "")
        with st.expander(heading + ("  (today)" if is_today else ""), expanded=is_today and day["kind"] != "rest"):
            for line in day["details"]:
                st.markdown(f"- {line}")
            if day["kind"] == "strength":
                ui.muted("Work 1 to 3 reps short of failure. When you reach the top of a rep range on every set, add weight next time.")
            if config.ENABLE_CALENDAR_WRITE and day.get("start") and day["start"] > state.now():
                if st.button("Add to Google Calendar", key=f"plan_{day['date']}"):
                    try:
                        cal.create_event(state.calendar_service(), day["title"], day["start"], day["end"], "\n".join(day["details"]))
                        st.cache_data.clear()
                        st.toast("Session added to your calendar")
                    except Exception as error:
                        st.error(f"Google refused the event: {error}")
    ui.muted("How the plan is built: hard running is kept away from heavy leg days, the long run sits on Sunday, Saturday stays free, "
             "running distance rises by at most 10% a week, and nothing finishes within two hours of your bedtime target.")
    if not config.ENABLE_CALENDAR_WRITE:
        ui.muted("To add sessions to your calendar with one press, set ENABLE_CALENDAR_WRITE=true in .env.")

# ------------------------------------------------------------------
with progress:
    exercises = health.list_exercises()
    ui.section("Strength")
    if exercises:
        chosen = st.selectbox("Exercise", exercises, key="progress_exercise")
        lifts = health.get_lifts(365, chosen)
        trend = training.strength_trend(lifts)
        ui.line_chart([{"date": point["date"], "value": point["e1rm"]} for point in trend],
                      y_title="Estimated one-rep max (kg)", number_format=".1f", height=240)
        st.latex(r"\text{1RM} \approx w\left(1 + \frac{r}{30}\right)")
        target = training.next_lift_target(lifts)
        if target:
            ui.note("accent", f"Next time: {target['weight_kg']:g} kg for {target['reps']} reps. {target['why']}")
    else:
        ui.empty("No lifts logged.", "Log your heaviest working set after each session to see strength trends and your next target.")

    ui.section("Running distance each week")
    if any(week["run_km"] for week in load):
        ui.bar_chart([{"label": week["week"][5:], "value": week["run_km"]} for week in load[-10:]], y_title="km", height=230)
        if ratio:
            ui.muted(f"This week is {ratio:.1f} times your recent weekly average. Keeping that under about 1.3 is a common guard against overuse injuries.")
    else:
        ui.empty("No runs logged.")

    weights = [{"date": row["date"], "value": row["weight_kg"]} for row in health.get_body(180) if row.get("weight_kg")]
    if len(weights) >= 2:
        ui.section("Body weight")
        ui.line_chart(weights, y_title="kg", number_format=".1f", height=230)
        ui.muted("For muscle gain, a slow rise is the usual aim. Day-to-day changes are mostly water, so read the trend, not single points.")

# ------------------------------------------------------------------
with importer:
    ui.section("Import from Apple Health")
    st.markdown(
        "Apple does not offer a web connection to Health, so the route is an export file:\n"
        "1. On your iPhone open **Health**, tap your picture, then **Export All Health Data**.\n"
        "2. AirDrop the zip to your Mac.\n"
        "3. Drop it here. Sleep, workouts, weight, steps and resting heart rate from the last 120 days are added. "
        "Anything you logged by hand is kept.")
    upload = st.file_uploader("Apple Health export (export.zip or export.xml)", type=["zip", "xml"])
    if upload and st.button("Import", type="primary"):
        try:
            with st.spinner("Reading the export. Large files take a minute."):
                counts = apple.save_health_import(apple.parse_health_export(upload))
            st.success(f"Imported {counts['sleep']} nights, {counts['workouts']} workouts and {counts['body']} days of body data.")
        except Exception as error:
            st.error(f"That file could not be read: {error}")
    ui.muted("The file stays on your Mac. If you use an app such as Bevel or Health Auto Export, its data reaches this page "
             "through the same Apple Health export.")
