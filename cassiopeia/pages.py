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
