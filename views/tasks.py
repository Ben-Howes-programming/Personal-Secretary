"""
tasks.py
========
Purpose : A plain to-do list with due dates, grouped by urgency.
Location: views/tasks.py
"""

import streamlit as st

from database import tasks
from ui import state
from ui import theme as ui

AREAS = ["University", "Placements", "Money", "Health", "Tutoring", "Home", "General"]
today = state.now().date()

ui.header("Tasks", "Things that are not in your inbox or your calendar.")

with st.form("new_task", clear_on_submit=True):
    title_col, area_col, priority_col, due_col, add_col = st.columns([3, 1.2, 1, 1.2, 0.9], vertical_alignment="bottom")
    title = title_col.text_input("Task", placeholder="What needs doing?")
    area = area_col.selectbox("Area", AREAS, index=len(AREAS) - 1)
    priority = priority_col.selectbox("Priority", ["High", "Medium", "Low"], index=1)
    due = due_col.date_input("Due", value=None)
    if add_col.form_submit_button("Add", type="primary") and title.strip():
        tasks.add_task(title.strip(), area, priority, due.isoformat() if due else None)
        st.rerun()

groups = tasks.group_tasks(tasks.list_tasks(), today)
ui.kpis([("overdue", len(groups["Overdue"]), "", "bad"), ("due today", len(groups["Today"])),
         ("upcoming", len(groups["Upcoming"])), ("no date", len(groups["No date"]))])

if not any(groups.values()):
    ui.empty("No open tasks.", "Add one above.")

for name, tone in (("Overdue", "bad"), ("Today", "warn"), ("Upcoming", None), ("No date", None)):
    if not groups[name]:
        continue
    ui.section(name)
    for task in groups[name]:
        text_col, done_col, delete_col = st.columns([6, 1, 1], vertical_alignment="center")
        with text_col:
            badges = ui.badge(task["priority"], {"High": "bad", "Medium": "warn"}.get(task["priority"], "neutral")) + ui.badge(task["area"])
            ui.rows([ui.row(task["title"], "", ui.days_until(task["due"], today) if task["due"] else "", tone=tone, badges=badges)])
        if done_col.button("Done", key=f"done_{task['id']}"):
            tasks.complete_task(task["id"])
            st.rerun()
        if delete_col.button("Remove", key=f"remove_{task['id']}"):
            tasks.delete_task(task["id"])
            st.rerun()

finished = [task for task in tasks.list_tasks(include_done=True) if task["done"]]
if finished:
    with st.expander(f"Completed ({len(finished)})"):
        for task in finished[-30:]:
            text_col, undo_col = st.columns([7, 1])
            text_col.markdown(f"~~{task['title']}~~")
            if undo_col.button("Undo", key=f"undo_{task['id']}"):
                tasks.complete_task(task["id"], done=False)
                st.rerun()
