"""
context.py
==========
Purpose : Builds the short block of facts the assistant is given about your day.
Location: ai/context.py
Used by : views/assistant.py, views/home.py
Note    : Smaller context means fewer tokens. Each section is a few lines, and the
          chat page lets you switch sections off.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import config
from database import database as db
from database import finance, health, tasks, university
from services import training
from services.calendar import describe_event, event_day

SOURCES = ["Email", "Calendar", "Tasks", "University", "Health", "Finance"]
DEFAULT_SOURCES = ["Email", "Calendar", "Tasks", "University"]


def _email_section():
    emails = [e for e in db.list_emails(40, include_done=False) if e["analysis"]["action_required"]]
    if not emails:
        return "EMAILS NEEDING ACTION: none."
    lines = ["EMAILS NEEDING ACTION:"]
    for email in emails[:8]:
        analysis = email["analysis"]
        sender = (email.get("sender") or "Unknown").split("<")[0].strip().strip('"')
        lines.append(f"- [{analysis['priority']}] {email.get('subject')} (from {sender}): {analysis['summary']}")
    return "\n".join(lines)


def _calendar_section(events):
    if not events:
        return "CALENDAR, NEXT 7 DAYS: nothing scheduled, or the calendar is not connected."
    lines = ["CALENDAR, NEXT 7 DAYS:"]
    for event in events[:25]:
        lines.append(f"- {event_day(event)}: {describe_event(event)}")
    return "\n".join(lines)


def _tasks_section():
    groups = tasks.group_tasks(tasks.list_tasks())
    lines = ["TASKS:"]
    for name in ("Overdue", "Today", "Upcoming"):
        for task in groups[name][:6]:
            lines.append(f"- {name}: {task['title']} ({task['priority']}, due {task['due']})")
    return "\n".join(lines) if len(lines) > 1 else "TASKS: none with a due date."


def _university_section():
    lines = ["UNIVERSITY:"]
    for item in university.list_assessments(only_open=True)[:8]:
        weight = f", worth {item['weight']:g}%" if item.get("weight") else ""
        lines.append(f"- Due {item['due'] or 'no date'}: {item['title']} ({item['module']}{weight})")
    due = university.reviews_due()
    if due:
        lines.append(f"- {len(due)} lecture reviews are due.")
    minutes = sum(row["minutes"] for row in university.study_minutes(7))
    lines.append(f"- Study logged in the last 7 days: {minutes / 60:.1f} h. Degree target: {config.DEGREE_TARGET:g}%.")
    return "\n".join(lines)


def _health_section():
    stats = training.sleep_stats(health.get_sleep(7), config.SLEEP_TARGET_HOURS)
    load = training.weekly_load(health.get_workouts(28))
    lines = ["HEALTH (last 7 days):"]
    if stats["nights"]:
        lines.append(f"- Sleep: {stats['average']:.1f} h average over {stats['nights']} nights, "
                     f"debt {stats['debt']:.1f} h against a {config.SLEEP_TARGET_HOURS:g} h target.")
    else:
        lines.append("- Sleep: nothing logged.")
    if load:
        latest = load[-1]
        lines.append(f"- This week: {latest['strength']} strength sessions, {latest['runs']} runs, {latest['run_km']:.1f} km.")
    lines.append(f"- Goal: build muscle and fitness. Plan: {config.GYM_DAYS_PER_WEEK} gym days and {config.RUN_DAYS_PER_WEEK} runs a week.")
    return "\n".join(lines)


def _finance_section():
    accounts = finance.list_accounts()
    worth = finance.net_worth(accounts)
    if not worth["has_data"]:
        return "FINANCE: no balances entered yet."
    lines = ["FINANCE (figures Ben entered):"]
    for account in accounts:
        if account["balance"] is not None:
            rate = f", {account['interest_rate']:g}% interest" if account.get("interest_rate") else ""
            lines.append(f"- {account['name']} ({account['provider']}): £{account['balance']:,.0f}{rate}")
    budget = finance.monthly_budget()
    lines.append(f"- Net worth £{worth['net']:,.0f}. Monthly income £{budget['income']:,.0f}, "
                 f"fixed costs £{budget['costs']:,.0f} (rent £{config.RENT_PER_MONTH:,.0f}).")
    return "\n".join(lines)


def build_context(sources=None, events=None):
    """Return the context text for the chosen sources. `events` is the week's calendar."""
    sources = DEFAULT_SOURCES if sources is None else sources
    now = datetime.now(ZoneInfo(config.TIMEZONE))
    parts = [f"NOW: {now.strftime('%A %d %B %Y, %H:%M')} ({config.TIMEZONE})."]
    builders = {
        "Email": _email_section,
        "Calendar": lambda: _calendar_section(events or []),
        "Tasks": _tasks_section,
        "University": _university_section,
        "Health": _health_section,
        "Finance": _finance_section,
    }
    for name in SOURCES:
        if name in sources:
            try:
                parts.append(builders[name]())
            except Exception as error:   # one broken section must not break the chat
                parts.append(f"{name.upper()}: unavailable ({error}).")
    return "\n\n".join(parts)
