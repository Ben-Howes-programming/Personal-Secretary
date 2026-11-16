"""
apple.py
========
Purpose : Optional Apple connections.
            1. Apple Health import from the export file your iPhone makes (tested with sample data).
            2. iCloud Mail over IMAP (read-only).
            3. iCloud Calendar over CalDAV (read-only, needs `pip install caldav`).
Location: services/apple.py
Used by : views/health.py, services/inbox.py, ui/state.py, views/settings.py
Status  : The Health import is covered by tests. Mail and Calendar follow Apple's
          published server settings but have NOT been run against a live iCloud
          account, so treat the first connection as a test.
Setup   : iCloud Mail and Calendar need an app-specific password, never your Apple
          ID password. Create one at https://account.apple.com (Sign-In and Security,
          App-Specific Passwords) and put it in .env as ICLOUD_APP_PASSWORD, with
          your iCloud address as ICLOUD_USER.
Note    : Apple has no web API for Health. Export from the Health app instead:
          profile picture, Export All Health Data, then AirDrop the zip to your Mac.
"""

import hashlib
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import config

LOCAL = ZoneInfo(config.TIMEZONE)
ASLEEP = ("Asleep",)   # matches AsleepCore, AsleepDeep, AsleepREM, AsleepUnspecified and the older Asleep
RUN_TYPES = ("Running",)
STRENGTH_TYPES = ("StrengthTraining", "FunctionalStrength", "CrossTraining")


# ------------------------------------------------------------------
# 1. Apple Health export
# ------------------------------------------------------------------
def _when(text):
    """Apple writes '2026-11-01 23:15:00 +0000'. Returns a UK-local datetime."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z").astimezone(LOCAL)


def _open_export(source):
    """Accept the export .zip or the export.xml inside it, as a path or an uploaded file."""
    data = source if hasattr(source, "read") else open(source, "rb")
    head = data.read(4)
    data.seek(0)
    if head.startswith(b"PK"):   # a zip file
        archive = zipfile.ZipFile(data)
        name = next((n for n in archive.namelist() if n.endswith("export.xml")), None)
        if name is None:
            raise ValueError("No export.xml found inside that zip.")
        return archive.open(name)
    return data


def parse_health_export(source, days=120):
    """Read sleep, workouts, weight, steps and resting heart rate from an Apple Health export.

    The file is read as a stream, so a large export does not fill memory.
    Returns {"sleep": [...], "workouts": [...], "body": {date: {...}}}.
    """
    cutoff = datetime.now(LOCAL) - timedelta(days=days)
    nights, workouts, body = {}, [], {}

    for _event, node in ET.iterparse(_open_export(source), events=("end",)):
        if node.tag == "Record":
            kind = node.get("type", "")
            try:
                start, end = _when(node.get("startDate")), _when(node.get("endDate"))
            except (TypeError, ValueError):
                node.clear()
                continue
            if end >= cutoff:
                day = end.date().isoformat()
                if kind == "HKCategoryTypeIdentifierSleepAnalysis" and any(tag in node.get("value", "") for tag in ASLEEP):
                    # A night is filed under the date you woke up. Evening naps after 15:00 count towards the next day.
                    night_date = (end + timedelta(hours=9)).date().isoformat()
                    night = nights.setdefault(night_date, {"start": start, "end": end, "seconds": 0.0})
                    night["start"], night["end"] = min(night["start"], start), max(night["end"], end)
                    night["seconds"] += (end - start).total_seconds()
                elif kind == "HKQuantityTypeIdentifierBodyMass":
                    value = float(node.get("value", 0))
                    if node.get("unit") == "lb":
                        value *= 0.45359237
                    body.setdefault(day, {})["weight_kg"] = round(value, 1)
                elif kind == "HKQuantityTypeIdentifierStepCount":
                    entry = body.setdefault(day, {})
                    entry["steps"] = entry.get("steps", 0) + int(float(node.get("value", 0)))
                elif kind == "HKQuantityTypeIdentifierRestingHeartRate":
                    body.setdefault(day, {})["resting_hr"] = float(node.get("value", 0))
            node.clear()
        elif node.tag == "Workout":
            try:
                start = _when(node.get("startDate"))
            except (TypeError, ValueError):
                node.clear()
                continue
            if start >= cutoff:
                activity = node.get("workoutActivityType", "").replace("HKWorkoutActivityType", "")
                minutes = float(node.get("duration") or 0)
                if node.get("durationUnit") == "s":
                    minutes /= 60
                distance = node.get("totalDistance")
                unit = node.get("totalDistanceUnit")
                if distance is None:   # newer exports keep distance in a child element
                    for child in node.iter("WorkoutStatistics"):
                        if "Distance" in child.get("type", ""):
                            distance, unit = child.get("sum"), child.get("unit")
                            break
                km = float(distance) if distance else None
                if km and unit == "mi":
                    km *= 1.609344
                if km and unit == "m":
                    km /= 1000
                if any(tag in activity for tag in RUN_TYPES):
                    kind = "run"
                elif any(tag in activity for tag in STRENGTH_TYPES):
                    kind = "strength"
                else:
                    kind = "other"
                workouts.append({"date": start.date().isoformat(), "kind": kind, "title": activity,
                                 "duration_min": round(minutes, 1), "distance_km": round(km, 2) if km else None})
            node.clear()

    sleep = [{"date": day, "bed_time": night["start"].strftime("%H:%M"), "wake_time": night["end"].strftime("%H:%M"),
              "hours": round(night["seconds"] / 3600, 2)} for day, night in sorted(nights.items())]
    return {"sleep": sleep, "workouts": workouts, "body": body}


def save_health_import(parsed):
    """Write a parsed export into the database. Manual entries are never overwritten."""
    from database import health
    from database.database import query
    manual_nights = {row["date"] for row in query("SELECT date FROM sleep WHERE source = 'manual'")}
    counts = {"sleep": 0, "workouts": 0, "body": 0}
    for night in parsed["sleep"]:
        if night["date"] not in manual_nights:
            health.log_sleep(night["date"], night["bed_time"], night["wake_time"], hours=night["hours"], source="apple")
            counts["sleep"] += 1
    for workout in parsed["workouts"]:
        if not health.workout_exists(workout["date"], workout["kind"], workout["duration_min"]):
            health.log_workout(workout["date"], workout["kind"], workout["title"], workout["duration_min"],
                               workout["distance_km"], source="apple")
            counts["workouts"] += 1
    for day, values in parsed["body"].items():
        health.log_body(day, weight_kg=values.get("weight_kg"), resting_hr=values.get("resting_hr"), steps=values.get("steps"))
        counts["body"] += 1
    return counts


# ------------------------------------------------------------------
# 2. iCloud Mail (IMAP, read-only)
# ------------------------------------------------------------------
def mail_configured():
    return bool(config.ICLOUD_USER and config.ICLOUD_APP_PASSWORD)


def _header(message, name):
    return str(make_header(decode_header(message.get(name, "")))) if message.get(name) else ""


def message_to_email(raw_bytes):
    """Convert a raw email into the same shape as services/gmail.get_email."""
    from services.gmail import html_to_text
    message = message_from_bytes(raw_bytes)
    plain, html = None, None
    for part in message.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and plain is None:
            plain = text
        elif part.get_content_type() == "text/html" and html is None:
            html = text
    body = plain if plain is not None else (html_to_text(html) if html else "[No readable body found]")
    stamp = None
    try:
        stamp = parsedate_to_datetime(message.get("Date")).timestamp()
    except (TypeError, ValueError):
        pass
    identity = message.get("Message-ID") or (_header(message, "Subject") + str(message.get("Date")))
    return {
        "id": "icloud:" + hashlib.sha1(identity.encode("utf-8", "replace")).hexdigest()[:24],
        "provider": "icloud", "thread_id": None, "sender": _header(message, "From") or "Unknown",
        "subject": _header(message, "Subject") or "No subject", "date": message.get("Date", "Unknown"),
        "received_ts": stamp, "body": body.strip(), "snippet": body.strip()[:180], "labels": [],
        "list_unsubscribe": message.get("List-Unsubscribe") is not None,
    }


def fetch_mail(limit=25):
    """The newest messages in the iCloud inbox. The mailbox is opened read-only."""
    import imaplib
    box = imaplib.IMAP4_SSL("imap.mail.me.com", 993)
    try:
        box.login(config.ICLOUD_USER, config.ICLOUD_APP_PASSWORD)
        box.select("INBOX", readonly=True)
        _status, data = box.search(None, "ALL")
        numbers = data[0].split()[-limit:]
        emails = []
        for number in reversed(numbers):
            _status, parts = box.fetch(number, "(BODY.PEEK[])")
            raw = next((part[1] for part in parts if isinstance(part, tuple)), None)
            if raw:
                emails.append(message_to_email(raw))
        return emails
    finally:
        try:
            box.logout()
        except Exception:
            pass


# ------------------------------------------------------------------
# 3. iCloud Calendar (CalDAV, read-only)
# ------------------------------------------------------------------
def calendar_configured():
    if not mail_configured():
        return False
    try:
        import caldav  # noqa: F401
    except ImportError:
        return False
    return True


def list_events(start_dt, end_dt):
    """iCloud events in Google's shape, so services/calendar.py can use them unchanged."""
    import caldav
    client = caldav.DAVClient(url="https://caldav.icloud.com", username=config.ICLOUD_USER,
                              password=config.ICLOUD_APP_PASSWORD)
    events = []
    for calendar in client.principal().calendars():
        try:
            found = calendar.search(start=start_dt, end=end_dt, event=True, expand=True)
        except Exception:
            continue
        for item in found:
            for component in item.icalendar_instance.walk("VEVENT"):
                start, end = component.get("dtstart"), component.get("dtend")
                if start is None:
                    continue
                start, end = start.dt, (end.dt if end is not None else start.dt)
                if isinstance(start, datetime):
                    shaped = {"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}}
                else:
                    shaped = {"start": {"date": start.isoformat()}, "end": {"date": end.isoformat()}}
                shaped.update(summary=str(component.get("summary", "Untitled event")), source="iCloud")
                if str(component.get("transp", "")).upper() == "TRANSPARENT":
                    shaped["transparency"] = "transparent"
                events.append(shaped)
    return events
