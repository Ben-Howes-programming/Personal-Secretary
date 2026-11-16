"""
app.py
======
Purpose : Entry point. Sets up the theme, the database and the sidebar, then hands
          over to whichever page you pick. Each page lives in its own file in views/.
Location: project root
Run     : streamlit run app.py
"""

import streamlit as st

import config
from ai import claude
from database import database as db
from services import apple, microsoft
from ui import state
from ui import theme as ui

st.set_page_config(page_title="Secretary", page_icon="🌒", layout="wide", initial_sidebar_state="expanded")
ui.inject()
db.initialise_database()

# ------------------------------------------------------------------
# Pages, grouped in the sidebar
# ------------------------------------------------------------------
pages = {
    "": [
        st.Page("views/home.py", title="Today", icon=":material/wb_twilight:", default=True),
        st.Page("views/assistant.py", title="Assistant", icon=":material/forum:"),
    ],
    "Messages and time": [
        st.Page("views/inbox.py", title="Inbox", icon=":material/mail:"),
        st.Page("views/calendar_view.py", title="Calendar", icon=":material/calendar_month:"),
        st.Page("views/tasks.py", title="Tasks", icon=":material/checklist:"),
        st.Page("views/tutoring.py", title="Tutoring", icon=":material/school:"),
    ],
    "Money": [
        st.Page("views/finance.py", title="Finance", icon=":material/account_balance:"),
        st.Page("views/markets.py", title="Markets", icon=":material/show_chart:"),
    ],
    "You": [
        st.Page("views/health.py", title="Health", icon=":material/fitness_center:"),
        st.Page("views/university.py", title="University", icon=":material/menu_book:"),
        st.Page("views/placements.py", title="Placements", icon=":material/rocket_launch:"),
    ],
    "System": [
        st.Page("views/settings.py", title="Settings", icon=":material/settings:"),
    ],
}
current_page = st.navigation(pages)

# ------------------------------------------------------------------
# Sidebar: late-night nudge, connection status, refresh
# ------------------------------------------------------------------
with st.sidebar:
    moment = state.now()
    if moment.hour >= 23 or moment.hour < 5:
        ui.note("warn", f"It is {moment.strftime('%H:%M')}. Your bedtime target is {state.pref('bedtime')}. Park it and sleep.")

    backend = claude.backend_status()
    claude_label = {"claude_code": "Claude (Pro plan)", "api": "Claude (API key)"}.get(backend["active"], "Claude")
    statuses = [
        (claude_label, backend["active"] is not None),
        ("Google", state.google_ready()),
    ]
    if microsoft.is_configured():
        statuses.append(("Outlook", microsoft.is_connected()))
    if apple.mail_configured():
        statuses.append(("iCloud", True))
    lines = "".join(
        f'<div class="ps-muted"><span style="color:{ui.GOOD if ok else ui.BAD}">●</span> {ui.esc(name)}'
        f'{"" if ok else " (not connected)"}</div>' for name, ok in statuses)
    st.markdown(lines, unsafe_allow_html=True)

    used = claude.tokens_today()
    if used > config.DAILY_TOKEN_BUDGET:
        ui.note("warn", f"{used:,} tokens used today, over your {config.DAILY_TOKEN_BUDGET:,} guide.")
    else:
        ui.muted(f"{used:,} tokens used today")

    if ui.button("Refresh data", help="Clear the five-minute cache and reload calendar and mail status"):
        st.cache_data.clear()
        st.rerun()

current_page.run()
