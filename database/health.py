"""
health.py
=========
Purpose : Storage for sleep, workouts, lifts and daily body numbers.
Location: database/health.py
Used by : views/health.py, ai/context.py, services/apple.py (Apple Health import)
Note    : The analysis itself lives in services/training.py. This file only reads and writes.
"""

from datetime import date, datetime, timedelta

from database.database import execute, query


def _since(days):
    return (date.today() - timedelta(days=days)).isoformat()


def hours_between(bed_time, wake_time):
    """'23:40' and '07:10' give 7.5. Works across midnight."""
    try:
        bed = datetime.strptime(bed_time, "%H:%M")
        wake = datetime.strptime(wake_time, "%H:%M")
    except (TypeError, ValueError):
        return None
    minutes = (wake - bed).total_seconds() / 60
    if minutes <= 0:
        minutes += 24 * 60
    return round(minutes / 60, 2)


# Sleep -------------------------------------------------------------
def log_sleep(night, bed_time, wake_time, quality=None, hours=None, source="manual"):
    """`night` is the date you woke up on."""
    hours = hours if hours is not None else hours_between(bed_time, wake_time)
    execute("INSERT OR REPLACE INTO sleep (date, bed_time, wake_time, hours, quality, source) VALUES (?, ?, ?, ?, ?, ?)",
            (night, bed_time, wake_time, hours, quality, source))


def get_sleep(days=30):
    return query("SELECT * FROM sleep WHERE date >= ? ORDER BY date", (_since(days),))


# Workouts ----------------------------------------------------------
def log_workout(on, kind, title="", duration_min=None, distance_km=None, rpe=None, notes="", source="manual"):
    return execute(
        "INSERT INTO workouts (date, kind, title, duration_min, distance_km, rpe, notes, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (on, kind, title, duration_min, distance_km, rpe, notes, source))


def get_workouts(days=60, kind=None):
    if kind:
        return query("SELECT * FROM workouts WHERE date >= ? AND kind = ? ORDER BY date", (_since(days), kind))
    return query("SELECT * FROM workouts WHERE date >= ? ORDER BY date", (_since(days),))


def workout_exists(on, kind, duration_min):
    """Used by the Apple Health import so the same session is never added twice."""
    return bool(query("SELECT 1 FROM workouts WHERE date = ? AND kind = ? AND ABS(COALESCE(duration_min, 0) - ?) < 1",
                      (on, kind, duration_min or 0)))


def delete_workout(workout_id):
    execute("DELETE FROM workouts WHERE id = ?", (workout_id,))


# Lifts -------------------------------------------------------------
def log_lift(on, exercise, weight_kg, reps, sets):
    execute("INSERT INTO lifts (date, exercise, weight_kg, reps, sets) VALUES (?, ?, ?, ?, ?)",
            (on, exercise.strip().title(), weight_kg, reps, sets))


def get_lifts(days=180, exercise=None):
    if exercise:
        return query("SELECT * FROM lifts WHERE date >= ? AND exercise = ? ORDER BY date, id", (_since(days), exercise))
    return query("SELECT * FROM lifts WHERE date >= ? ORDER BY date, id", (_since(days),))


def list_exercises():
    return [row["exercise"] for row in query("SELECT exercise, MAX(date) AS last FROM lifts GROUP BY exercise ORDER BY last DESC")]


# Body --------------------------------------------------------------
def log_body(on, weight_kg=None, protein_g=None, energy=None, resting_hr=None, steps=None):
    """Only the values you pass are changed, so you can log weight and protein separately."""
    existing = query("SELECT * FROM body WHERE date = ?", (on,))
    current = existing[0] if existing else {}
    def pick(new, key):
        return new if new is not None else current.get(key)
    execute("INSERT OR REPLACE INTO body (date, weight_kg, protein_g, energy, resting_hr, steps) VALUES (?, ?, ?, ?, ?, ?)",
            (on, pick(weight_kg, "weight_kg"), pick(protein_g, "protein_g"), pick(energy, "energy"),
             pick(resting_hr, "resting_hr"), pick(steps, "steps")))


def get_body(days=90):
    return query("SELECT * FROM body WHERE date >= ? ORDER BY date", (_since(days),))


def latest_weight():
    rows = query("SELECT weight_kg FROM body WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1")
    return rows[0]["weight_kg"] if rows else None
