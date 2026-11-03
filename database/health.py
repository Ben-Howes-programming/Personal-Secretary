"""
health.py
=========
Purpose : Store and summarise daily health data. Watch fields arrive from
          services/apple_health.py. Mood, energy, study time and protein can be typed in.
Location: database/health.py
Inputs  : dates as "YYYY-MM-DD", times as "HH:MM"
Outputs : dicts, plus a summary dict for the Health page
Design  : one row per day. A value of None leaves the saved value unchanged,
          so each source only overwrites the fields it actually provides.
"""

import sqlite3
from contextlib import contextmanager
from statistics import mean

import config

# Column name -> SQL type. This one dict drives the table, the migration and the
# list of fields save_daily_log accepts. Names go into SQL text, so they must
# only ever come from here.
COLUMNS = {
    "sleep_start": "TEXT",
    "sleep_end": "TEXT",
    "asleep_minutes": "INTEGER",
    "exercise_minutes": "INTEGER",
    "exercise_type": "TEXT",
    "resting_hr": "REAL",
    "hrv_ms": "REAL",
    "steps": "INTEGER",
    "active_kcal": "INTEGER",
    "protein_g": "INTEGER",
    "energy": "INTEGER",
    "mood": "INTEGER",
    "study_hours": "REAL",
}
FIELDS = tuple(COLUMNS)

# Allowed (min, max), to catch typos and bad imports
RANGES = {
    "asleep_minutes": (0, 960),
    "exercise_minutes": (0, 1440),
    "resting_hr": (20, 120),
    "hrv_ms": (1, 300),
    "steps": (0, 100000),
    "active_kcal": (0, 10000),
    "protein_g": (0, 500),
    "energy": (1, 5),
    "mood": (1, 5),
    "study_hours": (0, 16),
}


@contextmanager
def _connect(db_path):
    """Open the database, commit on success, roll back on error, always close."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_health_table(db_path=None):
    """Create daily_log if missing, and add any columns an older version lacks."""
    with _connect(db_path or config.DB_PATH) as conn:
        columns_sql = ", ".join(f"{n} {t}" for n, t in COLUMNS.items())
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS daily_log "
            f"(log_date TEXT PRIMARY KEY, {columns_sql})"
        )
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(daily_log)")}
        for name, kind in COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE daily_log ADD COLUMN {name} {kind}")


def save_daily_log(log_date, db_path=None, **fields):
    """Insert or update one day. Fields left out or None keep their saved value."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError(f"Unknown field(s): {sorted(unknown)}")

    values = {name: fields.get(name) for name in FIELDS}

    for name, (low, high) in RANGES.items():
        value = values[name]
        if value is not None and not (low <= value <= high):
            raise ValueError(f"{name} must be between {low} and {high}")

    columns = ", ".join(FIELDS)
    placeholders = ", ".join("?" for _ in FIELDS)
    # COALESCE(new, old) means: use the new value unless it is NULL
    updates = ", ".join(
        f"{c} = COALESCE(excluded.{c}, daily_log.{c})" for c in FIELDS
    )
    sql = (
        f"INSERT INTO daily_log (log_date, {columns}) "
        f"VALUES (?, {placeholders}) "
        f"ON CONFLICT(log_date) DO UPDATE SET {updates}"
    )
    with _connect(db_path or config.DB_PATH) as conn:
        conn.execute(sql, [log_date, *values.values()])


def get_logs(start_date, end_date, db_path=None):
    """All logged days between two ISO dates inclusive, oldest first."""
    with _connect(db_path or config.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT * FROM daily_log WHERE log_date BETWEEN ? AND ? "
            "ORDER BY log_date",
            (start_date, end_date),
        ).fetchall()

    logs = []
    for row in rows:
        log = dict(row)
        minutes = log["asleep_minutes"]
        log["sleep_hours"] = round(minutes / 60, 2) if minutes is not None else None
        logs.append(log)
    return logs


def _average(logs, key):
    """Mean of a field, skipping days where it was not logged."""
    values = [log[key] for log in logs if log.get(key) is not None]
    return round(mean(values), 1) if values else None


def weekly_summary(logs):
    """Averages and totals over whichever days you pass in."""
    return {
        "days_logged": len(logs),
        "avg_sleep_hours": _average(logs, "sleep_hours"),
        "avg_resting_hr": _average(logs, "resting_hr"),
        "avg_hrv_ms": _average(logs, "hrv_ms"),
        "avg_steps": _average(logs, "steps"),
        "avg_protein_g": _average(logs, "protein_g"),
        "avg_energy": _average(logs, "energy"),
        "avg_mood": _average(logs, "mood"),
        "total_study_hours": round(sum(log.get("study_hours") or 0 for log in logs), 1),
        "training_days": sum(1 for log in logs if (log.get("exercise_minutes") or 0) > 0),
    }