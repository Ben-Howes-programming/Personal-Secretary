"""
store.py
========
Purpose : Cassiopeia's own tables (memories, planned events, briefings, messages sent,
          vault index, trading lab results, simulations, self-updates, job history).
Location: cassiopeia/store.py
Used by : every other file in cassiopeia/
Note    : Follows rule 7 in CLAUDE.md. Tables are only ever added, never dropped or renamed.
"""

import json
import time

from database import database as db

SCHEMA = """
CREATE TABLE IF NOT EXISTS cass_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, kind TEXT DEFAULT 'fact', created_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, start_iso TEXT NOT NULL, end_iso TEXT,
    notes TEXT DEFAULT '', created_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, day TEXT, text TEXT, written_by TEXT, created_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, body TEXT, status TEXT, detail TEXT, created_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_vault (
    id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, name TEXT, area TEXT, unit TEXT, kind TEXT,
    size INTEGER, text TEXT DEFAULT '', added_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_day TEXT, symbol TEXT, strategy TEXT, trades INTEGER,
    total_return REAL, annualised REAL, win_rate REAL, max_drawdown REAL
);
CREATE TABLE IF NOT EXISTS cass_paper (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, strategy TEXT, symbol TEXT, day_return REAL, equity REAL,
    UNIQUE(day, strategy, symbol)
);
CREATE TABLE IF NOT EXISTS cass_sims (
    id INTEGER PRIMARY KEY AUTOINCREMENT, prompt TEXT, code TEXT, status TEXT, output TEXT DEFAULT '',
    files TEXT DEFAULT '[]', created_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, instruction TEXT, branch TEXT, worktree TEXT, status TEXT,
    diff TEXT DEFAULT '', test_output TEXT DEFAULT '', created_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_jobs (
    name TEXT PRIMARY KEY, last_run_ts REAL, last_status TEXT, last_detail TEXT
);
CREATE TABLE IF NOT EXISTS cass_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, metric TEXT, subject TEXT DEFAULT '', op TEXT, threshold REAL,
    enabled INTEGER DEFAULT 1, last_value REAL, last_checked_ts REAL, created_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_trigger_log (
    key TEXT PRIMARY KEY, kind TEXT, message TEXT, fired_ts REAL
);
CREATE TABLE IF NOT EXISTS cass_activity (
    day TEXT, app TEXT, minutes INTEGER DEFAULT 0, PRIMARY KEY (day, app)
);
"""


def initialise():
    """Create the main app's tables first, then Cassiopeia's. Safe to call every start."""
    db.initialise_database()
    with db.connect() as c:
        c.executescript(SCHEMA)
        # Emails analysed by version 0.5 carry stale "needs action" flags with no record of who set them.
        # Mark them as legacy once, so they stop crowding the inbox. Nothing is deleted.
        c.execute("UPDATE emails SET analysed_by = 'legacy' WHERE analysed_by IS NULL")
        have = {row["name"] for row in c.execute("PRAGMA table_info(cass_backtests)").fetchall()}
        for column in ("exposure REAL", "switches INTEGER"):           # added 18 Nov 2026 for the new lab rules
            if column.split()[0] not in have:
                c.execute(f"ALTER TABLE cass_backtests ADD COLUMN {column}")


# Memories ----------------------------------------------------------
def remember(text, kind="fact"):
    text = (text or "").strip()
    if not text:
        return None
    same = db.query("SELECT id FROM cass_memories WHERE text = ?", (text,))   # no duplicates
    return same[0]["id"] if same else db.execute(
        "INSERT INTO cass_memories (text, kind, created_ts) VALUES (?, ?, ?)", (text, kind, time.time()))


def memories(limit=60):
    return db.query("SELECT * FROM cass_memories ORDER BY created_ts DESC LIMIT ?", (limit,))


def forget(memory_id):
    db.execute("DELETE FROM cass_memories WHERE id = ?", (memory_id,))


# Planned events (kept locally; Google Calendar stays read-only unless you opt in) ----
def add_event(title, start_iso, end_iso=None, notes=""):
    return db.execute("INSERT INTO cass_events (title, start_iso, end_iso, notes, created_ts) VALUES (?, ?, ?, ?, ?)",
                      (title.strip(), start_iso, end_iso, notes or "", time.time()))


def events_between(start_iso, end_iso):
    return db.query("SELECT * FROM cass_events WHERE start_iso >= ? AND start_iso < ? ORDER BY start_iso",
                    (start_iso, end_iso))


def delete_event(event_id):
    db.execute("DELETE FROM cass_events WHERE id = ?", (event_id,))


# Briefings and messages ---------------------------------------------
def save_briefing(kind, day, text, written_by):
    return db.execute("INSERT INTO cass_briefings (kind, day, text, written_by, created_ts) VALUES (?, ?, ?, ?, ?)",
                      (kind, day, text, written_by, time.time()))


def latest_briefings(limit=4):
    return db.query("SELECT * FROM cass_briefings ORDER BY created_ts DESC LIMIT ?", (limit,))


def log_outbox(channel, body, status, detail=""):
    return db.execute("INSERT INTO cass_outbox (channel, body, status, detail, created_ts) VALUES (?, ?, ?, ?, ?)",
                      (channel, body[:2000], status, detail[:500], time.time()))


def outbox(limit=20):
    return db.query("SELECT * FROM cass_outbox ORDER BY created_ts DESC LIMIT ?", (limit,))


# Jobs --------------------------------------------------------------
def job_ran(name, status, detail=""):
    db.execute("INSERT OR REPLACE INTO cass_jobs (name, last_run_ts, last_status, last_detail) VALUES (?, ?, ?, ?)",
               (name, time.time(), status, str(detail)[:400]))


def job_state(name):
    rows = db.query("SELECT * FROM cass_jobs WHERE name = ?", (name,))
    return rows[0] if rows else None


def jobs():
    return db.query("SELECT * FROM cass_jobs ORDER BY name")


# Small helper used by sims and updates -------------------------------
def to_json(value):
    return json.dumps(value)


def from_json(text, default=None):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default
