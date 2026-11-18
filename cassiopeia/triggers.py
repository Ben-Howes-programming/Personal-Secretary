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
from datetime import date, timedelta

import config
from cassiopeia import events, notify, pages
from database import database as db
from database import tasks, university
from services import calendar as cal

KINDS = {
    "deadline": "A task or assessment due today or tomorrow that is still open",
    "email": "An urgent email that needs action",
    "event": "A calendar event starting in about 30 minutes",
    "placement": "A placement you are still researching or drafting closes within 7 days",
    "price": "A fund you hold moves more than 3% in a day",
}
PRICE_MOVE_PCT = 3.0
PLACEMENT_DAYS = 7

# Rules you write yourself. Each watches one measurement and fires when it crosses a threshold.
RULE_METRICS = {
    "price_day": "Daily change of a symbol, in %",
    "price_level": "Price of a symbol, in £",
    "sleep_avg": "7-day average sleep, in hours",
    "open_tasks": "Number of open tasks",
    "needs_action_emails": "Recent emails needing action",
    "days_to_deadline": "Days until a placement deadline (organisation name as the subject)",
}


def enabled(kind):
    return bool(db.get_setting(f"trigger_{kind}", True))      # all three are on unless you switch one off


def set_enabled(kind, on):
    if kind not in KINDS:
        raise ValueError("Unknown trigger.")
    db.set_setting(f"trigger_{kind}", bool(on))


# ------------------------------------------------------------------
# Your own rules
# ------------------------------------------------------------------
def list_rules():
    return db.query("SELECT * FROM cass_rules ORDER BY id")


def add_rule(name, metric, op, threshold, subject=""):
    name, subject = str(name or "").strip(), str(subject or "").strip()
    if metric not in RULE_METRICS:
        raise ValueError("Pick one of the listed measurements.")
    if op not in ("above", "below"):
        raise ValueError("Pick above or below.")
    if metric in ("price_day", "price_level", "days_to_deadline") and not subject:
        raise ValueError("That measurement needs a subject: a symbol such as VWRP.L, or an organisation.")
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        raise ValueError("The threshold must be a number.")
    return db.execute("INSERT INTO cass_rules (name, metric, subject, op, threshold, enabled, created_ts) "
                      "VALUES (?, ?, ?, ?, ?, 1, ?)", (name or f"{metric} {op} {threshold:g}", metric, subject.upper()
                      if metric.startswith("price") else subject, op, threshold, time.time()))


def remove_rule(rule_id):
    db.execute("DELETE FROM cass_rules WHERE id = ?", (int(rule_id),))


def measure(metric, subject, now):
    """The current value of one measurement, or None when it cannot be worked out."""
    if metric in ("price_day", "price_level"):
        from services import market
        figures = market.summarise(market.get_history(subject), market.gbpusd_rate())
        return figures["day"] if metric == "price_day" else figures["price_gbp"]
    if metric == "sleep_avg":
        from cassiopeia import more_pages
        return more_pages.health_numbers()["week_sleep"]["average"]
    if metric == "open_tasks":
        return len(tasks.list_tasks())
    if metric == "needs_action_emails":
        return sum(1 for e in db.list_emails(120, include_done=False) if pages.needs_action(e))
    if metric == "days_to_deadline":
        deadlines = [p["deadline"] for p in tasks.list_placements()
                     if subject.lower() in (p["organisation"] or "").lower() and p.get("deadline")]
        return (date.fromisoformat(min(deadlines)) - now.date()).days if deadlines else None
    return None


def rule_candidates(now):
    """A rule fires at most once a day, so a price that stays low does not text you every five minutes."""
    found = []
    for rule in list_rules():
        if not rule["enabled"]:
            continue
        try:
            value = measure(rule["metric"], rule["subject"], now)
        except Exception:
            value = None
        if value is None:
            continue
        hit = value > rule["threshold"] if rule["op"] == "above" else value < rule["threshold"]
        db.execute("UPDATE cass_rules SET last_value = ?, last_checked_ts = ? WHERE id = ?", (value, time.time(), rule["id"]))
        if hit:
            subject = f" {rule['subject']}" if rule["subject"] else ""
            found.append(("rule", f"rule:{rule['id']}:{now.date().isoformat()}",
                          f"Rule '{rule['name']}':{subject} is {value:.2f}, {rule['op']} {rule['threshold']:g}"))
    return found


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

    for placement in tasks.list_placements():
        if placement["status"] in ("Researching", "Drafting") and placement.get("deadline"):
            left = (date.fromisoformat(placement["deadline"]) - now.date()).days
            if 0 <= left <= PLACEMENT_DAYS:
                found.append(("placement", f"placement:{placement['id']}:{placement['deadline']}",
                              f"{placement['organisation']} closes in {left} day{'' if left == 1 else 's'} ({placement['deadline']}) "
                              f"and is still marked {placement['status']}"))

    if enabled("price"):
        found += price_moves(now)

    day_ago = time.time() - 24 * 3600
    for email in db.list_emails(60, include_done=False):
        if (email.get("received_ts") or 0) >= day_ago and pages.needs_action(email) and pages.is_urgent(email):
            found.append(("email", f"email:{email['id']}",
                          f"Email needing action from {pages.sender_name(email.get('sender'))}: {email.get('subject')}"))
    return found


def price_moves(now):
    """Funds you hold that moved more than PRICE_MOVE_PCT on their latest trading day. Uses cached prices."""
    from database import finance
    from services import market
    moves = []
    for item in finance.list_watchlist("holding"):
        try:
            figures = market.summarise(market.get_history(item["symbol"]), market.gbpusd_rate(), item.get("currency"))
        except Exception:
            continue
        if figures["day"] is not None and abs(figures["day"]) >= PRICE_MOVE_PCT:
            moves.append(("price", f"price:{item['symbol']}:{figures['as_of']}",
                          f"{item['name'] or item['symbol']} moved {figures['day']:+.1f}% on {figures['as_of']}. "
                          "General information, not advice."))
    return moves


def check(now=None):
    """Announce anything new. Returns the messages sent this time."""
    now = now or events.now()
    if in_quiet_hours(now):
        return []
    sent = []
    for kind, key, message in candidates(now) + rule_candidates(now):
        if (kind != "rule" and not enabled(kind)) or db.query("SELECT 1 FROM cass_trigger_log WHERE key = ?", (key,)):
            continue
        db.execute("INSERT INTO cass_trigger_log (key, kind, message, fired_ts) VALUES (?, ?, ?, ?)",
                   (key, kind, message, time.time()))
        notify.mac_notification(config.APP_NAME, message)
        notify.text_me(message)          # logs itself as "off" if texting is not switched on
        sent.append(message)
    return sent


def status():
    return {"kinds": [{"kind": k, "about": about, "on": enabled(k)} for k, about in KINDS.items()],
            "rules": list_rules(), "metrics": RULE_METRICS,
            "quiet_hours": list(config.QUIET_HOURS),
            "recent": db.query("SELECT kind, message, fired_ts FROM cass_trigger_log ORDER BY fired_ts DESC LIMIT 8")}
