"""
scheduler.py
============
Purpose : Runs jobs by the clock while Cassiopeia is open: morning briefing, evening
          summary, the overnight trading lab, and the optional once-a-minute activity sample.
Location: cassiopeia/scheduler.py
Used by : cassiopeia/__main__.py
Design  : A job that was missed because the Mac was asleep still runs when it wakes, as
          long as it is within the job's grace period. After that it waits for tomorrow.
"""

import platform
import subprocess
import threading
import time
from datetime import datetime, timedelta

import config
from cassiopeia import briefing, events, lab, store
from database import database as db


def due(at_hhmm, grace_hours, now, last_run_ts):
    """True when a daily job should run now. Pure function, tested in tests/test_cassiopeia.py."""
    hour, minute = (int(part) for part in at_hhmm.split(":"))
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < scheduled or now - scheduled > timedelta(hours=grace_hours):
        return False
    return last_run_ts is None or datetime.fromtimestamp(last_run_ts, now.tzinfo) < scheduled


def sample_activity():
    """Add one minute to whichever app is in front. Needs ENABLE_ACTIVITY_TRACKING and macOS."""
    if platform.system() != "Darwin":
        return "needs macOS"
    done = subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first '
                           'application process whose frontmost is true'], capture_output=True, text=True, timeout=10)
    app = done.stdout.strip()
    if done.returncode != 0 or not app:
        return "could not read the front app"
    day = events.now().date().isoformat()
    db.execute("INSERT INTO cass_activity (day, app, minutes) VALUES (?, ?, 1) "
               "ON CONFLICT(day, app) DO UPDATE SET minutes = minutes + 1", (day, app))
    return app


def activity_today():
    day = events.now().date().isoformat()
    return db.query("SELECT app, minutes FROM cass_activity WHERE day = ? ORDER BY minutes DESC LIMIT 8", (day,))


# name, time of day, hours of grace, what to run
DAILY_JOBS = [
    ("morning briefing", config.MORNING_BRIEFING_AT, 4.0, lambda: briefing.deliver("morning")["written_by"]),
    ("evening summary", config.EVENING_SUMMARY_AT, 2.5, lambda: briefing.deliver("evening")["written_by"]),
    ("overnight lab", config.OVERNIGHT_LAB_AT, 6.0, lab.run_overnight),
]


def run_job(name, action):
    """Run one job and record the outcome. A failing job never stops the scheduler."""
    try:
        store.job_ran(name, "ok", action())
    except Exception as problem:
        store.job_ran(name, "failed", str(problem))


def tick(now=None):
    """Check every job once. Called every 30 seconds by the loop below."""
    now = now or events.now()
    for name, at, grace, action in DAILY_JOBS:
        state = store.job_state(name)
        if due(at, grace, now, state["last_run_ts"] if state else None):
            run_job(name, action)


def start():
    """Start the background loop. Returns the thread."""
    def loop():
        last_sample = 0.0
        while True:
            try:
                tick()
                if config.ENABLE_ACTIVITY_TRACKING and time.time() - last_sample >= 60:
                    last_sample = time.time()
                    sample_activity()
            except Exception:
                pass                # never let one bad tick end the loop
            time.sleep(30)
    thread = threading.Thread(target=loop, name="cassiopeia-scheduler", daemon=True)
    thread.start()
    return thread
