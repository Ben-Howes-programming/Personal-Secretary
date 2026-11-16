"""
config.py
=========
Purpose : One place for paths, feature flags, model names and personal defaults.
Location: project root
Used by : every other module. Nothing else should hard-code a path or a setting.
Note    : Secrets live in .env (never in this file). Anything marked VERIFY is a
          value you should check against the official source before relying on it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Folder containing this file, so paths work wherever you launch from
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _flag(name, default=False):
    """Read a true/false switch from .env, e.g. ENABLE_CALENDAR_WRITE=true."""
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------
# Files
# ------------------------------------------------------------------
DB_PATH = PROJECT_ROOT / "secretary.db"
GOOGLE_CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
GOOGLE_TOKEN_PATH = PROJECT_ROOT / "token.json"
MS_TOKEN_PATH = PROJECT_ROOT / "ms_token.json"

# ------------------------------------------------------------------
# Google. Read-only by default. The two write features are opt-in:
# turn one on in .env, delete token.json, and log in again.
# ------------------------------------------------------------------
ENABLE_GMAIL_DRAFTS = _flag("ENABLE_GMAIL_DRAFTS")      # save a reply into Gmail Drafts (never sends)
ENABLE_CALENDAR_WRITE = _flag("ENABLE_CALENDAR_WRITE")  # add events such as gym sessions

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
if ENABLE_GMAIL_DRAFTS:
    GOOGLE_SCOPES.append("https://www.googleapis.com/auth/gmail.compose")
if ENABLE_CALENDAR_WRITE:
    GOOGLE_SCOPES.append("https://www.googleapis.com/auth/calendar.events")

GMAIL_QUERY = "in:inbox newer_than:21d"   # which emails a sync looks at
MAX_EMAILS = 25                           # emails fetched per sync
MAX_AI_EMAILS_PER_SYNC = 12               # hard cap on emails sent to Claude per sync
EMAIL_BODY_CHARS = 2500                   # body is trimmed to this before Claude sees it
AUTO_SYNC_MINUTES = 30                    # the inbox re-syncs itself at most this often

# ------------------------------------------------------------------
# Claude
# AI_BACKEND: "auto"        use your Claude Pro plan through Claude Code if it is
#                           installed, otherwise the API key
#             "claude_code" Pro plan only (runs `claude -p`)
#             "api"         API key only (billed separately from Pro)
# ------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AI_BACKEND = os.environ.get("AI_BACKEND", "auto").strip().lower()

# Three tiers so cheap jobs never use an expensive model.
MODELS = {                       # VERIFY names at docs.claude.com
    "fast": "claude-haiku-5-5",   # email triage, short summaries
    "chat": "claude-sonnet-5-5",  # the assistant
    "deep": "claude-opus-5-5",    # long analysis you ask for explicitly
}
CLI_MODELS = {"fast": "haiku", "chat": "sonnet", "deep": "opus"}   # names `claude -p --model` accepts
CLAUDE_MODEL = MODELS["chat"]    # kept so older code that imports this still works

CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "")   # leave blank to find `claude` automatically
# Extra flags: one turn only, and no tools, so Claude Code only writes text and cannot touch files.
# Checked against Claude Code 2.1.325. If a later version rejects one, the app retries without them.
CLAUDE_CLI_EXTRA_ARGS = ["--max-turns", "1", "--tools", ""]
CLAUDE_CLI_TIMEOUT = 180                                  # seconds

# Optional cost estimate. Fill in USD per million tokens from the pricing page,
# e.g. {"claude-sonnet-5-5": (input_price, output_price)}. Empty means tokens only.
PRICES_PER_MTOK = {}

CHAT_HISTORY_TURNS = 12          # only the last N messages are re-sent to Claude
DAILY_TOKEN_BUDGET = 400_000     # soft limit; the app warns when you pass it

# ------------------------------------------------------------------
# You
# ------------------------------------------------------------------
OWNER_NAME = "Ben"
TIMEZONE = "Europe/London"

BEDTIME_TARGET = "23:30"
SLEEP_TARGET_HOURS = 8.0
PROTEIN_G_PER_KG = (1.6, 2.2)    # common sports-nutrition range for muscle gain
GYM_DAYS_PER_WEEK = 4
RUN_DAYS_PER_WEEK = 2
TRAINING_WINDOW = ("07:00", "20:30")   # sessions are only suggested inside this window

RENT_PER_MONTH = 750.0
DEGREE_TARGET = 75.0

TUTORING_WEEKDAY = 6             # Monday is 0, so 6 is Sunday
TUTORING_WINDOW = ("12:00", "18:00")
TUTORING_LESSON_MINUTES = 60

# UK allowances. VERIFY each tax year on gov.uk.
ISA_ALLOWANCE = 20_000.0
LISA_ALLOWANCE = 4_000.0
LISA_BONUS_RATE = 0.25

# ------------------------------------------------------------------
# Markets. Symbols use Yahoo Finance codes (London listings end in .L).
# ------------------------------------------------------------------
DEFAULT_WATCHLIST = [
    # symbol, name, kind, keywords used to match news headlines
    ("VWRP.L", "Vanguard FTSE All-World (Acc)", "holding",
     "global equities,stock markets,wall street,federal reserve,interest rates,nvidia,apple,microsoft,emerging markets"),
    ("VALL.L", "Vanguard FTSE Global All Cap (Acc)", "holding",
     "global equities,small caps,stock markets,interest rates,earnings"),
    ("WQTM.L", "WisdomTree Quantum Computing (Acc)", "holding",
     "quantum,ionq,d-wave,rigetti,ibm,qubit"),
]

# A study list, not a buy list. Each one is here because it teaches a concept.
RESEARCH_LIST = [
    ("VUAG.L", "Vanguard S&P 500 (Acc)", "Single-country concentration versus a global fund"),
    ("VFEG.L", "Vanguard FTSE Emerging Markets (Acc)", "Higher growth hopes, higher volatility, currency risk"),
    ("WLDS.L", "iShares MSCI World Small Cap", "The size factor: do smaller companies behave differently?"),
    ("VMID.L", "Vanguard FTSE 250", "Home bias and UK mid caps"),
    ("IGLT.L", "iShares Core UK Gilts", "Bonds: how prices move against interest rates"),
    ("SGLN.L", "iShares Physical Gold", "An asset with no cash flows, often held as a diversifier"),
    ("EQQQ.L", "Invesco Nasdaq-100", "Sector concentration in large US technology"),
]

MARKET_TRACKERS = [
    # symbol, name, what it tells you
    ("^FTSE", "FTSE 100", "The 100 largest London-listed companies. Heavy in banks, energy and miners."),
    ("^GSPC", "S&P 500", "500 large US companies. The reference point for most global equity funds."),
    ("^IXIC", "Nasdaq Composite", "US technology-heavy index. Moves more than the S&P 500 in both directions."),
    ("^VIX", "VIX", "Expected S&P 500 volatility from option prices. Rises when investors are nervous."),
    ("^TNX", "US 10-year yield", "The return on lending to the US government for ten years. Higher yields pull down bond prices and pressure growth stocks."),
    ("GBPUSD=X", "Pound in dollars", "Matters because your global funds hold mostly dollar assets. A weaker pound lifts their value in pounds."),
    ("GC=F", "Gold", "Priced in dollars per ounce. Often rises when real interest rates fall or fear rises."),
    ("BZ=F", "Brent crude", "The oil benchmark for Europe. Feeds into inflation and energy shares."),
]

# News. `lean` is shown beside every headline so you always know the source's slant.
MYFT_RSS_URL = os.environ.get("MYFT_RSS_URL", "")   # your personal myFT feed address (optional)
NEWS_FEEDS = [
    # source, section, lean, url
    ("FT", "Markets", "Centre, pro-market and economically liberal", "https://www.ft.com/markets?format=rss"),
    ("FT", "Companies", "Centre, pro-market and economically liberal", "https://www.ft.com/companies?format=rss"),
    ("FT", "Technology", "Centre, pro-market and economically liberal", "https://www.ft.com/technology?format=rss"),
    ("FT", "World", "Centre, pro-market and economically liberal", "https://www.ft.com/world?format=rss"),
    ("BBC", "Business", "Public broadcaster with an impartiality duty", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC", "Top stories", "Public broadcaster with an impartiality duty", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("BBC", "Science", "Public broadcaster with an impartiality duty", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("Guardian", "Business", "Centre-left", "https://www.theguardian.com/uk/business/rss"),
    ("Guardian", "World", "Centre-left", "https://www.theguardian.com/world/rss"),
]
if MYFT_RSS_URL:
    NEWS_FEEDS.insert(0, ("FT", "myFT", "Centre, pro-market and economically liberal", MYFT_RSS_URL))

# ------------------------------------------------------------------
# Optional integrations (all off until you fill these in .env)
# ------------------------------------------------------------------
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
MS_TENANT = os.environ.get("MS_TENANT", "common")
MS_SCOPES = ["Mail.Read", "Calendars.Read"]

ICLOUD_USER = os.environ.get("ICLOUD_USER", "")
ICLOUD_APP_PASSWORD = os.environ.get("ICLOUD_APP_PASSWORD", "")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")   # speech-to-text model size
