"""
triggers.py
===========
Purpose : Things Cassiopeia tells you without being asked: a deadline within a day, an
          urgent email, an event starting in half an hour.
Location: cassiopeia/triggers.py
Used by : cassiopeia/scheduler.py (every five minutes), cassiopeia/server.py
Rules   : Each thing is announced once (cass_trigger_log remembers). Nothing is sent
          during quiet hours, which start at your bedtime target. Deadlines and emails
          found overnight are announced when quiet hours end. Costs no Claude tokens.
"""

import time
from datetime import timedelta

import config
from cassiopeia import events, notify, pages
from database import database as db
from database import tasks, university
from services import calendar as cal

KINDS = {
    "deadline": "A task or assessment due today or tomorrow that is still open",
    "email": "An urgent email that needs action",
    "event": "A calendar event starting in about 30 minutes",
}


def enabled(kind):
    return bool(db.get_setting(f"trigger_{kind}", True))      # all three are on unless you switch one off


def set_enabled(kind, on):
    if kind not in KINDS:
        raise ValueError("Unknown trigger.")
    db.set_setting(f"trigger_{kind}", bool(on))


def in_quiet_hours(now):
    """True between config.QUIET_HOURS[0] in the evening and config.QUIET_HOURS[1] in the morning."""
    clock = now.strftime("%H:%M")
    start, end = config.QUIET_HOURS
    return clock >= start or clock < end if start > end else start <= clock < end


def candidates(now):
    """Everything worth announcing right now, as (kind, key, message). The key makes each one fire once."""
    found = []
    today, tomorrow = now.date().isoformat(), (now.date() + timedelta(days=1)).isoformat()
    label = {today: "today", tomorrow: "tomorrow"}

    for task in tasks.list_tasks():
        if task.get("due") in label:
            found.append(("deadline", f"task:{task['id']}:{task['due']}", f"Due {label[task['due']]}: {task['title']}"))
    for item in university.list_assessments(only_open=True):
        due = (item.get("due") or "")[:10]
        if due in label:
            module = f" ({item['module']})" if item.get("module") else ""
            found.append(("deadline", f"assessment:{item['id']}:{due}", f"Assessment due {label[due]}: {item['title']}{module}"))

    soon, _errors = events.between(events.midnight(), events.midnight(1))
    for event in soon:
        begins, _ends = cal.event_to_datetime(event)
        if begins is None or cal.is_all_day(event):
            continue
        minutes = (begins - now).total_seconds() / 60
        if 0 < minutes <= 35:
            found.append(("event", f"event:{event.get('summary')}:{begins.isoformat()}",
                          f"In {round(minutes)} minutes: {cal.describe_event(event)}"))

    day_ago = time.time() - 24 * 3600
    for email in db.list_emails(60, include_done=False):
        if (email.get("received_ts") or 0) >= day_ago and pages.is_urgent(email):
            found.append(("email", f"email:{email['id']}",
                          f"Email needing action from {pages.sender_name(email.get('sender'))}: {email.get('subject')}"))
    return found


def check(now=None):
    """Announce anything new. Returns the messages sent this time."""
    now = now or events.now()
    if in_quiet_hours(now):
        return []
    sent = []
    for kind, key, message in candidates(now):
        if not enabled(kind) or db.query("SELECT 1 FROM cass_trigger_log WHERE key = ?", (key,)):
            continue
        db.execute("INSERT INTO cass_trigger_log (key, kind, message, fired_ts) VALUES (?, ?, ?, ?)",
                   (key, kind, message, time.time()))
        notify.mac_notification(config.APP_NAME, message)
        notify.text_me(message)          # logs itself as "off" if texting is not switched on
        sent.append(message)
    return sent


def status():
    return {"kinds": [{"kind": k, "about": about, "on": enabled(k)} for k, about in KINDS.items()],
            "quiet_hours": list(config.QUIET_HOURS),
            "recent": db.query("SELECT kind, message, fired_ts FROM cass_trigger_log ORDER BY fired_ts DESC LIMIT 8")}
