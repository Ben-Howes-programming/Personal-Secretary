"""
settings.py
===========
Purpose : Connections, Claude usage, your preferences, caches and backups.
Location: views/settings.py
"""

import time

import streamlit as st

import config
from ai import claude, voice
from database import database as db
from services import apple, google_auth, market, microsoft, news
from ui import state
from ui import theme as ui

ui.header("Settings", "Connections, usage and preferences.")

connections, usage, preferences, data = st.tabs(["Connections", "Claude usage", "Preferences", "Data"])

# ------------------------------------------------------------------
with connections:
    backend = claude.backend_status()
    ui.section("Claude")
    ui.rows([
        ui.row("Claude Pro plan, through Claude Code", "Uses the plan you already pay for. Needs Claude Code installed and signed in.",
               "found" if backend["claude_code"] else "not found", tone="good" if backend["claude_code"] else "neutral"),
        ui.row("API key", "Billed per token, separately from Pro. Streams replies word by word.",
               "set" if backend["api"] else "not set", tone="good" if backend["api"] else "neutral"),
    ])
    active = {"claude_code": "your Pro plan through Claude Code", "api": "the API key"}.get(backend["active"], "nothing yet")
    ui.muted(f"AI_BACKEND is \"{backend['setting']}\", so the app is using {active}. Change it in .env (auto, claude_code or api).")
    if backend["last_error"]:
        ui.note("bad", f"Last error: {backend['last_error']}")
    if st.button("Test Claude", help="Sends one very short message"):
        try:
            with st.spinner("Asking"):
                st.success(claude.complete("Reply with the single word: connected", tier="fast", max_tokens=10, purpose="test"))
        except claude.AIError as error:
            st.error(str(error))

    ui.section("Google (Gmail and Calendar)")
    if not google_auth.is_configured():
        ui.note("bad", "credentials.json is missing from the project folder. The setup guide explains how to download it from Google Cloud.")
    elif state.google_ready():
        ui.note("good", "Connected. Access is read-only" + (" plus Gmail drafts" if config.ENABLE_GMAIL_DRAFTS else "")
                + (" plus adding calendar events." if config.ENABLE_CALENDAR_WRITE else "."))
        if st.session_state.get("google_error"):
            ui.note("warn", f"Last Google error: {st.session_state['google_error']}")
    else:
        ui.note("warn", "Not connected, or a new permission was switched on in .env.")
        if st.button("Connect Google", type="primary", help="Opens Google's sign-in page in your browser"):
            try:
                state.connect_google()
                st.rerun()
            except Exception as error:
                st.error(f"Google sign-in failed: {error}")
    ui.muted(f"Drafts into Gmail: {'on' if config.ENABLE_GMAIL_DRAFTS else 'off'}. Adding calendar events: "
             f"{'on' if config.ENABLE_CALENDAR_WRITE else 'off'}. Both are switched in .env. The app can never send an email.")

    ui.section("Outlook (Microsoft)")
    if not microsoft.is_configured():
        ui.muted("Not set up. Add MS_CLIENT_ID to .env first. The setup guide has the five steps. "
                 "A university account may need approval from the university's IT team.")
    elif microsoft.is_connected():
        ui.note("good", "Connected, read-only mail and calendar.")
    else:
        if st.button("Connect Outlook", type="primary"):
            try:
                st.session_state["ms_flow"] = microsoft.start_login()
            except Exception as error:
                st.error(f"Could not start the Microsoft sign-in: {error}")
        flow = st.session_state.get("ms_flow")
        if flow:
            st.markdown(f"1. Open [{flow['verification_uri']}]({flow['verification_uri']})\n2. Enter this code:")
            st.code(flow["user_code"], language=None)
            if st.button("I have signed in"):
                try:
                    if microsoft.finish_login(flow):
                        st.session_state.pop("ms_flow")
                        st.rerun()
                    else:
                        st.warning("Microsoft has not confirmed the sign-in yet. Finish it in the browser, then press again.")
                except Exception as error:
                    st.error(f"Sign-in failed: {error}")

    ui.section("Apple")
    ui.rows([
        ui.row("iCloud Mail", "Read-only over IMAP, using an app-specific password in .env.",
               "set" if apple.mail_configured() else "not set", tone="good" if apple.mail_configured() else "neutral"),
        ui.row("iCloud Calendar", "Read-only over CalDAV. Needs the same password and `pip install caldav`.",
               "ready" if apple.calendar_configured() else "not set", tone="good" if apple.calendar_configured() else "neutral"),
        ui.row("Apple Health", "Imported from an export file on the Health page. Apple offers no live connection.", "manual import"),
    ])

    ui.section("Voice")
    engine = voice.stt_engine()
    ui.rows([
        ui.row("Speaking replies", "Uses the Mac's built-in voice.", "available" if voice.can_speak() else "Mac only"),
        ui.row("Listening", "Transcribed on your Mac by a local Whisper model. Nothing is uploaded.",
               engine.replace("_", "-") if engine else "not installed", tone="good" if engine else "neutral"),
    ])

# ------------------------------------------------------------------
with usage:
    now_ts = time.time()
    periods = {"Today": state.midnight().timestamp(), "Last 7 days": now_ts - 7 * 86400, "Last 30 days": now_ts - 30 * 86400}
    period = st.segmented_control("Period", list(periods), default="Last 7 days", key="usage_period") or "Last 7 days"
    summary = db.ai_usage_summary(periods[period])
    cost = claude.estimate_cost(summary["by_purpose"])
    ui.kpis([
        ("requests", summary["calls"]),
        ("answered from cache", summary["cache_hits"], "free", "good"),
        ("tokens in", f"{summary['input_tokens']:,}"),
        ("tokens out", f"{summary['output_tokens']:,}"),
        ("estimated cost", f"${cost:,.2f}" if cost is not None else "prices not set", "" if cost is not None else "add them in config.py"),
    ])
    if summary["by_purpose"]:
        ui.table([{"What for": row["purpose"], "Model": row["model"], "Requests": row["calls"],
                   "Tokens in": row["input_tokens"], "Tokens out": row["output_tokens"], "From cache": row["cache_hits"]}
                  for row in summary["by_purpose"]])
    else:
        ui.empty("No Claude requests in this period.")
    ui.muted("On the Pro plan, tokens count against your plan's usage limits and cost nothing extra. With an API key they are billed. "
             f"The sidebar warns once a day's total passes {config.DAILY_TOKEN_BUDGET:,}.")
    ui.section("How the app keeps usage low")
    st.markdown(
        "- Pages read from the local database. Opening or switching pages uses no tokens.\n"
        "- Each email is analysed once, in batches, with the cheapest model. Bulk mail is filed by rules and never reaches Claude.\n"
        f"- At most {config.MAX_AI_EMAILS_PER_SYNC} emails are analysed per mail check, and mail is checked at most every {config.AUTO_SYNC_MINUTES} minutes.\n"
        "- Briefings, study notes, news summaries and health reviews are stored and reused until the underlying data changes.\n"
        f"- Chat re-sends only the last {config.CHAT_HISTORY_TURNS} messages and only the data sources you tick.")

# ------------------------------------------------------------------
with preferences:
    with st.form("preferences"):
        a, b, c = st.columns(3)
        bedtime = a.text_input("Bedtime target (HH:MM)", value=state.pref("bedtime"))
        sleep_target = b.number_input("Sleep target (hours)", value=float(state.pref("sleep_target")), min_value=5.0, max_value=10.0, step=0.5)
        train_time = c.selectbox("Prefer to train in the", ["morning", "midday", "evening"],
                                 index=["morning", "midday", "evening"].index(state.pref("train_time")))
        d, e = st.columns(2)
        gym_days = d.selectbox("Gym days a week", [3, 4], index=1 if int(state.pref("gym_days")) >= 4 else 0)
        run_days = e.selectbox("Runs a week", [0, 1, 2, 3], index=min(int(state.pref("run_days")), 3))
        if ui.submit("Save preferences", type="primary"):
            if len(bedtime) == 5 and bedtime[2] == ":" and bedtime.replace(":", "").isdigit():
                state.set_pref("bedtime", bedtime)
            for key, value in (("sleep_target", sleep_target), ("train_time", train_time), ("gym_days", gym_days), ("run_days", run_days)):
                state.set_pref(key, value)
            st.rerun()
    ui.muted("Model names, tutoring hours, rent, news feeds and the watchlist defaults live in config.py.")

# ------------------------------------------------------------------
with data:
    ui.section("Caches")
    a, b, c = st.columns(3)
    if a.button("Refresh prices now"):
        market.clear_cache()
        st.toast("Prices will reload on the next visit to Markets")
    if b.button("Refresh news now"):
        news.clear_cache()
        st.toast("Headlines will reload on the next visit to Markets")
    if c.button("Forget stored Claude answers", help="Briefings and notes will be rewritten when next requested"):
        db.ai_cache_clear()
        st.toast("Stored answers cleared")

    ui.section("Backup")
    ui.muted("Everything you enter lives in one file, secretary.db, on this Mac. It is not uploaded anywhere and Git ignores it.")
    if config.DB_PATH.exists():
        st.download_button("Download a backup of secretary.db", data=config.DB_PATH.read_bytes(),
                           file_name=f"secretary-backup-{time.strftime('%Y-%m-%d')}.db")
