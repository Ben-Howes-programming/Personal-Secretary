"""
test_health.py
==============
Purpose : Check the save rules, the migration and the summary maths in database/health.py.
Run     : pytest -q   (from the project root, venv active)
Note    : tmp_path gives each test a throwaway database, so secretary.db is never touched.
"""

import sqlite3

import pytest

from database.health import (
    get_logs, init_health_table, save_daily_log, weekly_summary,
)


def make_db(tmp_path):
    db = tmp_path / "test.db"
    init_health_table(db_path=db)
    return db


def test_partial_saves_keep_existing_values(tmp_path):
    db = make_db(tmp_path)
    save_daily_log("2026-11-03", db_path=db, asleep_minutes=450, resting_hr=52)
    save_daily_log("2026-11-03", db_path=db, protein_g=140)   # later update
    log = get_logs("2026-11-03", "2026-11-03", db_path=db)[0]
    assert log["sleep_hours"] == 7.5
    assert log["resting_hr"] == 52
    assert log["protein_g"] == 140


def test_unknown_field_is_rejected(tmp_path):
    db = make_db(tmp_path)
    with pytest.raises(ValueError):
        save_daily_log("2026-11-03", db_path=db, calories=2500)


def test_out_of_range_value_is_rejected(tmp_path):
    db = make_db(tmp_path)
    with pytest.raises(ValueError):
        save_daily_log("2026-11-03", db_path=db, mood=9)


def test_old_table_gains_new_columns(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE daily_log (log_date TEXT PRIMARY KEY, mood INTEGER)")
    conn.commit()
    conn.close()

    init_health_table(db_path=db)
    save_daily_log("2026-11-03", db_path=db, steps=9000)
    assert get_logs("2026-11-03", "2026-11-03", db_path=db)[0]["steps"] == 9000


def test_weekly_summary_ignores_missing_values():
    logs = [
        {"sleep_hours": 8.0, "protein_g": 100, "steps": 9000, "exercise_minutes": 60},
        {"sleep_hours": 6.0, "mood": 2},
    ]
    summary = weekly_summary(logs)
    assert summary["avg_sleep_hours"] == 7.0
    assert summary["avg_protein_g"] == 100.0
    assert summary["avg_steps"] == 9000.0
    assert summary["avg_energy"] is None
    assert summary["training_days"] == 1