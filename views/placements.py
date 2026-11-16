"""
placements.py
=============
Purpose : Track research and industry placement applications from first look to outcome.
Location: views/placements.py
Note    : Starts empty. Add each opportunity with its real deadline from the
          organisation's own page.
"""

from datetime import date

import streamlit as st

from database import tasks
from ui import state
from ui import theme as ui

today = state.now().date()
STATUS_TONE = {"Researching": "neutral", "Drafting": "warn", "Applied": "info", "Interview": "accent",
               "Offer": "good", "Rejected": "bad", "Closed": "neutral"}

ui.header("Placements", "Research and industry applications, with nothing falling through.")

placements = tasks.list_placements()
live = [p for p in placements if p["status"] not in ("Rejected", "Closed", "Offer")]
upcoming = [p for p in live if p.get("deadline") and p["deadline"] >= today.isoformat() and p["status"] in ("Researching", "Drafting")]

ui.kpis([
    ("in progress", len(live)),
    ("applied", len([p for p in placements if p["status"] == "Applied"])),
    ("interviews", len([p for p in placements if p["status"] == "Interview"])),
    ("next deadline", ui.days_until(upcoming[0]["deadline"], today) if upcoming else "none set",
     upcoming[0]["organisation"] if upcoming else ""),
])

with st.form("new_placement", clear_on_submit=True):
    a, b, c, d = st.columns([2, 2, 1.5, 1.3])
    organisation = a.text_input("Organisation", placeholder="ESA, CERN, an observatory")
    role = b.text_input("Role or scheme")
    location = c.text_input("Location")
    deadline = d.date_input("Deadline", value=None)
    link = st.text_input("Link to the advert")
    if ui.submit("Add opportunity", type="primary") and organisation.strip():
        tasks.add_placement(organisation.strip(), role.strip(), location.strip(),
                            deadline.isoformat() if deadline else None, link=link.strip())
        st.rerun()

if not placements:
    ui.empty("No opportunities tracked yet.",
             "Add the ones you are considering. Entering the deadline now is the part that prevents missed applications.")

for placement in placements:
    gap = (date.fromisoformat(placement["deadline"]) - today).days if placement.get("deadline") else None
    urgent = gap is not None and 0 <= gap <= 14 and placement["status"] in ("Researching", "Drafting")
    when = f"deadline {placement['deadline']}, {ui.days_until(placement['deadline'], today)}" if placement.get("deadline") else "no deadline set"
    title = f"{placement['organisation']}: {placement['role'] or 'role to confirm'} ({placement['status']}), {when}"
    with st.expander(title, expanded=urgent):
        st.markdown(ui.badge(placement["status"], STATUS_TONE.get(placement["status"], "neutral"))
                    + (ui.badge("Deadline close", "bad") if urgent else "")
                    + f"<span class='ps-muted'>{ui.esc(placement['location'] or '')}</span>", unsafe_allow_html=True)
        if placement.get("link"):
            st.markdown(f"[Open the advert]({placement['link']})")
        a, b = st.columns(2)
        status = a.selectbox("Status", tasks.PLACEMENT_STATUSES, index=tasks.PLACEMENT_STATUSES.index(placement["status"])
                             if placement["status"] in tasks.PLACEMENT_STATUSES else 0, key=f"status_{placement['id']}")
        new_deadline = b.date_input("Deadline", value=date.fromisoformat(placement["deadline"]) if placement.get("deadline") else None,
                                    key=f"deadline_{placement['id']}")
        notes = st.text_area("Notes", value=placement["notes"] or "", key=f"notes_{placement['id']}",
                             placeholder="Requirements, contacts, what to put in the cover letter, interview questions")
        save_col, delete_col = st.columns(2)
        if save_col.button("Save changes", key=f"save_{placement['id']}", type="primary"):
            tasks.update_placement(placement["id"], status, notes, new_deadline.isoformat() if new_deadline else None)
            st.rerun()
        if delete_col.button("Remove", key=f"delete_{placement['id']}"):
            tasks.delete_placement(placement["id"])
            st.rerun()
