"""
more_pages.py
=============
Purpose : Data for the Health, Markets, Placements and Tutoring tabs of the Cassiopeia
          window (ported from the classic Streamlit pages in views/).
Location: cassiopeia/more_pages.py
Used by : cassiopeia/server.py, cassiopeia/triggers.py
Tokens  : Loading any of these tabs costs nothing. The calculations are rules in
          services/training.py, services/market.py and database/. Claude is only
          called from the two "write a review" and "study note" buttons.
Note    : Health is general training guidance, not medical advice. Markets is general
          information, not personal financial advice. Paper trades use pretend money.
"""

import time
from datetime import date, timedelta

import config
from ai import claude
from cassiopeia import events
from database import database as db
from database import finance, health, tasks
from services import calendar as cal
from services import market, news, training

PREF_DEFAULTS = {"bedtime": config.BEDTIME_TARGET, "sleep_target": config.SLEEP_TARGET_HOURS,
                 "gym_days": config.GYM_DAYS_PER_WEEK, "run_days": config.RUN_DAYS_PER_WEEK,
                 "train_time": "evening"}


def pref(key):
    """The same preferences the classic dashboard stores (settings table, pref_* keys)."""
    return db.get_setting(f"pref_{key}", PREF_DEFAULTS.get(key))


def _number(value, name, low=None, high=None, allow_blank=False):
    if allow_blank and (value is None or str(value).strip() == ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if (low is not None and number < low) or (high is not None and number > high):
        raise ValueError(f"{name} must be between {low:g} and {high:g}.")
    return number


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------
def health_numbers():
    """The figures every part of the Health tab is built from."""
    today = events.now().date()
    sleep_rows = health.get_sleep(30)
    week_sleep = training.sleep_stats([r for r in sleep_rows if r["date"] >= (today - timedelta(days=7)).isoformat()],
                                      float(pref("sleep_target")))
    load = training.weekly_load(health.get_workouts(70))
    body = health.get_body(30)
    weight = health.latest_weight()
    protein_range = training.protein_target(weight, config.PROTEIN_G_PER_KG)
    protein_days = [r["protein_g"] for r in body[-7:] if r.get("protein_g")]
    return {"today": today, "sleep_rows": sleep_rows, "week_sleep": week_sleep, "load": load,
            "this_week": load[-1] if load else {"strength": 0, "runs": 0, "run_km": 0.0},
            "ratio": training.run_load_ratio(load), "weight": weight, "protein_range": protein_range,
            "protein_avg": sum(protein_days) / len(protein_days) if protein_days else None}


def week_plan(next_week=False):
    """Training sessions for the week, each given a time that fits around the calendar."""
    n = health_numbers()
    monday = training.week_start(n["today"]) + timedelta(days=7 if next_week else 0)
    start = cal.at(monday, "00:00")
    week_events, errors = events.between(start, start + timedelta(days=7))
    last_km = n["load"][-2]["run_km"] if len(n["load"]) >= 2 else (n["load"][-1]["run_km"] if n["load"] else 0.0)
    plan = training.suggest_times(training.build_week_plan(int(pref("gym_days")), int(pref("run_days")), monday, last_km),
                                  week_events, config.TRAINING_WINDOW, pref("train_time"), pref("bedtime"))
    return [{"date": d["date"].isoformat(), "title": d["title"], "kind": d["kind"], "details": d["details"],
             "start": d["start"].strftime("%H:%M") if d.get("start") else None,
             "end": d["end"].strftime("%H:%M") if d.get("end") else None,
             "today": d["date"] == n["today"]} for d in plan], errors


def health_page(next_week=False):
    n = health_numbers()
    plan, errors = week_plan(next_week)
    exercises = []
    for name in health.list_exercises():
        lifts = health.get_lifts(365, name)
        trend = training.strength_trend(lifts)
        exercises.append({"name": name, "trend": trend[-12:], "next": training.next_lift_target(lifts)})
    return {
        "sleep": n["week_sleep"], "sleep_target": float(pref("sleep_target")), "bedtime": pref("bedtime"),
        "this_week": n["this_week"], "gym_days": int(pref("gym_days")), "run_days": int(pref("run_days")),
        "train_time": pref("train_time"), "ratio": n["ratio"], "weight": n["weight"],
        "protein_avg": n["protein_avg"], "protein_range": n["protein_range"],
        "insights": [{"tone": tone, "text": text} for tone, text in training.insights(
            n["week_sleep"], n["load"], n["ratio"], n["protein_avg"], n["protein_range"],
            (int(pref("gym_days")), int(pref("run_days"))))],
        "sleep_history": [{"date": r["date"], "hours": r["hours"]} for r in n["sleep_rows"] if r.get("hours")],
        "weeks": n["load"][-8:], "plan": plan, "plan_errors": errors, "next_week": bool(next_week),
        "recent": health.get_workouts(30)[-8:][::-1], "exercises": exercises,
        "note": "General training guidance, not medical advice.",
    }


def health_update(action, body):
    today = events.now().date().isoformat()
    if action == "sleep":
        bed, wake = str(body.get("bed", "")), str(body.get("wake", ""))
        if len(bed) < 5 or len(wake) < 5:
            raise ValueError("Bed and wake times must look like 23:30.")
        quality = int(_number(body.get("quality", 3), "How rested", 1, 5))
        health.log_sleep(body.get("night") or today, bed[:5], wake[:5], quality)
    elif action == "body":
        health.log_body(today, _number(body.get("weight"), "Weight", 30, 250, allow_blank=True),
                        _number(body.get("protein"), "Protein", 0, 600, allow_blank=True),
                        _number(body.get("energy"), "Energy", 1, 5, allow_blank=True))
    elif action == "workout":
        if body.get("kind") not in ("strength", "run", "other"):
            raise ValueError("Pick strength, run or other.")
        health.log_workout(body.get("date") or today, body["kind"], str(body.get("title", "")).strip(),
                           _number(body.get("minutes", 60), "Minutes", 0, 600),
                           _number(body.get("distance"), "Distance", 0, 300, allow_blank=True),
                           _number(body.get("effort"), "Effort", 1, 10, allow_blank=True))
    elif action == "lift":
        name = str(body.get("exercise", "")).strip()
        if not name:
            raise ValueError("Name the exercise.")
        health.log_lift(today, name, _number(body.get("weight"), "Weight", 0, 500),
                        int(_number(body.get("reps", 8), "Reps", 1, 50)), int(_number(body.get("sets", 3), "Sets", 1, 12)))
    elif action == "plan-settings":
        gym, runs = int(_number(body.get("gym_days"), "Gym days", 3, 4)), int(_number(body.get("run_days"), "Runs", 0, 3))
        if body.get("train_time") not in ("morning", "midday", "evening"):
            raise ValueError("Pick morning, midday or evening.")
        for key, value in (("gym_days", gym), ("run_days", runs), ("train_time", body["train_time"])):
            db.set_setting(f"pref_{key}", value)
    elif action == "plan-to-calendar":
        return plan_to_calendar(bool(body.get("next_week")))
    else:
        raise ValueError("Unknown health action.")
    return health_page(bool(body.get("next_week")))


def plan_to_calendar(next_week=False):
    """Copy the timed sessions into Cassiopeia's own calendar (Google is not changed). Skips duplicates."""
    plan, _errors = week_plan(next_week)
    added = 0
    for day in plan:
        if not day["start"]:
            continue
        start, end = f"{day['date']}T{day['start']}:00", f"{day['date']}T{day['end']}:00"
        # Once added, the session itself blocks that time, so the plan would move it: match on title and day instead
        if db.query("SELECT 1 FROM cass_events WHERE title = ? AND substr(start_iso, 1, 10) = ?", (day["title"], day["date"])):
            continue
        db.execute("INSERT INTO cass_events (title, start_iso, end_iso, notes, created_ts) VALUES (?, ?, ?, ?, ?)",
                   (day["title"], start, end, "\n".join(day["details"]), time.time()))
        added += 1
    page = health_page(next_week)
    page["added"] = added
    return page


def health_review():
    """One Claude call, cached for a day for the same numbers."""
    n = health_numbers()
    summary = (f"Sleep: {n['week_sleep']}. This week: {n['this_week']}. Running load ratio: {n['ratio']}. "
               f"Protein average: {n['protein_avg']}, target range: {n['protein_range']}. "
               f"Plan: {pref('gym_days')} strength and {pref('run_days')} runs a week. Goal: build muscle and general fitness.")
    return {"review": claude.health_review(summary)}


# ------------------------------------------------------------------
# Markets (general information, not personal financial advice)
# ------------------------------------------------------------------
MARKET_NOTE = "General information, not personal financial advice. Paper trades use pretend money."


def _price_text(figures):
    if not figures["ok"]:
        return None
    return figures["price_gbp"] if figures["price_gbp"] is not None else figures["price"]


def markets_page(days=130, force=False):
    watch = finance.list_watchlist()
    histories = market.get_many([w["symbol"] for w in watch] + [t[0] for t in config.MARKET_TRACKERS]
                                + [market.FX_SYMBOL], force=force)
    rate = market.gbpusd_rate()

    def figures(symbol, currency=None):
        f = market.summarise(histories.get(symbol) or market.get_history(symbol), rate, currency)
        return {k: f[k] for k in ("ok", "price", "price_gbp", "currency", "day", "month", "ytd", "year",
                                  "volatility", "drawdown", "as_of", "stale", "error")}

    headlines = []
    try:
        headlines = news.get_news()
    except Exception:
        pass
    funds = []
    for w in watch:
        hits = news.matching(headlines, (w.get("keywords") or "").split(","))[:3] if w["kind"] == "holding" else []
        funds.append({"symbol": w["symbol"], "name": w["name"], "kind": w["kind"], "note": w.get("note"),
                      "figures": figures(w["symbol"], w.get("currency")),
                      "news": [{"title": h["title"], "link": h["link"], "source": h.get("source", "")} for h in hits]})
    holdings = [w["symbol"] for w in watch if w["kind"] == "holding"]
    trades = []
    for t in finance.list_paper_trades():
        now_gbp = figures(t["symbol"])["price_gbp"]
        value_now = t["units"] * (t["close_price_gbp"] if t.get("close_price_gbp") else (now_gbp or 0))
        cost = t["units"] * t["price_gbp"]
        trades.append(dict(t, value_now=value_now if (now_gbp or t.get("close_price_gbp")) else None,
                           gain=(value_now / cost - 1) if cost and (now_gbp or t.get("close_price_gbp")) else None))
    problems = sorted({h["error"] for h in histories.values() if h.get("error")})
    return {"funds": funds, "trackers": [dict(symbol=s, name=n, about=a, figures=figures(s)) for s, n, a in config.MARKET_TRACKERS],
            "chart": market.indexed({s: histories[s] for s in holdings if s in histories}, int(days)),
            "days": int(days), "gbpusd": rate, "trades": trades, "problems": problems[:3], "note": MARKET_NOTE}


def markets_update(action, body):
    if action == "watch":
        symbol = str(body.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("Enter a Yahoo Finance symbol, for example VUAG.L.")
        kind = "research" if body.get("kind") == "research" else "holding"
        finance.add_to_watchlist(symbol, str(body.get("name", "")).strip() or symbol, kind,
                                 note=str(body.get("note", "")).strip(), keywords=str(body.get("keywords", "")).strip())
    elif action == "unwatch":
        finance.remove_from_watchlist(str(body.get("symbol", "")))
    elif action == "paper-buy":
        symbol, amount = str(body.get("symbol", "")).strip().upper(), _number(body.get("amount"), "Amount", 1, 1_000_000)
        thesis = str(body.get("thesis", "")).strip()
        if not thesis:
            raise ValueError("Write one line on why. Reviewing the reason later is the point of the exercise.")
        price = market.summarise(market.get_history(symbol), market.gbpusd_rate())["price_gbp"]
        if not price:
            raise ValueError(f"No price in pounds for {symbol}. Check the symbol.")
        finance.add_paper_trade(symbol, amount / price, price, thesis)
    elif action == "paper-close":
        trade = next((t for t in finance.list_paper_trades() if t["id"] == int(body.get("id", 0))), None)
        if not trade:
            raise ValueError("No such paper trade.")
        price = market.summarise(market.get_history(trade["symbol"]), market.gbpusd_rate())["price_gbp"]
        if not price:
            raise ValueError("No current price, so the trade cannot be closed yet.")
        finance.close_paper_trade(trade["id"], price)
    else:
        raise ValueError("Unknown markets action.")
    return markets_page()


def study_note(symbol):
    """Claude's balanced study note on one instrument, cached for a week."""
    item = next((w for w in finance.list_watchlist() if w["symbol"] == symbol), None)
    name = item["name"] if item else symbol
    f = market.summarise(market.get_history(symbol), market.gbpusd_rate())
    facts = {k: f[k] for k in ("price_gbp", "year", "volatility", "drawdown", "as_of")}
    return {"symbol": symbol, "note": claude.ticker_brief(symbol, name, facts)}


# ------------------------------------------------------------------
# Placements
# ------------------------------------------------------------------
def placements_page():
    today = events.now().date()
    rows = []
    for p in tasks.list_placements():
        gap = (date.fromisoformat(p["deadline"]) - today).days if p.get("deadline") else None
        rows.append(dict(p, days_left=gap, urgent=gap is not None and 0 <= gap <= 14 and p["status"] in ("Researching", "Drafting")))
    live = [p for p in rows if p["status"] not in ("Rejected", "Closed", "Offer")]
    upcoming = [p for p in live if p["days_left"] is not None and p["days_left"] >= 0 and p["status"] in ("Researching", "Drafting")]
    return {"placements": rows, "statuses": tasks.PLACEMENT_STATUSES,
            "counts": {"in progress": len(live), "applied": sum(p["status"] == "Applied" for p in rows),
                       "interviews": sum(p["status"] == "Interview" for p in rows)},
            "next": upcoming[0] if upcoming else None}


def placements_update(action, body):
    if action == "add":
        organisation = str(body.get("organisation", "")).strip()
        if not organisation:
            raise ValueError("Enter the organisation.")
        link = str(body.get("link", "")).strip()
        if link and not link.startswith(("http://", "https://")):
            raise ValueError("The link must start with http:// or https://.")
        tasks.add_placement(organisation, str(body.get("role", "")).strip(), str(body.get("location", "")).strip(),
                            body.get("deadline") or None, link=link)
    elif action == "update":
        status = body.get("status")
        if status not in tasks.PLACEMENT_STATUSES:
            raise ValueError("Unknown status.")
        tasks.update_placement(int(body["id"]), status, str(body.get("notes", "")), body.get("deadline") or None)
    elif action == "remove":
        tasks.delete_placement(int(body["id"]))
    else:
        raise ValueError("Unknown placements action.")
    return placements_page()


# ------------------------------------------------------------------
# Tutoring
# ------------------------------------------------------------------
def tutoring_page():
    """Free lesson slots on the next two tutoring days, and enquiries filed as Tutoring."""
    now = events.now()
    first = cal.next_weekday(config.TUTORING_WEEKDAY, now)
    days = []
    for day in (first, first + timedelta(days=7)):
        start, end = cal.at(day, config.TUTORING_WINDOW[0]), cal.at(day, config.TUTORING_WINDOW[1])
        found, errors = events.between(start.replace(hour=0, minute=0), start.replace(hour=0, minute=0) + timedelta(days=1))
        slots = [s for s in cal.free_slots_from_events(found, start, end, config.TUTORING_LESSON_MINUTES) if s[0] > now]
        days.append({"day": day.strftime("%A %d %B"), "slots": [a.strftime("%H:%M") for a, _b in slots], "errors": errors})
    enquiries = [{"id": e["id"], "sender": (e.get("sender") or "").split("<")[0].strip().strip('"'),
                  "subject": e.get("subject"), "summary": e["analysis"].get("summary"), "received_ts": e.get("received_ts")}
                 for e in db.list_emails(120, include_done=False) if e["analysis"].get("category") == "Tutoring"]
    return {"window": list(config.TUTORING_WINDOW), "lesson_minutes": config.TUTORING_LESSON_MINUTES,
            "days": days, "enquiries": enquiries}
