# Personal Secretary

A local dashboard that pulls my email, calendar, tasks, money, training and university work into one place, with a Claude assistant that can see all of it.

I started it to cut the routine admin of being a student. Version 1.0 is a full rebuild: the first version was a single-file prototype, this one is a modular app with a proper data layer, tests, and a strict budget on AI usage.

## What it does

| Page | What you get |
|---|---|
| Today | What needs me now: emails needing action, a timeline of the day with a suggested training slot, tasks, deadlines, fund prices |
| Assistant | Chat with Claude using my own data as context, by typing or voice. Chats are saved locally |
| Inbox | Gmail (plus optional Outlook and iCloud) triaged by priority, with summaries and reply drafts. The app never sends mail |
| Calendar | Merged agenda and a free-time finder |
| Tasks | To-dos grouped by urgency |
| Tutoring | Free lesson slots from the live calendar and enquiries awaiting a reply |
| Finance | Accounts, net worth over time, holdings with live value, budget, ISA allowances, savings projections |
| Markets | Fund tracking, market indicators with plain-English notes, news with source lean shown, a pretend-money portfolio, and a short course on the vocabulary |
| Health | Sleep and training patterns, a weekly gym and running plan timed around the calendar, strength progression, Apple Health import |
| University | Deadlines, marks against a target, study time, and a spaced review queue for lectures |
| Placements | Application tracker |
| Settings | Connections, Claude usage, preferences, backup |

## How it is built

- **Python and Streamlit** for the interface, **SQLite** for storage, all on my own machine.
- **Claude** through either a Claude Pro plan (via Claude Code) or the Anthropic API, chosen in `.env`.
- **Google APIs** for Gmail and Calendar, read-only unless a write feature is switched on.
- **Yahoo Finance** (yfinance) for prices and **RSS** for headlines.

```
app.py        entry point and navigation
config.py     settings, no secrets
ai/           every Claude call, context building, voice
database/     schema and queries, one module per area
services/     Google, Outlook, iCloud, markets, news, training logic
ui/           theme, shared components, cached state
views/        one file per page
tests/        logic tests and a page smoke test
```

### Keeping AI usage low

The assistant is useful because it sees real data, which could get expensive. The app is designed so that it does not:

- Pages read from the local database, so opening one costs nothing.
- Each email is analysed once, in batches, by the cheapest model. Bulk mail is filed by rules and never reaches Claude.
- Briefings, study notes and summaries are stored and reused until the data behind them changes.
- Health, finance and university analysis is ordinary Python, not AI.
- Every request is logged, and the Settings page shows where tokens went.

### Safety choices

- No email is ever sent. Drafts are for me to review.
- Calendar and Gmail access is read-only by default.
- Credentials and the database are kept out of Git.
- Email text is treated as untrusted: escaped before display and marked as data in prompts.
- Finance and health pages give general information, not advice.

## Running it

See [SETUP_GUIDE.md](SETUP_GUIDE.md). In short:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in what you use
streamlit run app.py
```

Tests: `python -m pytest tests -q`

## Status

Version 1.0, November 2026. Under active development. [CLAUDE.md](CLAUDE.md) documents the architecture and conventions for anyone, human or AI, working on the code.
