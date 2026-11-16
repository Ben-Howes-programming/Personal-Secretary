"""
university.py
=============
Purpose : Modules, assessments and marks, study sessions, and the lecture review queue.
Location: database/university.py
Used by : views/university.py, views/home.py, ai/context.py
"""

from datetime import date, timedelta

from database.database import execute, query

REVIEW_GAPS = [1, 3, 7, 14, 30]   # days between reviews: short gaps first, then longer


# Modules -----------------------------------------------------------
def list_modules():
    return query("SELECT * FROM modules ORDER BY semester, name")


def add_module(name, code="", credits=None, semester=""):
    return execute("INSERT INTO modules (code, name, credits, semester) VALUES (?, ?, ?, ?)", (code, name, credits, semester))


def update_module(module_id, code, credits):
    execute("UPDATE modules SET code = ?, credits = ? WHERE id = ?", (code, credits, module_id))


def delete_module(module_id):
    for table in ("assessments", "study_sessions", "lectures"):
        execute(f"DELETE FROM {table} WHERE module_id = ?", (module_id,))
    execute("DELETE FROM modules WHERE id = ?", (module_id,))


# Assessments -------------------------------------------------------
def list_assessments(only_open=False):
    where = "WHERE s.status != 'done'" if only_open else ""
    return query(
        f"SELECT s.*, m.name AS module FROM assessments s LEFT JOIN modules m ON m.id = s.module_id {where} "
        "ORDER BY CASE WHEN s.due IS NULL OR s.due = '' THEN 1 ELSE 0 END, s.due")


def add_assessment(module_id, title, due=None, weight=None):
    return execute("INSERT INTO assessments (module_id, title, due, weight) VALUES (?, ?, ?, ?)", (module_id, title, due, weight))


def set_mark(assessment_id, mark):
    execute("UPDATE assessments SET mark = ?, status = 'done' WHERE id = ?", (mark, assessment_id))


def set_assessment_status(assessment_id, status):
    execute("UPDATE assessments SET status = ? WHERE id = ?", (status, assessment_id))


def delete_assessment(assessment_id):
    execute("DELETE FROM assessments WHERE id = ?", (assessment_id,))


def module_standing(assessments, target=75.0):
    """Where a module stands and what is still needed.

    `assessments` are rows for one module with `weight` (percent of the module) and `mark`.
    needed = (target * total_weight - sum(weight * mark)) / remaining_weight
    """
    weighted = [a for a in assessments if a.get("weight")]
    total = sum(a["weight"] for a in weighted)
    done = [a for a in weighted if a.get("mark") is not None]
    done_weight = sum(a["weight"] for a in done)
    earned = sum(a["weight"] * a["mark"] for a in done)
    remaining = total - done_weight
    needed = None
    if remaining > 0:
        needed = (target * total - earned) / remaining
    return {
        "average": (earned / done_weight) if done_weight else None,   # average of marked work so far
        "done_weight": done_weight, "total_weight": total,
        "needed": needed,   # average needed on what is left to finish on target
        "secured": (earned / total) if total else None,               # marks already banked, out of 100
    }


# Study sessions ----------------------------------------------------
def log_study(module_id, minutes, note="", on=None):
    execute("INSERT INTO study_sessions (date, module_id, minutes, note) VALUES (?, ?, ?, ?)",
            (on or date.today().isoformat(), module_id, minutes, note))


def study_minutes(days=28):
    since = (date.today() - timedelta(days=days)).isoformat()
    return query(
        "SELECT s.date, s.minutes, COALESCE(m.name, 'General') AS module FROM study_sessions s "
        "LEFT JOIN modules m ON m.id = s.module_id WHERE s.date >= ? ORDER BY s.date", (since,))


# Lectures ----------------------------------------------------------
def log_lecture(module_id, topic, understanding, on=None):
    """Poorly understood lectures come back tomorrow, well understood ones in three days."""
    on = on or date.today().isoformat()
    gap = 1 if understanding <= 3 else 3
    next_review = (date.fromisoformat(on) + timedelta(days=gap)).isoformat()
    execute("INSERT INTO lectures (module_id, date, topic, understanding, next_review) VALUES (?, ?, ?, ?, ?)",
            (module_id, on, topic, understanding, next_review))


def reviews_due(today=None):
    today = (today or date.today()).isoformat()
    return query(
        "SELECT l.*, m.name AS module FROM lectures l LEFT JOIN modules m ON m.id = l.module_id "
        "WHERE l.next_review IS NOT NULL AND l.next_review <= ? ORDER BY l.next_review", (today,))


def next_review_date(reviews_done, understanding, today=None):
    """Spaced repetition: each successful review pushes the next one further out."""
    today = today or date.today()
    step = reviews_done if understanding >= 4 else 0   # still shaky: start the ladder again
    if step >= len(REVIEW_GAPS):
        return None                                    # reviewed enough, leave the queue
    return (today + timedelta(days=REVIEW_GAPS[step])).isoformat()


def complete_review(lecture_id, understanding):
    row = query("SELECT reviews_done FROM lectures WHERE id = ?", (lecture_id,))[0]
    done = row["reviews_done"] + 1
    execute("UPDATE lectures SET understanding = ?, reviews_done = ?, next_review = ? WHERE id = ?",
            (understanding, done, next_review_date(done, understanding), lecture_id))


def recent_lectures(limit=15):
    return query("SELECT l.*, m.name AS module FROM lectures l LEFT JOIN modules m ON m.id = l.module_id ORDER BY l.date DESC, l.id DESC LIMIT ?", (limit,))
