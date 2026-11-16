"""
database.py
===========
Purpose : The single SQLite layer. Creates every table, upgrades older databases
          in place, and provides the email cache plus small shared helpers
          (key-value cache, AI response cache, AI usage log, settings, chat history).
Location: database/database.py
Used by : everything that stores or reads data.
Note    : Your existing secretary.db is kept. Missing tables and columns are added,
          nothing is deleted.
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from email.utils import parsedate_to_datetime

import config

ANALYSIS_VERSION = 4   # bump when the email analysis prompt changes meaningfully

# ------------------------------------------------------------------
# Schema. CREATE IF NOT EXISTS makes this safe to run on every start.
# ------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY, sender TEXT, subject TEXT, date TEXT, body TEXT,
    category TEXT, priority TEXT, action_required INTEGER, reply_needed INTEGER,
    availability_request INTEGER, requested_day TEXT, requested_start TEXT,
    requested_end TEXT, summary TEXT, draft_reply TEXT,
    status TEXT DEFAULT 'open', analysis_version INTEGER DEFAULT 3
);
CREATE TABLE IF NOT EXISTS kv_cache (key TEXT PRIMARY KEY, value TEXT, expires_at REAL);
CREATE TABLE IF NOT EXISTS ai_cache (key TEXT PRIMARY KEY, response TEXT, created_at REAL, expires_at REAL);
CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, purpose TEXT, backend TEXT, model TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cached INTEGER
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, role TEXT, content TEXT, ts REAL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, kind TEXT, provider TEXT,
    interest_rate REAL, is_liability INTEGER DEFAULT 0, notes TEXT, archived INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, date TEXT, balance REAL,
    UNIQUE(account_id, date)
);
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, symbol TEXT, units REAL, avg_cost REAL
);
CREATE TABLE IF NOT EXISTS contributions (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, date TEXT, amount REAL);
CREATE TABLE IF NOT EXISTS cashflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, kind TEXT, category TEXT, amount REAL, note TEXT
);
CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, kind TEXT, amount REAL, frequency TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY, name TEXT, kind TEXT, note TEXT, keywords TEXT, currency TEXT, added REAL
);
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, symbol TEXT, units REAL, price_gbp REAL,
    thesis TEXT, closed_date TEXT, close_price_gbp REAL
);

CREATE TABLE IF NOT EXISTS sleep (date TEXT PRIMARY KEY, bed_time TEXT, wake_time TEXT, hours REAL, quality INTEGER, source TEXT);
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, kind TEXT, title TEXT, duration_min REAL,
    distance_km REAL, rpe INTEGER, notes TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS lifts (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, exercise TEXT, weight_kg REAL, reps INTEGER, sets INTEGER);
CREATE TABLE IF NOT EXISTS body (date TEXT PRIMARY KEY, weight_kg REAL, protein_g REAL, energy INTEGER, resting_hr REAL, steps INTEGER);

CREATE TABLE IF NOT EXISTS modules (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, credits REAL, semester TEXT);
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, module_id INTEGER, title TEXT, due TEXT, weight REAL, mark REAL, status TEXT DEFAULT 'todo'
);
CREATE TABLE IF NOT EXISTS study_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, module_id INTEGER, minutes REAL, note TEXT);
CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT, module_id INTEGER, date TEXT, topic TEXT,
    understanding INTEGER, next_review TEXT, reviews_done INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, area TEXT, priority TEXT, due TEXT,
    done INTEGER DEFAULT 0, created REAL, done_at REAL
);
CREATE TABLE IF NOT EXISTS placements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, organisation TEXT, role TEXT, location TEXT, deadline TEXT,
    status TEXT, link TEXT, notes TEXT, updated REAL
);
"""

# Columns added to the emails table since the first version of the app
EMAIL_EXTRA_COLUMNS = {
    "availability_request": "INTEGER", "requested_day": "TEXT", "requested_start": "TEXT",
    "requested_end": "TEXT", "status": "TEXT DEFAULT 'open'", "analysis_version": "INTEGER DEFAULT 3",
    "provider": "TEXT DEFAULT 'gmail'", "account": "TEXT", "thread_id": "TEXT",
    "received_ts": "REAL", "analysed_by": "TEXT",
}


# ------------------------------------------------------------------
# Connection helpers
# ------------------------------------------------------------------
def get_connection():
    connection = sqlite3.connect(str(config.DB_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def connect():
    """Open, commit and close in one go:  with connect() as c: c.execute(...)"""
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def query(sql, params=()):
    """Run a SELECT and return a list of plain dictionaries."""
    with connect() as c:
        return [dict(row) for row in c.execute(sql, params).fetchall()]


def execute(sql, params=()):
    """Run an INSERT, UPDATE or DELETE. Returns the new row id for inserts."""
    with connect() as c:
        return c.execute(sql, params).lastrowid


def initialise_database():
    """Create anything missing, upgrade old tables, and add first-run defaults."""
    with connect() as c:
        c.executescript(SCHEMA)
        existing = {row["name"] for row in c.execute("PRAGMA table_info(emails)").fetchall()}
        for column, column_type in EMAIL_EXTRA_COLUMNS.items():
            if column not in existing:
                c.execute(f"ALTER TABLE emails ADD COLUMN {column} {column_type}")
        # Older rows have a date string but no sortable timestamp: fill it in once
        for row in c.execute("SELECT id, date FROM emails WHERE received_ts IS NULL").fetchall():
            try:
                stamp = parsedate_to_datetime(row["date"]).timestamp()
            except (TypeError, ValueError, AttributeError):
                continue
            c.execute("UPDATE emails SET received_ts = ? WHERE id = ?", (stamp, row["id"]))
    _seed_defaults()


def _seed_defaults():
    """First run only: add your account names, watchlist and modules with no figures."""
    if get_setting("seeded_v1"):
        return
    with connect() as c:
        if not c.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
            c.executemany(
                "INSERT INTO accounts (name, kind, provider, is_liability, notes) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Stocks and Shares ISA", "investment", "Vanguard", 0, "Vanguard All-World"),
                    ("Lifetime ISA", "lisa", "JP Morgan", 0, ""),
                    ("Chase saver 1", "savings", "Chase", 0, ""),
                    ("Chase saver 2", "savings", "Chase", 0, ""),
                    ("Chase current account", "current", "Chase", 0, ""),
                    ("Student overdraft", "overdraft", "Nationwide", 1, "Interest-free while a student"),
                ],
            )
        if not c.execute("SELECT 1 FROM recurring LIMIT 1").fetchone():
            c.executemany(
                "INSERT INTO recurring (name, kind, amount, frequency) VALUES (?, ?, ?, ?)",
                [("Rent", "expense", config.RENT_PER_MONTH, "monthly"),
                 ("Bills", "expense", 0.0, "monthly"),
                 ("Maintenance loan", "income", 0.0, "monthly"),
                 ("Tutoring", "income", 0.0, "monthly")],
            )
        if not c.execute("SELECT 1 FROM watchlist LIMIT 1").fetchone():
            now = time.time()
            for symbol, name, kind, keywords in config.DEFAULT_WATCHLIST:
                c.execute("INSERT INTO watchlist (symbol, name, kind, keywords, added) VALUES (?, ?, ?, ?, ?)",
                          (symbol, name, kind, keywords, now))
            for symbol, name, note in config.RESEARCH_LIST:
                c.execute("INSERT INTO watchlist (symbol, name, kind, note, keywords, added) VALUES (?, ?, 'research', ?, '', ?)",
                          (symbol, name, note, now))
        if not c.execute("SELECT 1 FROM modules LIMIT 1").fetchone():
            c.executemany(
                "INSERT INTO modules (code, name, credits, semester) VALUES (?, ?, ?, ?)",
                [("", "Vector calculus", None, "1"), ("", "Statistical mechanics", None, "1"),
                 ("", "Atomic physics", None, "1"), ("", "Particle physics", None, "1")],
            )
    set_setting("seeded_v1", "1")


# ------------------------------------------------------------------
# Settings (small preferences you change inside the app)
# ------------------------------------------------------------------
def get_setting(key, default=None):
    try:
        rows = query("SELECT value FROM settings WHERE key = ?", (key,))
    except sqlite3.OperationalError:
        return default
    return json.loads(rows[0]["value"]) if rows else default


def set_setting(key, value):
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))


# ------------------------------------------------------------------
# Key-value cache with expiry (market prices, news feeds)
# ------------------------------------------------------------------
def cache_get(key, allow_stale=False):
    rows = query("SELECT value, expires_at FROM kv_cache WHERE key = ?", (key,))
    if not rows:
        return None
    if rows[0]["expires_at"] < time.time() and not allow_stale:
        return None
    return json.loads(rows[0]["value"])


def cache_set(key, value, ttl_seconds):
    execute("INSERT OR REPLACE INTO kv_cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + ttl_seconds))


def cache_clear(prefix=""):
    execute("DELETE FROM kv_cache WHERE key LIKE ?", (prefix + "%",))


# ------------------------------------------------------------------
# AI response cache and usage log (this is what keeps token use down)
# ------------------------------------------------------------------
def ai_cache_get(key):
    rows = query("SELECT response FROM ai_cache WHERE key = ? AND expires_at > ?", (key, time.time()))
    return rows[0]["response"] if rows else None


def ai_cache_set(key, response, ttl_seconds):
    now = time.time()
    execute("INSERT OR REPLACE INTO ai_cache (key, response, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (key, response, now, now + ttl_seconds))


def ai_cache_clear():
    execute("DELETE FROM ai_cache")


def log_ai_usage(purpose, backend, model, input_tokens=0, output_tokens=0, cache_read_tokens=0, cached=False):
    execute(
        "INSERT INTO ai_usage (ts, purpose, backend, model, input_tokens, output_tokens, cache_read_tokens, cached) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (time.time(), purpose, backend, model, int(input_tokens or 0), int(output_tokens or 0),
         int(cache_read_tokens or 0), int(bool(cached))),
    )


def ai_usage_summary(since_ts):
    """Totals since a timestamp: calls, tokens, and how many calls the cache answered for free."""
    row = query(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens), 0) AS input_tokens, "
        "COALESCE(SUM(output_tokens), 0) AS output_tokens, COALESCE(SUM(cached), 0) AS cache_hits "
        "FROM ai_usage WHERE ts >= ?", (since_ts,))[0]
    row["by_purpose"] = query(
        "SELECT purpose, model, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, "
        "SUM(output_tokens) AS output_tokens, SUM(cached) AS cache_hits "
        "FROM ai_usage WHERE ts >= ? GROUP BY purpose, model ORDER BY input_tokens DESC", (since_ts,))
    return row


# ------------------------------------------------------------------
# Chat history
# ------------------------------------------------------------------
def create_conversation(title="New chat"):
    now = time.time()
    return execute("INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)", (title, now, now))


def list_conversations(limit=15):
    return query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,))


def add_message(conversation_id, role, content):
    now = time.time()
    execute("INSERT INTO messages (conversation_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now))
    execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))


def get_messages(conversation_id):
    return query("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,))


def rename_conversation(conversation_id, title):
    execute("UPDATE conversations SET title = ? WHERE id = ?", (title[:60], conversation_id))


def delete_conversation(conversation_id):
    execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


# ------------------------------------------------------------------
# Emails
# ------------------------------------------------------------------
def _row_to_email(row):
    return {
        "id": row["id"], "sender": row["sender"], "subject": row["subject"],
        "date": row["date"], "body": row["body"],
        "analysis": {
            "category": row["category"], "priority": row["priority"],
            "action_required": bool(row["action_required"]),
            "reply_needed": bool(row["reply_needed"]),
            "availability_request": bool(row["availability_request"]),
            "requested_day": row["requested_day"], "requested_start": row["requested_start"],
            "requested_end": row["requested_end"], "summary": row["summary"],
        },
        "draft_reply": row["draft_reply"], "status": row["status"] or "open",
        "analysis_version": row["analysis_version"] or 1,
        "provider": row.get("provider") or "gmail", "account": row.get("account"),
        "thread_id": row.get("thread_id"), "received_ts": row.get("received_ts"),
        "analysed_by": row.get("analysed_by"),
    }


def save_email(email):
    """Insert or update one email together with its analysis."""
    analysis = email.get("analysis") or {}
    execute(
        """
        INSERT OR REPLACE INTO emails (
            id, sender, subject, date, body, category, priority, action_required, reply_needed,
            availability_request, requested_day, requested_start, requested_end, summary,
            draft_reply, status, analysis_version, provider, account, thread_id, received_ts, analysed_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email["id"], email.get("sender"), email.get("subject"), email.get("date"), email.get("body"),
            analysis.get("category"), analysis.get("priority"),
            int(bool(analysis.get("action_required"))), int(bool(analysis.get("reply_needed"))),
            int(bool(analysis.get("availability_request"))),
            analysis.get("requested_day"), analysis.get("requested_start"), analysis.get("requested_end"),
            analysis.get("summary"), email.get("draft_reply"), email.get("status", "open"),
            email.get("analysis_version", ANALYSIS_VERSION), email.get("provider", "gmail"),
            email.get("account"), email.get("thread_id"), email.get("received_ts"), email.get("analysed_by"),
        ),
    )


def email_is_cached(message_id):
    return bool(query("SELECT 1 FROM emails WHERE id = ?", (message_id,)))


def get_cached_email(message_id):
    rows = query("SELECT * FROM emails WHERE id = ?", (message_id,))
    return _row_to_email(rows[0]) if rows else None


def list_emails(limit=60, include_done=True):
    """Newest first. Older rows without a timestamp fall to the bottom."""
    where = "" if include_done else "WHERE status != 'completed'"
    rows = query(f"SELECT * FROM emails {where} ORDER BY COALESCE(received_ts, 0) DESC, rowid DESC LIMIT ?", (limit,))
    return [_row_to_email(row) for row in rows]


def pending_emails(limit):
    """Emails stored but not yet analysed by Claude (the per-sync cap was reached)."""
    rows = query("SELECT * FROM emails WHERE analysed_by = 'pending' ORDER BY COALESCE(received_ts, 0) DESC LIMIT ?", (limit,))
    return [_row_to_email(row) for row in rows]


def update_draft_reply(message_id, draft):
    execute("UPDATE emails SET draft_reply = ? WHERE id = ?", (draft, message_id))


def clear_draft_reply(message_id):
    execute("UPDATE emails SET draft_reply = NULL WHERE id = ?", (message_id,))


def update_email_status(message_id, status):
    if status not in ("open", "completed"):
        raise ValueError("Status must be 'open' or 'completed'.")
    execute("UPDATE emails SET status = ? WHERE id = ?", (status, message_id))
