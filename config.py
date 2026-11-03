"""
config.py
=========
Purpose : One place for paths, scopes and settings, so no other file hard-codes them.
Location: project root
Used by : services/google_auth.py, database/health.py, pages/1_Health.py
Note    : Think of it as your gym membership card. Everything else just shows it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Folder containing this file, so paths work wherever you launch from
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# Files
DB_PATH = PROJECT_ROOT / "secretary.db"
GOOGLE_CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
GOOGLE_TOKEN_PATH = PROJECT_ROOT / "token.json"

# Read-only scopes. If you change this list, delete token.json and log in again.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Claude
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-5-5"   # verify against docs.claude.com

# App
MAX_EMAILS = 20
TIMEZONE = "Europe/London"