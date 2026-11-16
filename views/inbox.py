"""
inbox.py
========
Purpose : Every mail account in one triaged list, with reply drafting.
Location: views/inbox.py
Tokens  : Mail is checked at most every 30 minutes (or when you press the button).
          Bulk mail is filed by rules. Each email is analysed once and then cached.
"""

import streamlit as st

from database import database as db
from ui import emails as email_ui
from ui import state
from ui import theme as ui

ui.header("Inbox", "Sorted by what needs you, not by when it arrived.")

if not state.any_mail():
    ui.note("info", "No mail account is connected yet. Open Settings and press Connect Google.")
    st.stop()

check, caption = st.columns([1, 3])
forced = check.button("Check mail now", type="primary")
result = state.sync_inbox(force=forced)
if result:
    for problem in result["errors"]:
        st.warning(problem)
    if result["new"]:
        st.toast(f"{result['new']} new: {result['by_rules']} filed by rules, {result['by_claude']} read by Claude")
caption.markdown(f"<div class='ps-muted' style='padding-top:.6rem'>{ui.esc(state.sync_caption())}</div>", unsafe_allow_html=True)

emails = db.list_emails(120)
open_emails = [e for e in emails if e["status"] != "completed"]
views = {
    "Needs action": [e for e in open_emails if e["analysis"]["action_required"]],
    "Replies": [e for e in open_emails if e["analysis"]["reply_needed"]],
    "High priority": [e for e in open_emails if e["analysis"]["priority"] == "High"],
    "Everything": open_emails,
    "Done": [e for e in emails if e["status"] == "completed"],
}

ui.kpis([(name.lower(), len(items)) for name, items in views.items() if name != "Done"])

pick, find = st.columns([2, 1])
chosen = pick.segmented_control("Show", list(views), default="Needs action", key="inbox_view") or "Needs action"
search = find.text_input("Search", placeholder="Sender or subject", label_visibility="collapsed")

shown = views[chosen]
categories = sorted({e["analysis"]["category"] for e in shown if e["analysis"]["category"]})
if len(categories) > 1:
    wanted = st.pills("Category", categories, selection_mode="multi", key="inbox_categories")
    if wanted:
        shown = [e for e in shown if e["analysis"]["category"] in wanted]
if search:
    needle = search.lower()
    shown = [e for e in shown if needle in (e.get("subject") or "").lower() or needle in (e.get("sender") or "").lower()]

if not shown:
    ui.empty("Nothing here.", "Try Everything, or check mail again.")
for email in shown[:40]:
    email_ui.render(email, prefix="inbox")
if len(shown) > 40:
    ui.muted(f"Showing the newest 40 of {len(shown)}. Use search to narrow it down.")
