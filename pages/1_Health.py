"""
1_Health.py
===========
Purpose : Health page. Shows watch data (sleep, resting heart rate, HRV, steps, training)
          and lets you type in mood, energy, study hours and protein.
Location: pages/1_Health.py (Streamlit lists it in the sidebar automatically)
Note    : Watch data comes from: python -m services.apple_health ~/Downloads/export.zip
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import config
from database.health import (
    get_logs, init_health_table, save_daily_log, weekly_summary,
)

init_health_table()

st.title("Health and study")
st.caption(
    "Watch data arrives through the Apple Health import. "
    "Mood, energy, study hours and protein are typed here."
)

today = datetime.now(ZoneInfo(config.TIMEZONE)).date()

# ---------------- Manual entry ----------------
log_date = st.date_input("Date", value=today, max_value=today)

with st.form("manual_form"):
    energy = st.slider("Energy (1 low, 5 high)", 1, 5, 3)
    mood = st.slider("Mood (1 low, 5 high)", 1, 5, 3)
    study = st.number_input("Study hours", 0.0, 16.0, value=None, step=0.5)
    protein = st.number_input("Protein (g)", 0, 500, value=None, step=5)

    if st.form_submit_button("Save"):
        try:
            save_daily_log(
                log_date.isoformat(),
                energy=energy,
                mood=mood,
                study_hours=study,    # blank stays blank, nothing is overwritten
                protein_g=protein,
            )
            st.success("Saved.")
        except ValueError as error:
            st.error(str(error))

# ---------------- History (loaded after saving so it is never stale) ----------------
st.divider()
logs = get_logs((today - timedelta(days=13)).isoformat(), today.isoformat())

watch_days = [
    log["log_date"] for log in logs
    if log["steps"] is not None or log["asleep_minutes"] is not None
]
if watch_days:
    st.caption(f"Latest watch data: {watch_days[-1]}")
else:
    st.warning("No watch data yet. Export from the Health app and run the import.")

if logs:
    # ISO date strings sort correctly as text
    week_start = (today - timedelta(days=6)).isoformat()
    summary = weekly_summary([log for log in logs if log["log_date"] >= week_start])

    def show(value, unit="", digits=1):
        return "n/a" if value is None else f"{value:,.{digits}f}{unit}"

    st.subheader("Last 7 days")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Average sleep", show(summary["avg_sleep_hours"], " h"))
    c2.metric("Resting HR", show(summary["avg_resting_hr"], " bpm", 0))
    c3.metric("Average steps", show(summary["avg_steps"], "", 0))
    c4.metric("Training days", summary["training_days"])
    c5.metric("Study hours", summary["total_study_hours"])

    df = pd.DataFrame(logs).set_index("log_date")
    for column in ("sleep_hours", "resting_hr", "hrv_ms", "steps", "protein_g"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    st.subheader("Sleep (hours asleep)")
    st.line_chart(df["sleep_hours"])
    st.subheader("Resting heart rate (bpm)")
    st.line_chart(df["resting_hr"])
    st.subheader("HRV (SDNN, ms)")
    st.caption("Apple's SDNN method. Other apps may use a different one, so don't compare numbers across apps.")
    st.line_chart(df["hrv_ms"])
    st.subheader("Steps")
    st.bar_chart(df["steps"])
    st.subheader("Protein (g)")
    st.bar_chart(df["protein_g"])

    with st.expander("Raw data"):
        st.dataframe(df)
