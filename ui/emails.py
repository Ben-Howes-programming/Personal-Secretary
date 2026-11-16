"""
emails.py
=========
Purpose : Draws one email as a card with its summary, reply draft and actions.
          Shared by the Inbox and Tutoring pages so they behave the same.
Location: ui/emails.py
"""

import streamlit as st

import config
from ai import claude
from database import database as db
from services import calendar as cal
from services import gmail, inbox
from ui import state
from ui import theme as ui

PRIORITY_TONE = {"High": "bad", "Medium": "warn", "Low": "neutral"}


def sender_name(sender):
    if not sender:
        return "Unknown sender"
    return sender.split("<")[0].strip().strip('"') or sender


def free_slots_for(email):
    """Free lesson slots inside the window an email asked about, from the live calendar."""
    window = cal.requested_window(email["analysis"])
    if not window or not state.any_calendar():
        return None
    events, _errors = state.events_between(*window)
    return cal.free_slots_from_events(events, window[0], window[1], config.TUTORING_LESSON_MINUTES)


def render(email, prefix="mail"):
    """One email card. `prefix` keeps widget keys unique when a page shows the same email twice."""
    analysis = email["analysis"]
    key = f"{prefix}_{email['id']}"
    done = email.get("status") == "completed"

    with st.container(border=True):
        badges = ui.badge(analysis.get("priority") or "Unknown", PRIORITY_TONE.get(analysis.get("priority"), "neutral"))
        badges += ui.badge(analysis.get("category") or "Other")
        if analysis.get("reply_needed"):
            badges += ui.badge("Reply needed", "accent")
        if email.get("provider") and email["provider"] != "gmail":
            badges += ui.badge(email["provider"].title(), "info")
        if email.get("analysed_by") == "pending":
            badges += ui.badge("Waiting for analysis", "info")
        st.markdown(f"{badges}<br><strong>{ui.esc(email.get('subject') or 'No subject')}</strong>"
                    f"<div class='ps-muted'>{ui.esc(sender_name(email.get('sender')))}, {ui.esc(email.get('date') or '')}</div>",
                    unsafe_allow_html=True)
        st.write(analysis.get("summary") or "No summary.")

        slots = None
        if analysis.get("availability_request"):
            slots = free_slots_for(email)
            asked = f"{analysis.get('requested_day') or 'a day'} {analysis.get('requested_start') or ''} to {analysis.get('requested_end') or ''}"
            if slots:
                times = ", ".join(f"{a.strftime('%H:%M')} to {b.strftime('%H:%M')}" for a, b in slots[:6])
                ui.note("good", f"They asked about {asked}. You are free: {times}.")
            elif slots is not None:
                ui.note("warn", f"They asked about {asked}. Your calendar has no free lesson slot then.")
            else:
                ui.note("info", f"They asked about {asked}. Connect a calendar to check it automatically.")

        with st.expander("Read the email"):
            st.text(email.get("body") or "[No body]")

        # Reply draft ------------------------------------------------
        draft = email.get("draft_reply")
        if draft:
            edited = st.text_area("Reply draft", value=draft, height=180, key=f"{key}_draft")
            save, to_gmail, discard = st.columns(3)
            if save.button("Save draft", key=f"{key}_save"):
                db.update_draft_reply(email["id"], edited)
                st.toast("Draft saved")
            if config.ENABLE_GMAIL_DRAFTS and email.get("provider", "gmail") == "gmail":
                if to_gmail.button("Put in Gmail Drafts", key=f"{key}_gmail"):
                    try:
                        gmail.create_draft(state.gmail_service(), email, edited)
                        st.toast("Draft is in Gmail. Nothing was sent.")
                    except Exception as error:
                        st.error(f"Gmail refused the draft: {error}")
            if discard.button("Discard draft", key=f"{key}_discard"):
                db.clear_draft_reply(email["id"])
                st.rerun()

        # Actions ----------------------------------------------------
        first, second, third = st.columns(3)
        if not draft and first.button("Draft a reply", key=f"{key}_write", type="primary" if analysis.get("reply_needed") else "secondary"):
            try:
                with st.spinner("Drafting"):
                    db.update_draft_reply(email["id"], claude.draft_reply(email, slots))
                st.rerun()
            except claude.AIError as error:
                st.error(str(error))
        if second.button("Reopen" if done else "Mark done", key=f"{key}_done"):
            db.update_email_status(email["id"], "open" if done else "completed")
            st.rerun()
        if third.button("Re-analyse", key=f"{key}_again", help="Send this email to Claude again"):
            try:
                with st.spinner("Analysing"):
                    inbox.reanalyse(email)
                st.rerun()
            except claude.AIError as error:
                st.error(str(error))
