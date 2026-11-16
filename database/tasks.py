"""
tasks.py
========
Purpose : The to-do list and the placement application tracker.
Location: database/tasks.py
Used by : views/tasks.py, views/placements.py, views/home.py, ai/context.py
"""

import time
from datetime import date

from database.database import execute, query

PLACEMENT_STATUSES = ["Researching", "Drafting", "Applied", "Interview", "Offer", "Rejected", "Closed"]


# Tasks -------------------------------------------------------------
def add_task(title, area="General", priority="Medium", due=None):
    return execute("INSERT INTO tasks (title, area, priority, due, created) VALUES (?, ?, ?, ?, ?)",
                   (title, area, priority, due, time.time()))


def list_tasks(include_done=False):
    where = "" if include_done else "WHERE done = 0"
    return query(
        f"SELECT * FROM tasks {where} ORDER BY done, CASE WHEN due IS NULL OR due = '' THEN 1 ELSE 0 END, due, "
        "CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END")


def complete_task(task_id, done=True):
    execute("UPDATE tasks SET done = ?, done_at = ? WHERE id = ?", (int(done), time.time() if done else None, task_id))


def delete_task(task_id):
    execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def group_tasks(tasks, today=None):
    """Split open tasks into Overdue, Today, Upcoming and No date."""
    today = (today or date.today()).isoformat()
    groups = {"Overdue": [], "Today": [], "Upcoming": [], "No date": []}
    for task in tasks:
        due = task.get("due")
        if not due:
            groups["No date"].append(task)
        elif due < today:
            groups["Overdue"].append(task)
        elif due == today:
            groups["Today"].append(task)
        else:
            groups["Upcoming"].append(task)
    return groups


# Placements --------------------------------------------------------
def add_placement(organisation, role="", location="", deadline=None, status="Researching", link="", notes=""):
    return execute(
        "INSERT INTO placements (organisation, role, location, deadline, status, link, notes, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (organisation, role, location, deadline, status, link, notes, time.time()))


def list_placements():
    return query("SELECT * FROM placements ORDER BY CASE WHEN deadline IS NULL OR deadline = '' THEN 1 ELSE 0 END, deadline")


def update_placement(placement_id, status, notes, deadline):
    execute("UPDATE placements SET status = ?, notes = ?, deadline = ?, updated = ? WHERE id = ?",
            (status, notes, deadline, time.time(), placement_id))


def delete_placement(placement_id):
    execute("DELETE FROM placements WHERE id = ?", (placement_id,))
