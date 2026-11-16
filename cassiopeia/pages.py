"""
pages.py
========
Purpose : The data behind the Calendar and Inbox pages of the Cassiopeia window.
          Each function returns plain dictionaries ready to be sent as JSON.
Location: cassiopeia/pages.py
Used by : cassiopeia/server.py, cassiopeia/triggers.py
Tokens  : Checking for new mail is free: rules sort it and Claude is not called.
          Claude reads an email only when you press Analyse or Draft a reply.
"""

import re
from datetime import datetime, timedelta

import config
from ai import claude
from cassiopeia import events
from database import database as db
from services import calendar as cal
from services import inbox

URGENT_WORDS = re.compile(r"\b(urgent|deadline|action required|final reminder|last chance to|interview|"
                          r"offer|overdue|respond by|reply by|due (today|tomorrow))\b", re.I)
PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


# ------------------------------------------------------------------
# Calendar
# ------------------------------------------------------------------
def parse_day(text):
    """'2026-11-17' -> midnight that day in UK time. Anything else -> today."""
    try:
        return datetime.fromisoformat(text).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=events.ZONE)
    except (TypeError, ValueError):
        return events.midnight()


def calendar(start=None, days=7):
    """Every event in a run of days, shaped for the week grid."""
    first = parse_day(start)
    days = max(1, min(int(days or 7), 31))
    found, errors = events.between(first, first + timedelta(days=days))
    shaped, booked = [], 0.0
    for event in found:
        begins, ends = cal.event_to_datetime(event)
        if begins is None:
            continue
        all_day = cal.is_all_day(event)
        if not all_day:
            booked += (ends - begins).total_seconds() / 3600
        shaped.append({"title": event.get("summary", "Untitled event"), "start": begins.isoformat(),
                       "end": ends.isoformat(), "all_day": all_day, "source": event.get("source", "Calendar"),
                       "local_id": event.get("local_id"), "notes": (event.get("description") or "")[:300]})
    return {"start": first.date().isoformat(), "days": days, "events": shaped, "errors": errors,
            "hours_booked": round(booked, 1), "today": events.now().date().isoformat()}


def free_time(day=None, start="09:00", end="18:00", minutes=60):
    """Gaps in one day between two clock times, and how many slots of a given length fit."""
    base = parse_day(day)
    try:
        begins = base.replace(hour=int(start[:2]), minute=int(start[3:5]))
        finishes = base.replace(hour=int(end[:2]), minute=int(end[3:5]))
        minutes = max(15, min(int(minutes), 480))
    except (TypeError, ValueError, IndexError):
        raise ValueError("Times must look like 09:00.")
    if finishes <= begins:
        raise ValueError("The end time must be after the start time.")
    day_events, _errors = events.between(base, base + timedelta(days=1))
    gaps = cal.free_ranges(day_events, begins, finishes)
    slots = cal.free_slots_from_events(day_events, begins, finishes, minutes)
    return {"day": base.date().isoformat(), "minutes": minutes, "slots": len(slots),
            "gaps": [{"from": a.strftime("%H:%M"), "to": b.strftime("%H:%M"),
                      "hours": round((b - a).total_seconds() / 3600, 1)} for a, b in gaps]}


# ------------------------------------------------------------------
# Inbox
# ------------------------------------------------------------------
def gmail_service():
    """The Gmail connection, or None when Google is not connected. Never opens a browser."""
    from services import gmail, google_auth
    if not (google_auth.is_configured() and google_auth.has_token()):
        return None
    return gmail.get_gmail_service(interactive=False)


def sender_name(sender):
    return (sender or "Unknown").split("<")[0].strip().strip('"') or (sender or "Unknown")


def is_urgent(email):
    """Worth an unprompted text? Claude's verdict if there is one, otherwise a cautious word rule."""
    analysis = email["analysis"]
    if email.get("analysed_by") == "claude":
        return analysis["priority"] == "High" and analysis["action_required"]
    if email.get("analysed_by") == "rules":          # the rules only ever file bulk mail
        return False
    return bool(URGENT_WORDS.search(email.get("subject") or ""))


def shape_email(email):
    return {"id": email["id"], "sender": sender_name(email.get("sender")), "address": email.get("sender"),
            "subject": email.get("subject") or "(no subject)", "received_ts": email.get("received_ts"),
            "analysis": email["analysis"], "analysed_by": email.get("analysed_by") or "pending",
            "status": email["status"], "draft_reply": email.get("draft_reply"), "provider": email.get("provider"),
            "urgent": is_urgent(email), "body": (email.get("body") or "")[:2500]}


def inbox_list(show="open"):
    """Emails for the page. Those needing action come first, then by priority, then newest."""
    rows = [shape_email(e) for e in db.list_emails(120, include_done=(show != "open"))]
    if show == "done":
        rows = [r for r in rows if r["status"] == "completed"]
    rows.sort(key=lambda r: (not (r["analysis"]["action_required"] or r["urgent"]),
                             PRIORITY_ORDER.get(r["analysis"]["priority"], 3), -(r["received_ts"] or 0)))
    since = inbox.minutes_since_sync()
    return {"emails": rows, "pending": len(db.pending_emails(500)),
            "minutes_since_sync": None if since is None else round(since),
            "connected": gmail_service() is not None, "claude": claude.is_available(),
            "gmail_drafts": config.ENABLE_GMAIL_DRAFTS, "analyse_cap": config.MAX_AI_EMAILS_PER_SYNC}


def inbox_sync(analyse=False):
    """Fetch new mail. analyse=False costs nothing. analyse=True also sends pending mail to Claude."""
    service = gmail_service()
    if service is None:
        raise RuntimeError("Google is not connected. Connect it from the classic dashboard's Settings page first.")
    return inbox.sync(service, analyse=analyse)


def _email(email_id):
    email = db.get_cached_email(email_id)
    if email is None:
        raise ValueError("That email is no longer stored.")
    return email


def analyse_one(email_id):
    inbox.reanalyse(_email(email_id))
    return shape_email(_email(email_id))


def draft_reply(email_id):
    """Ask Claude for a reply draft, offering real free slots if the email asked about availability."""
    email, slots = _email(email_id), None
    window = cal.requested_window(email["analysis"]) if email["analysis"].get("availability_request") else None
    if window:
        day_events, _errors = events.between(window[0].replace(hour=0, minute=0), window[0].replace(hour=0, minute=0) + timedelta(days=1))
        slots = cal.free_slots_from_events(day_events, window[0], window[1], config.TUTORING_LESSON_MINUTES)
    db.update_draft_reply(email_id, claude.draft_reply(email, slots))
    return shape_email(_email(email_id))


def save_draft(email_id, text, to_gmail=False):
    """Keep an edited draft. With to_gmail it is also placed in Gmail's Drafts folder. Nothing is sent."""
    email = _email(email_id)
    db.update_draft_reply(email_id, text)
    if to_gmail:
        if not config.ENABLE_GMAIL_DRAFTS:
            raise RuntimeError("Saving to Gmail is off. Set ENABLE_GMAIL_DRAFTS=true in .env, delete token.json and reconnect Google.")
        from services import gmail
        gmail.create_draft(gmail_service(), email, text)
    return shape_email(_email(email_id))


def discard_draft(email_id):
    db.clear_draft_reply(email_id)
    return shape_email(_email(email_id))


def set_done(email_id, done=True):
    db.update_email_status(email_id, "completed" if done else "open")
    return shape_email(_email(email_id))


# ------------------------------------------------------------------
# Money (figures you entered yourself; nothing here is advice)
# ------------------------------------------------------------------
ACCOUNT_KINDS = {"current": "Current account", "savings": "Savings", "investment": "Stocks and Shares ISA",
                 "lisa": "Lifetime ISA", "overdraft": "Overdraft", "other": "Other"}
MONEY_NOTE = "These are the figures you entered. General information, not personal financial advice."


def money():
    """Accounts, net worth, ISA allowances, monthly budget and the overdraft plan."""
    from datetime import date
    from database import finance
    accounts = finance.list_accounts()
    paid = finance.contributions_this_tax_year()
    isa_paid, lisa_paid = paid.get("investment", 0) + paid.get("lisa", 0), paid.get("lisa", 0)
    overdraft = next((a for a in accounts if a["kind"] == "overdraft"), None)
    owed = abs(overdraft["balance"]) if overdraft and overdraft["balance"] else 0.0
    target = db.get_setting("pref_overdraft_clear_by", "2029-07-01")     # shared with the classic dashboard
    plan = finance.payoff_plan(owed, finance.parse_date(target) or date(2029, 7, 1)) if owed else None
    return {
        "accounts": [{"id": a["id"], "name": a["name"], "kind": ACCOUNT_KINDS.get(a["kind"], a["kind"]), "kind_key": a["kind"],
                      "rate": a["interest_rate"], "balance": a["balance"], "balance_date": a["balance_date"],
                      "is_liability": bool(a["is_liability"])} for a in accounts],
        "worth": finance.net_worth(accounts), "history": finance.net_worth_history(),
        "tax_year_start": finance.tax_year_start().isoformat(),
        "allowances": [
            {"name": "ISA allowance, all ISAs together", "used": isa_paid, "limit": config.ISA_ALLOWANCE},
            {"name": "Lifetime ISA", "used": lisa_paid, "limit": config.LISA_ALLOWANCE,
             "bonus": lisa_paid * config.LISA_BONUS_RATE}],
        "budget": finance.monthly_budget(), "recurring": finance.list_recurring(),
        "overdraft": {"owed": owed, "target": target, "plan": plan}, "note": MONEY_NOTE,
    }


def _amount(value, name="Amount"):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")


def money_update(action, body):
    """Every change the Money page can make. Returns the refreshed page."""
    from database import finance
    if action == "balance":
        finance.record_balance(int(body["account_id"]), _amount(body.get("balance"), "Balance"), body.get("date") or None)
    elif action == "contribution":
        finance.add_contribution(int(body["account_id"]), _amount(body.get("amount")), body.get("date") or None)
    elif action == "recurring":
        if body.get("kind") not in ("income", "expense") or not str(body.get("name", "")).strip():
            raise ValueError("A regular item needs a name and a kind of income or expense.")
        frequency = body.get("frequency") if body.get("frequency") in finance.MONTHLY_FACTOR else "monthly"
        finance.add_recurring(body["name"].strip(), body["kind"], _amount(body.get("amount")), frequency)
    elif action == "set-recurring":
        finance.update_recurring(int(body["id"]), _amount(body.get("amount")))
    elif action == "remove-recurring":
        finance.delete_recurring(int(body["id"]))
    elif action == "overdraft-target":
        if not finance.parse_date(body.get("date")):
            raise ValueError("Pick a date to clear the overdraft by.")
        db.set_setting("pref_overdraft_clear_by", body["date"])
    else:
        raise ValueError("Unknown money action.")
    return money()


# ------------------------------------------------------------------
# University
# ------------------------------------------------------------------
def university_page():
    """Module standings against the degree target, open assessments, the review queue and study time."""
    from database import university
    modules, assessments = university.list_modules(), university.list_assessments()
    minutes = {}
    for row in university.study_minutes(28):
        minutes[row["module"]] = minutes.get(row["module"], 0) + (row["minutes"] or 0)
    standings = []
    for module in modules:
        own = [a for a in assessments if a["module_id"] == module["id"]]
        standings.append(dict(university.module_standing(own, config.DEGREE_TARGET), id=module["id"],
                              name=module["name"], code=module["code"], assessments=len(own),
                              study_minutes=minutes.get(module["name"], 0)))
    return {"target": config.DEGREE_TARGET, "modules": standings,
            "open": [a for a in assessments if a["status"] != "done"],
            "marked": [a for a in assessments if a["mark"] is not None][-12:],
            "reviews": university.reviews_due(), "recent_lectures": university.recent_lectures(8),
            "study_total": sum(minutes.values())}


def university_update(action, body):
    """Every change the University page can make. Returns the refreshed page."""
    from database import university
    if action == "assessment":
        if not str(body.get("title", "")).strip():
            raise ValueError("The assessment needs a title.")
        weight = _amount(body["weight"], "Weight") if str(body.get("weight", "")).strip() else None
        university.add_assessment(int(body["module_id"]), body["title"].strip(), body.get("due") or None, weight)
    elif action == "mark":
        mark = _amount(body.get("mark"), "Mark")
        if not 0 <= mark <= 100:
            raise ValueError("A mark is between 0 and 100.")
        university.set_mark(int(body["id"]), mark)
    elif action == "done":
        university.set_assessment_status(int(body["id"]), "done")
    elif action == "lecture":
        rating = int(_amount(body.get("understanding"), "Understanding"))
        if not str(body.get("topic", "")).strip() or not 1 <= rating <= 5:
            raise ValueError("A lecture needs a topic and an understanding score from 1 to 5.")
        university.log_lecture(int(body["module_id"]), body["topic"].strip(), rating)
    elif action == "review":
        university.complete_review(int(body["id"]), int(_amount(body.get("understanding"), "Understanding")))
    elif action == "study":
        university.log_study(int(body["module_id"]), _amount(body.get("minutes"), "Minutes"), body.get("note", ""))
    else:
        raise ValueError("Unknown university action.")
    return university_page()
