"""
test_core.py
============
Purpose : Checks the logic that does not need a browser, Google or Claude.
Location: tests/test_core.py
Run     : python -m pytest tests -q     (from the project folder, venv active)
Note    : Uses a temporary database, so your real secretary.db is never touched.
"""

import io
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

UK = ZoneInfo("Europe/London")


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    from database import database as db
    db.initialise_database()
    yield


def event(day, start, end, **extra):
    return dict({"summary": "Busy", "start": {"dateTime": f"{day}T{start}:00+00:00"},
                 "end": {"dateTime": f"{day}T{end}:00+00:00"}}, **extra)


# Database -----------------------------------------------------------
def test_database_seeds_once_and_upgrades_old_tables(tmp_path, monkeypatch):
    import sqlite3
    from database import database as db, finance
    assert len(finance.list_accounts()) == 6
    db.initialise_database()                      # second run must not duplicate anything
    assert len(finance.list_accounts()) == 6
    assert {w["symbol"] for w in finance.list_watchlist("holding")} == {"VWRP.L", "VALL.L", "WQTM.L"}

    # An old-style database with the original emails table gains the new columns
    old = tmp_path / "old.db"
    connection = sqlite3.connect(old)
    connection.execute("CREATE TABLE emails (id TEXT PRIMARY KEY, sender TEXT, subject TEXT, date TEXT, body TEXT, "
                       "category TEXT, priority TEXT, action_required INTEGER, reply_needed INTEGER, summary TEXT, draft_reply TEXT)")
    connection.execute("INSERT INTO emails VALUES ('a1', 'x@y.com', 'Hi', 'Mon, 02 Nov 2026 10:00:00 +0000', 'body', "
                       "'Personal', 'High', 1, 1, 'sum', NULL)")
    connection.commit()
    connection.close()
    monkeypatch.setattr(config, "DB_PATH", old)
    db.initialise_database()
    email = db.get_cached_email("a1")
    assert email["analysis"]["priority"] == "High" and email["provider"] == "gmail"
    assert email["received_ts"] is not None


def test_email_round_trip_and_caches():
    from database import database as db
    db.save_email({"id": "m1", "sender": "A <a@b.com>", "subject": "S", "date": "d", "body": "b", "received_ts": 5.0,
                   "analysis": {"category": "Tutoring", "priority": "High", "action_required": True, "reply_needed": True,
                                "summary": "x"}, "analysed_by": "claude"})
    assert db.email_is_cached("m1") and db.list_emails()[0]["analysis"]["reply_needed"] is True
    db.update_email_status("m1", "completed")
    assert db.list_emails(include_done=False) == []
    db.cache_set("k", {"a": 1}, 60)
    assert db.cache_get("k") == {"a": 1}
    db.cache_set("old", 1, -1)
    assert db.cache_get("old") is None and db.cache_get("old", allow_stale=True) == 1
    db.set_setting("x", [1, 2])
    assert db.get_setting("x") == [1, 2] and db.get_setting("missing", 7) == 7


# Claude helpers (no network) ------------------------------------------
def test_json_extraction_and_cleaning():
    from ai import claude
    assert claude.extract_json('```json\n[{"n": 1}]\n```') == [{"n": 1}]
    assert claude.extract_json('Here you go: {"a": 2} thanks') == {"a": 2}
    assert claude.extract_json("no json") is None
    cleaned = claude.clean_analysis({"category": "Nonsense", "priority": "High", "action_required": False,
                                     "reply_needed": True, "availability_request": True, "requested_start": "afternoon"})
    assert cleaned["category"] == "Other" and cleaned["reply_needed"] is False and cleaned["requested_start"] is None


def test_rules_file_bulk_mail_but_never_university_mail():
    from ai import claude
    promo = {"sender": "Shop <offers@shop.com>", "labels": ["CATEGORY_PROMOTIONS"], "snippet": "50% off"}
    assert claude.quick_classify(promo)["category"] == "Marketing"
    uni = {"sender": "Dept <noreply@bath.ac.uk>", "labels": ["CATEGORY_PROMOTIONS"], "list_unsubscribe": True}
    assert claude.quick_classify(uni) is None
    assert claude.quick_classify({"sender": "Parent <p@gmail.com>", "labels": ["INBOX"]}) is None


def test_batch_analysis_and_response_cache(monkeypatch):
    from ai import claude
    calls = []

    def fake_api(system, context, messages, tier, max_tokens):
        calls.append(tier)
        return '[{"n": 2, "category": "Tutoring", "priority": "High", "action_required": true, "summary": "second"}]', {}, "fake"

    monkeypatch.setattr(config, "AI_BACKEND", "api")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(claude, "_api_complete", fake_api)
    results = claude.analyse_emails([{"sender": "a", "subject": "1", "body": "x"}, {"sender": "b", "subject": "2", "body": "y"}])
    assert results[0] is None and results[1]["category"] == "Tutoring" and calls == ["fast"]

    first = claude.complete("same question", cache_ttl=60)
    second = claude.complete("same question", cache_ttl=60)
    assert first == second and len(calls) == 2          # the second identical request never reached the backend


def test_no_backend_gives_a_clear_error(monkeypatch):
    from ai import claude
    monkeypatch.setattr(config, "AI_BACKEND", "api")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
    with pytest.raises(claude.AIError):
        claude.complete("hello")


# Calendar -------------------------------------------------------------
def test_free_slots_ignore_all_day_and_free_events():
    from services import calendar as cal
    start, end = datetime(2026, 11, 22, 12, tzinfo=UK), datetime(2026, 11, 22, 18, tzinfo=UK)
    events = [event("2026-11-22", "13:00", "14:30"),
              {"summary": "Reading week", "start": {"date": "2026-11-22"}, "end": {"date": "2026-11-23"}},
              event("2026-11-22", "16:00", "17:00", transparency="transparent")]
    slots = cal.free_slots_from_events(events, start, end, 60)
    assert [s[0].strftime("%H:%M") for s in slots] == ["12:00", "14:30", "15:30", "16:30"]
    window = cal.requested_window({"requested_day": "Sunday", "requested_start": "12:00", "requested_end": "17:00"},
                                  now=datetime(2026, 11, 16, 9, tzinfo=UK))
    assert window[0].date() == date(2026, 11, 22) and window[1].hour == 17


# Finance --------------------------------------------------------------
def test_finance_maths():
    from database import finance
    assert finance.tax_year_start(date(2026, 4, 5)) == date(2025, 4, 6)
    assert finance.tax_year_start(date(2026, 4, 6)) == date(2026, 4, 6)
    assert finance.future_value(1000, 0, 0, 10) == 1000
    assert finance.future_value(0, 100, 0, 1) == 1200
    assert round(finance.future_value(1000, 0, 12, 1), 2) == 1126.83      # 1% a month, compounded
    plan = finance.payoff_plan(1500, date(2027, 2, 16), today=date(2026, 11, 16))
    assert plan["months"] == 3 and plan["per_month"] == 500


def test_net_worth_and_budget():
    from database import finance
    accounts = {a["name"]: a for a in finance.list_accounts()}
    finance.record_balance(accounts["Chase saver 1"]["id"], 2000, "2026-11-01")
    finance.record_balance(accounts["Student overdraft"]["id"], 500, "2026-11-01")
    finance.record_balance(accounts["Chase saver 1"]["id"], 2600, "2026-11-10")
    worth = finance.net_worth()
    assert worth["net"] == 2100 and worth["debts"] == 500
    assert [h["net_worth"] for h in finance.net_worth_history()] == [1500, 2100]
    budget = finance.monthly_budget([{"kind": "income", "amount": 1000, "frequency": "monthly"},
                                     {"kind": "expense", "amount": 750, "frequency": "monthly"}])
    assert budget["surplus"] == 250 and budget["savings_rate"] == 0.25
    finance.add_contribution(accounts["Lifetime ISA"]["id"], 1000, date.today().isoformat())
    assert finance.contributions_this_tax_year()["lisa"] == 1000


# Markets --------------------------------------------------------------
def test_currency_conversion_and_summary():
    from services import market
    assert market.to_gbp(373, "GBp") == 3.73
    assert market.to_gbp(110.5, "GBP") == 110.5
    assert market.to_gbp(50, "USD", 1.25) == 40
    assert market.to_gbp(50, "USD") is None and market.to_gbp(50, "EUR", 1.25) is None
    start = date(2026, 1, 1)
    closes = [[(start + timedelta(days=i)).isoformat(), 100 + i] for i in range(300)]
    figures = market.summarise({"symbol": "X.L", "currency": "GBp", "closes": closes})
    assert figures["ok"] and figures["price_gbp"] == pytest.approx(3.99)
    assert figures["day"] == pytest.approx((399 / 398 - 1) * 100)
    assert figures["drawdown"] == 0 and figures["volatility"] is not None
    assert market.max_drawdown([100, 120, 60, 90]) == -50
    rows = market.indexed({"A": {"closes": closes}}, 10)
    assert rows[0]["value"] == 100 and len(rows) == 10


def test_price_cache_serves_stale_data_when_offline(monkeypatch):
    from database import database as db
    from services import market
    db.cache_set("hist:OLD.L", {"symbol": "OLD.L", "currency": "GBP", "closes": [["2026-11-13", 5.0]]}, -1)
    monkeypatch.setattr(market, "_download", lambda symbol: (_ for _ in ()).throw(RuntimeError("offline")))
    history = market.get_history("OLD.L")
    assert history["stale"] is True and history["closes"][0][1] == 5.0 and "offline" in history["error"]
    assert market.get_history("NEW.L")["closes"] == []


# News -----------------------------------------------------------------
def test_feed_parsing_and_keyword_matching():
    from services import news
    xml = """<rss><channel>
      <item><title>Quantum stocks rally as IonQ wins contract</title><link>https://example.com/a</link>
            <pubDate>Mon, 16 Nov 2026 08:00:00 GMT</pubDate><description>&lt;p&gt;Shares rose.&lt;/p&gt;</description></item>
      <item><title>Budget day</title><link>https://example.com/b</link></item></channel></rss>"""
    items = news.parse_feed(xml)
    assert len(items) == 2 and items[0]["summary"] == "Shares rose." and items[0]["published_ts"]
    assert [i["link"] for i in news.matching(items, ["quantum", "ionq"])] == ["https://example.com/a"]
    assert news.matching(items, [""]) == []


# Training -------------------------------------------------------------
def test_sleep_and_strength_maths():
    from database import health
    from services import training
    assert health.hours_between("23:30", "07:00") == 7.5
    stats = training.sleep_stats([{"hours": 6, "bed_time": "23:30"}, {"hours": 8, "bed_time": "00:30"},
                                  {"hours": 7, "bed_time": "00:00"}], 8)
    assert stats["average"] == 7 and stats["debt"] == 3 and stats["average_bedtime"] == "00:00"
    assert stats["bedtime_spread"] == pytest.approx(30)
    assert training.epley_1rm(100, 1) == 100 and training.epley_1rm(60, 10) == pytest.approx(80)
    lifts = [{"date": "2026-11-10", "weight_kg": 60, "reps": 10}]
    assert training.next_lift_target(lifts)["weight_kg"] == 62.5
    assert training.next_lift_target([{"date": "2026-11-10", "weight_kg": 60, "reps": 7}])["reps"] == 8
    assert training.protein_target(75) == (120, 165)


def test_week_plan_fits_around_the_calendar():
    from services import training
    monday = date(2026, 11, 16)
    plan = training.build_week_plan(4, 2, monday, recent_weekly_km=10)
    assert len(plan) == 7 and plan[0]["date"] == monday
    assert sum(day["kind"] == "strength" for day in plan) == 4 and sum(day["kind"] == "run" for day in plan) == 2
    assert training.run_distances(10, 2) == {"Long run": 6.5, "Quality run": 4.5}
    busy = [event("2026-11-16", "17:00", "20:30")]
    timed = training.suggest_times(plan, busy, ("07:00", "20:30"), "evening", "23:30")
    first = timed[0]
    assert first["end"] <= datetime(2026, 11, 16, 17, tzinfo=UK)           # pushed before the evening booking
    assert timed[5]["start"] is None                                        # Saturday is a rest day
    morning = training.suggest_times(plan, [], ("07:00", "20:30"), "morning", "23:30")
    assert morning[0]["start"].strftime("%H:%M") == "07:00"
    load = training.weekly_load([{"date": "2026-11-02", "kind": "run", "distance_km": 5},
                                 {"date": "2026-11-09", "kind": "run", "distance_km": 5},
                                 {"date": "2026-11-16", "kind": "run", "distance_km": 10},
                                 {"date": "2026-11-17", "kind": "strength"}], through=date(2026, 11, 18))
    assert load[-1]["strength"] == 1 and training.run_load_ratio(load) == 2
    later = training.weekly_load([{"date": "2026-11-02", "kind": "run", "distance_km": 5}], through=date(2026, 11, 18))
    assert [week["runs"] for week in later] == [1, 0, 0]                    # empty weeks are kept as zeros


# University -----------------------------------------------------------
def test_needed_mark_and_review_spacing():
    from database import university
    standing = university.module_standing([{"weight": 20, "mark": 60}, {"weight": 80, "mark": None}], 75)
    assert standing["average"] == 60 and standing["needed"] == pytest.approx(78.75)
    assert university.module_standing([], 75)["needed"] is None
    today = date(2026, 11, 16)
    assert university.next_review_date(1, 5, today) == "2026-11-19"
    assert university.next_review_date(1, 2, today) == "2026-11-17"       # still shaky: back tomorrow
    assert university.next_review_date(5, 5, today) is None
    module = university.list_modules()[0]
    university.log_lecture(module["id"], "Topic", 2, on=(date.today() - timedelta(days=2)).isoformat())
    due = university.reviews_due()
    assert len(due) == 1
    university.complete_review(due[0]["id"], 5)
    assert university.reviews_due() == []


def test_tasks_group_by_urgency():
    from database import tasks
    today = date(2026, 11, 16)
    groups = tasks.group_tasks([{"due": "2026-11-15"}, {"due": "2026-11-16"}, {"due": "2026-12-01"}, {"due": None}], today)
    assert [len(groups[k]) for k in ("Overdue", "Today", "Upcoming", "No date")] == [1, 1, 1, 1]


# Apple ----------------------------------------------------------------
def test_apple_health_export_is_parsed_and_saved():
    from database import health
    from services import apple
    recent = datetime.now(UK).replace(hour=7, minute=0, second=0, microsecond=0) - timedelta(days=2)
    stamp = lambda moment: moment.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S +0000")
    bed = recent - timedelta(hours=7, minutes=30)
    xml = f"""<?xml version="1.0"?><HealthData>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepCore"
              startDate="{stamp(bed)}" endDate="{stamp(bed + timedelta(hours=4))}"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepREM"
              startDate="{stamp(bed + timedelta(hours=4))}" endDate="{stamp(recent)}"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisInBed"
              startDate="{stamp(bed)}" endDate="{stamp(recent)}"/>
      <Record type="HKQuantityTypeIdentifierBodyMass" unit="kg" value="76.4" startDate="{stamp(recent)}" endDate="{stamp(recent)}"/>
      <Record type="HKQuantityTypeIdentifierStepCount" value="4000" startDate="{stamp(recent)}" endDate="{stamp(recent)}"/>
      <Record type="HKQuantityTypeIdentifierStepCount" value="2500" startDate="{stamp(recent)}" endDate="{stamp(recent)}"/>
      <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="31.5" durationUnit="min"
               startDate="{stamp(recent)}" endDate="{stamp(recent + timedelta(minutes=31))}">
        <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="5.2" unit="km"/>
      </Workout>
      <Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining" duration="3600" durationUnit="s"
               startDate="{stamp(recent)}" endDate="{stamp(recent)}"/>
    </HealthData>"""
    parsed = apple.parse_health_export(io.BytesIO(xml.encode()))
    assert parsed["sleep"][0]["hours"] == 7.5 and parsed["sleep"][0]["wake_time"] == "07:00"
    kinds = {w["kind"]: w for w in parsed["workouts"]}
    assert kinds["run"]["distance_km"] == 5.2 and kinds["strength"]["duration_min"] == 60
    day = recent.date().isoformat()
    assert parsed["body"][day] == {"weight_kg": 76.4, "steps": 6500}
    counts = apple.save_health_import(parsed)
    assert counts == {"sleep": 1, "workouts": 2, "body": 1}
    assert apple.save_health_import(parsed)["workouts"] == 0              # importing twice adds nothing
    assert health.latest_weight() == 76.4


def test_raw_email_is_converted_for_icloud():
    from services import apple
    raw = (b"From: Jo <jo@example.com>\r\nSubject: =?utf-8?q?Lesson_on_Sunday=3F?=\r\n"
           b"Date: Mon, 16 Nov 2026 09:00:00 +0000\r\nMessage-ID: <1@x>\r\nContent-Type: text/plain\r\n\r\nAre you free?\r\n")
    email = apple.message_to_email(raw)
    assert email["subject"] == "Lesson on Sunday?" and email["body"] == "Are you free?" and email["id"].startswith("icloud:")


def test_gmail_body_prefers_plain_text_then_html():
    import base64
    from services import gmail
    encode = lambda text: base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
    nested = {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/html", "body": {"data": encode("<p>Hello <b>Ben</b></p>")}}]}]}
    assert gmail.get_email_body(nested) == "Hello \nBen" or "Hello" in gmail.get_email_body(nested)
    nested["parts"][0]["parts"].append({"mimeType": "text/plain", "body": {"data": encode("Hello Ben")}})
    assert gmail.get_email_body(nested) == "Hello Ben"
