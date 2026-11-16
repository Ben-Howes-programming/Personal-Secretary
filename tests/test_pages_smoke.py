"""
test_pages_smoke.py
===================
Purpose : Runs app.py and every page top to bottom against a stand-in for Streamlit,
          with sample data, to catch crashes (typos, missing imports, bad data
          handling) without opening a browser.
Location: tests/test_pages_smoke.py
Run     : python tests/test_pages_smoke.py   (or as part of: python -m pytest tests -q)
Limits  : It proves each page runs, not that it looks right. Layout still needs a
          human look in the browser. Google, Yahoo and Claude are never contacted.
"""

import runpy
import sys
import tempfile
import types
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
UK = ZoneInfo("Europe/London")
PRESS = {"on": False}     # when True, every button reports that it was pressed


class StopPage(Exception):
    pass


class State(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


def _value(args, kwargs, position, fallback=None):
    if "value" in kwargs:
        return kwargs["value"]
    return args[position] if len(args) > position else fallback


class Box:
    """Stands in for st, st.sidebar, a column, a tab, a form or an expander."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def columns(self, spec, **_kw):
        return [Box() for _ in range(spec if isinstance(spec, int) else len(spec))]

    def tabs(self, names):
        return [Box() for _ in names]

    def button(self, *_a, **_kw):
        return PRESS["on"]

    form_submit_button = download_button = button

    def toggle(self, *_a, **kw):
        return kw.get("value", False)

    checkbox = toggle

    def text_input(self, *args, **kw):
        return kw.get("value", "sample" if PRESS["on"] else "")

    text_area = text_input

    def number_input(self, *args, **kw):
        return _value(args, kw, 3, 1.0 if PRESS["on"] else None) if "value" in kw or len(args) > 3 else (1.0 if PRESS["on"] else 0.0)

    def slider(self, *args, **kw):
        return _value(args, kw, 3, 1)

    def select_slider(self, label, options, **kw):
        return kw.get("value", options[0])

    def selectbox(self, label, options, index=0, **_kw):
        options = list(options)
        if PRESS["on"] and options and options[0] is None and len(options) > 1:
            return options[1]
        return options[index] if options and index is not None else None

    def multiselect(self, label, options, default=None, **_kw):
        return list(default or [])

    def pills(self, label, options, default=None, **_kw):
        return default

    segmented_control = pills

    def date_input(self, *args, **kw):
        return kw["value"] if "value" in kw else date.today()

    def time_input(self, *args, **kw):
        return kw.get("value", time(9, 0))

    def file_uploader(self, *_a, **_kw):
        return None

    audio_input = chat_input = file_uploader

    def write_stream(self, stream):
        return "".join(stream)

    def stop(self):
        raise StopPage()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name in ("container", "expander", "form", "chat_message", "spinner", "popover", "empty", "status"):
            return lambda *a, **k: Box()
        return lambda *a, **k: None       # markdown, write, latex, toast, rerun, page_link ...


def _cache(function=None, **_kw):
    def wrap(inner):
        inner.clear = lambda: None
        return inner
    return wrap(function) if callable(function) else wrap


def fake_streamlit():
    module = types.ModuleType("streamlit")
    box = Box()
    for name in dir(Box):
        if not name.startswith("_"):
            setattr(module, name, getattr(box, name))
    module.__getattr__ = lambda name: getattr(box, name)
    module.__version__ = "0.0-smoke"
    module.session_state = State()
    module.sidebar = Box()
    module.cache_data = _cache
    module.cache_resource = _cache
    module.cache_data.clear = module.cache_resource.clear = lambda: None
    module.column_config = mock.MagicMock()
    module.Page = lambda path, **kw: types.SimpleNamespace(path=path, run=lambda: None, **kw)
    module.navigation = lambda pages, **kw: types.SimpleNamespace(run=lambda: None)
    return module


def sample_data():
    """Fill a temporary database so every loop on every page has something to draw."""
    from database import database as db, finance, health, tasks, university
    db.initialise_database()
    today = date.today()
    iso = lambda offset: (today + timedelta(days=offset)).isoformat()
    db.save_email({"id": "e1", "sender": "Parent <p@example.com>", "subject": "Lesson <b>Sunday</b>?", "date": "today",
                   "body": "Is Ben free Sunday afternoon?", "received_ts": 2.0, "analysed_by": "claude",
                   "analysis": {"category": "Tutoring", "priority": "High", "action_required": True, "reply_needed": True,
                                "availability_request": True, "requested_day": "Sunday", "requested_start": "12:00",
                                "requested_end": "17:00", "summary": "Asks about a Sunday lesson."}, "draft_reply": "Hi"})
    db.save_email({"id": "e2", "sender": "Shop <x@shop.com>", "subject": "Sale", "date": "today", "body": "..",
                   "received_ts": 1.0, "analysed_by": "pending", "status": "completed", "provider": "outlook",
                   "analysis": {"category": "Marketing", "priority": "Low", "summary": "Sale."}})
    accounts = finance.list_accounts()
    for number, account in enumerate(accounts):
        finance.record_balance(account["id"], 500.0 * (number + 1), iso(-20))
        finance.record_balance(account["id"], 520.0 * (number + 1), iso(0))
        finance.update_account(account["id"], 4.1)
    finance.add_holding(accounts[0]["id"], "VWRP.L", 10, 100.0)
    finance.add_holding(accounts[0]["id"], "NODATA.L", 1, 1.0)
    finance.add_contribution(accounts[1]["id"], 400.0)
    finance.add_cashflow("expense", "Food", 12.5, "lunch")
    finance.add_paper_trade("WQTM.L", 5, 30.0, "Testing a view", on=iso(-30))
    for symbol, *_ in [("NODATA.L",)]:
        db.cache_set(f"hist:{symbol}", {"symbol": symbol, "currency": None, "closes": [], "stale": True, "error": "no data"}, 3600)
    import config
    symbols = [w["symbol"] for w in finance.list_watchlist()] + [t[0] for t in config.MARKET_TRACKERS] + ["GBPUSD=X"]
    for position, symbol in enumerate(symbols):
        closes = [[iso(offset - 400), 100 + position + offset * 0.05 + (offset % 7)] for offset in range(400)]
        currency = "USD" if symbol.startswith("WQTM") else ("GBp" if symbol.endswith(".L") else None)
        if symbol == "GBPUSD=X":
            closes = [[day, 1.25] for day, _value in closes]
        db.cache_set(f"hist:{symbol}", {"symbol": symbol, "currency": currency, "closes": closes, "stale": False, "error": None}, 3600)
    for feed in config.NEWS_FEEDS:
        db.cache_set(f"news:{feed[3]}", [{"title": "Quantum stocks rally on interest rates", "link": f"https://example.com/{feed[1]}",
                                          "summary": "Summary", "published_ts": 1.7e9, "source": feed[0], "section": feed[1],
                                          "lean": feed[2]}], 3600)
    for offset in range(1, 12):
        health.log_sleep(iso(-offset), "23:45" if offset % 2 else "00:40", "07:15", 3)
        health.log_body(iso(-offset), 75.0 + offset / 10, 120 + offset, 3)
        health.log_workout(iso(-offset), "run" if offset % 3 == 0 else "strength", "Session", 55, 5.0 if offset % 3 == 0 else None, 7)
        health.log_lift(iso(-offset), "Bench press", 60 + offset, 8, 3)
    module = university.list_modules()[0]
    first = university.add_assessment(module["id"], "Problem sheet", iso(2), 20)
    university.add_assessment(module["id"], "Exam", iso(40), 80)
    university.set_mark(first, 68)
    university.add_assessment(module["id"], "Lab report", iso(5), None)
    university.update_module(module["id"], "PH2", 6)
    university.log_study(module["id"], 90, "", iso(-1))
    university.log_lecture(module["id"], "Partition function", 2, on=iso(-3))
    tasks.add_task("Overdue thing", "General", "High", iso(-1))
    tasks.add_task("Today thing", "Health", "Medium", iso(0))
    tasks.add_task("No date", "Money", "Low", None)
    done = tasks.add_task("Finished", "Home", "Low", None)
    tasks.complete_task(done)
    tasks.add_placement("ESA", "Trainee", "Noordwijk", iso(7), link="https://example.com")
    tasks.add_placement("CERN", "", "", None, status="Applied")


def sample_events(start, end):
    today = datetime.now(UK).replace(hour=0, minute=0, second=0, microsecond=0)
    events = []
    for offset in range(-1, 15):
        day = (today + timedelta(days=offset)).date().isoformat()
        events.append({"summary": "Lecture", "start": {"dateTime": f"{day}T09:15:00+00:00"},
                       "end": {"dateTime": f"{day}T11:05:00+00:00"}, "source": "Google"})
    events.append({"summary": "Reading week", "start": {"date": today.date().isoformat()},
                   "end": {"date": (today + timedelta(days=1)).date().isoformat()}, "source": "iCloud"})
    keep = [e for e in events if "date" in e["start"] or start <= datetime.fromisoformat(e["start"]["dateTime"]) < end]
    return keep, ["Outlook: sample error"]


def run_all():
    sys.modules["streamlit"] = fake_streamlit()
    sys.modules.setdefault("altair", mock.MagicMock())
    import config
    config.DB_PATH = Path(tempfile.mkdtemp()) / "smoke.db"
    config.AI_BACKEND, config.ANTHROPIC_API_KEY = "api", "smoke-test"      # never start the real Claude Code
    sample_data()

    from ai import claude
    from ui import state
    claude._api_complete = lambda system, context, messages, tier, max_tokens: ("Sample answer.", {"input": 10, "output": 5}, "fake")
    claude.stream = lambda *a, **k: iter(["Sample ", "answer."])
    state.events_between = sample_events
    state.week_events = lambda: sample_events(state.midnight(), state.midnight(7))[0]
    state.any_calendar = state.any_mail = lambda: True

    pages = ["app.py"] + sorted(str(path.relative_to(ROOT)) for path in (ROOT / "views").glob("*.py"))
    failures = []
    for pressed in (False, True):
        PRESS["on"] = pressed
        for page in pages:
            sys.modules["streamlit"].session_state.clear()
            try:
                runpy.run_path(str(ROOT / page), run_name="__main__")
            except StopPage:
                pass
            except Exception as error:   # report every failure, then fail at the end
                import traceback
                failures.append((page, pressed, traceback.format_exc(limit=-3)))
                print(f"FAIL {page} (buttons pressed: {pressed}): {error!r}")
            else:
                print(f"ok   {page} (buttons pressed: {pressed})")
    return failures


def test_every_page_runs():
    assert run_all() == []


if __name__ == "__main__":
    problems = run_all()
    for page, pressed, trace in problems:
        print("\n" + "=" * 70 + f"\n{page} (buttons pressed: {pressed})\n{trace}")
    sys.exit(1 if problems else 0)
