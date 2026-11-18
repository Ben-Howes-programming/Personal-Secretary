"""
feeds.py
========
Purpose : Calendar feeds you subscribe to by link (iCal, .ics or webcal://).
          "Timetable" feeds, such as your Bath MyTimetable link, count as busy time.
          "Suggestions" feeds, such as a society or events calendar, never block time:
          they appear as ideas in the Calendar tab and the morning briefing.
Location: cassiopeia/feeds.py
Used by : cassiopeia/events.py, cassiopeia/briefing.py, cassiopeia/server.py
Note    : A personal timetable link works like a password (anyone with it can read your
          timetable), so links are kept in the local database only and never shown in full.
          Repeating events written as a rule (RRULE) only show their first date; most
          university timetable feeds list every lecture separately, so this rarely matters.
"""

import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

import config
from database import database as db

KINDS = {"timetable": "Counts as busy time", "suggestions": "Ideas only, never blocks time"}
FETCH_TTL = 3600                      # re-download each feed at most once an hour
LOCAL = ZoneInfo(config.TIMEZONE)


# ------------------------------------------------------------------
# Parsing (pure functions, tested)
# ------------------------------------------------------------------
def unfold(text):
    """iCal wraps long lines by starting the continuation with a space or tab. Join them back."""
    return re.sub(r"\r?\n[ \t]", "", text).replace("\r\n", "\n").split("\n")


def unescape(value):
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def parse_when(params, value):
    """(datetime or date, is_all_day) from a DTSTART/DTEND property."""
    value = value.strip()
    if "VALUE=DATE" in params.upper() or re.fullmatch(r"\d{8}", value):
        return date(int(value[:4]), int(value[4:6]), int(value[6:8])), True
    moment = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(LOCAL), False
    tzid = re.search(r"TZID=([^;:]+)", params)
    try:
        zone = ZoneInfo(tzid.group(1).strip('"')) if tzid else LOCAL
    except (ZoneInfoNotFoundError, ValueError):
        zone = LOCAL                   # Windows-style zone names: assume UK time
    return moment.replace(tzinfo=zone).astimezone(LOCAL), False


def parse_ics(text):
    """Every VEVENT as a dictionary in Google Calendar's shape, which the rest of the app uses."""
    found, current = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if "start" in current:
                found.append(current)
            current = None
        elif current is not None and ":" in line:
            head, value = line.split(":", 1)
            name, _, params = head.partition(";")
            try:
                if name in ("DTSTART", "DTEND"):
                    moment, all_day = parse_when(params, value)
                    key = "start" if name == "DTSTART" else "end"
                    current[key] = {"date": moment.isoformat()} if all_day else {"dateTime": moment.isoformat()}
                elif name == "SUMMARY":
                    current["summary"] = unescape(value)
                elif name == "LOCATION":
                    current["location"] = unescape(value)
                elif name == "DESCRIPTION":
                    current["description"] = unescape(value)[:500]
                elif name == "URL":
                    current["link"] = value.strip()
                elif name == "STATUS" and value.strip().upper() == "CANCELLED":
                    current["cancelled"] = True
            except ValueError:
                continue                 # one malformed line must not lose the whole feed
    for event in found:
        if "end" not in event:           # no end given: an hour, or the whole day for dates
            start = event["start"]
            if "date" in start:
                event["end"] = {"date": (date.fromisoformat(start["date"]) + timedelta(days=1)).isoformat()}
            else:
                event["end"] = {"dateTime": (datetime.fromisoformat(start["dateTime"]) + timedelta(hours=1)).isoformat()}
    return [e for e in found if not e.get("cancelled")]


# ------------------------------------------------------------------
# Subscriptions
# ------------------------------------------------------------------
def normalise_url(url):
    url = (url or "").strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not re.match(r"https?://[^\s/]+\.[^\s]+", url):
        raise ValueError("Paste the full calendar link, starting with https:// or webcal://.")
    return url


def masked(url):
    """Show enough of a link to recognise it, never the secret part."""
    host = re.sub(r"^https?://", "", url).split("/")[0]
    return f"{host}/..."


def add(name, url, kind):
    if kind not in KINDS:
        raise ValueError("Pick timetable or suggestions.")
    name = str(name or "").strip() or ("Timetable" if kind == "timetable" else "Suggestions")
    return db.execute("INSERT INTO cass_feeds (name, url, kind, created_ts) VALUES (?, ?, ?, ?)",
                      (name[:60], normalise_url(url), kind, time.time()))


def remove(feed_id):
    feed = db.query("SELECT id FROM cass_feeds WHERE id = ?", (int(feed_id),))
    db.execute("DELETE FROM cass_feeds WHERE id = ?", (int(feed_id),))
    db.cache_clear(f"feed:{int(feed_id)}")
    return bool(feed)


def listing():
    return [{"id": f["id"], "name": f["name"], "kind": f["kind"], "where": masked(f["url"]),
             "count": f["last_count"], "error": f["last_error"], "fetched_ts": f["last_fetch_ts"]}
            for f in db.query("SELECT * FROM cass_feeds ORDER BY kind, name")]


def fetch(feed, force=False):
    """Events from one feed, downloaded at most once an hour. A failed download keeps the last good copy."""
    key = f"feed:{feed['id']}"
    cached = None if force else db.cache_get(key)
    if cached is not None:
        return cached
    try:
        response = requests.get(feed["url"], timeout=15, headers={"User-Agent": "Cassiopeia calendar"})
        response.raise_for_status()
        found = parse_ics(response.text)
        error = None
    except Exception as problem:
        found, error = db.cache_get(key, allow_stale=True) or [], f"Could not fetch: {str(problem)[:120]}"
    for event in found:
        event["source"] = feed["name"]
        if feed["kind"] == "suggestions":
            event["transparency"] = "transparent"     # never blocks time in free-slot maths
            event["suggestion"] = True
    if error is None:
        db.cache_set(key, found, FETCH_TTL)
    db.execute("UPDATE cass_feeds SET last_fetch_ts = ?, last_count = ?, last_error = ? WHERE id = ?",
               (time.time(), len(found), error, feed["id"]))
    return found


def events_between(start, end, force=False):
    """Events from every feed overlapping [start, end)."""
    from services import calendar as cal
    chosen = []
    for feed in db.query("SELECT * FROM cass_feeds"):
        for event in fetch(feed, force):
            begins, finishes = cal.event_to_datetime(event)
            if begins is not None and begins < end and finishes > start:
                chosen.append(event)
    return chosen


def suggestions(days=7, limit=8):
    """Upcoming ideas from suggestion feeds, soonest first."""
    from cassiopeia import events
    from services import calendar as cal
    start = events.now()
    found = [e for e in events_between(start, start + timedelta(days=days)) if e.get("suggestion")]
    found.sort(key=lambda e: cal.event_to_datetime(e)[0])
    return [{"title": e.get("summary", "Event"), "when": f"{cal.event_day(e)}, {cal.describe_event(e).split('  ')[0]}",
             "where": e.get("location", ""), "link": e.get("link", ""), "source": e["source"]} for e in found[:limit]]
