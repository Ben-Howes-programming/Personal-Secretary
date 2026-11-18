"""
lab.py
======
Purpose : The trading lab. Tests simple daily patterns on past prices, then follows the
          same patterns forward one day at a time with test money. No real orders, ever.
Location: cassiopeia/lab.py
Used by : cassiopeia/scheduler.py (overnight job), cassiopeia/server.py
Honesty : A pattern that looks good on past prices often fails later, and trading costs
          eat small edges. Every result here subtracts config.LAB_COST_BPS per round trip,
          which is an assumption you should replace with your broker's real figure.
          General information, not personal financial advice.
"""

from datetime import date

import config
from database import database as db
from database import finance

STRATEGIES = {
    "overnight": "Buy at the close, sell at the next open",
    "intraday": "Buy at the open, sell at the same day's close",
    "hold": "Buy once and hold (the benchmark to beat)",
    "trend_50": "Hold only while the price is above its 50-day average",
    "cross_20_100": "Hold while the 20-day average is above the 100-day average",
    "momentum_6m": "Hold while the price is higher than six months ago",
    "dip_buy": "Buy the day after a fall of more than 2%, sell a day later",
    "three_down": "Buy after three falling days in a row, sell a day later",
    "turn_of_month": "Hold only for the last two and first three trading days of each month",
}

# What each rule is testing, in plain words. Shown on the Lab page.
RULE_NOTES = {
    "overnight": "Some studies find most stock-market gains arrive overnight rather than during trading hours. "
                 "This trades every day, so costs are charged every day. If it loses to Hold after costs, the edge is too small to use.",
    "intraday": "The mirror image of the overnight rule. Useful as a check: if both overnight and intraday beat Hold, something is wrong with the data.",
    "hold": "Doing nothing. Every other rule has to beat this after costs to be worth anything.",
    "trend_50": "Trend following: stay in while the market is rising, step aside when it falls below its recent average. "
                "The hope is to dodge long falls. The usual cost is being whipsawed in and out in choppy markets. Watch the Worst fall column against Hold.",
    "cross_20_100": "A slower trend rule, often called a golden cross. It trades less than the 50-day rule, so costs matter less, but it reacts later.",
    "momentum_6m": "Time-series momentum: assets that rose over the last six months have tended to keep rising for a while. Trades rarely.",
    "dip_buy": "Mean reversion: after a sharp one-day fall, prices sometimes bounce. Tests whether that bounce is reliable for a broad fund. It is in the market only a few days a year.",
    "three_down": "Another mean-reversion test: three falls in a row as a sign of an overreaction. Expect few trades, so treat any result with suspicion.",
    "turn_of_month": "A calendar effect: money from salaries and pension contributions arrives around month end. "
                     "Holds about a quarter of the time. If its return is close to Hold's with less time in the market, that is interesting. If not, the effect has faded.",
}
POSITION_RULES = {"trend_50", "cross_20_100", "momentum_6m", "dip_buy", "three_down", "turn_of_month"}
TRADING_DAYS = 252          # trading days in a year, used to annualise


def ohlc(symbol, force=False):
    """Two years of [date, open, close] rows from Yahoo, cached for 12 hours. [] if unavailable."""
    key = f"ohlc:{symbol}"
    cached = None if force else db.cache_get(key)
    if cached is not None:
        return cached
    try:
        import yfinance as yf
        frame = yf.Ticker(symbol).history(period="2y", interval="1d", auto_adjust=True)
        rows = [[index.strftime("%Y-%m-%d"), float(o), float(c)]
                for index, o, c in zip(frame.index, frame["Open"], frame["Close"]) if o == o and c == c and o > 0]
    except Exception:
        return db.cache_get(key, allow_stale=True) or []
    db.cache_set(key, rows, 12 * 3600)
    return rows


def _average(closes, end, length):
    """Mean of the `length` closes up to and including index `end`, or None if there is not enough history."""
    if end + 1 < length:
        return None
    window = closes[end + 1 - length:end + 1]
    return sum(window) / length


def positions(rows, strategy):
    """1 (hold) or 0 (cash) for each day after the first, decided using only data up to the previous close.

    position[i] applies to the move from close i to close i+1, so no rule can see the future.
    """
    closes = [row[2] for row in rows]
    months = [row[0][:7] for row in rows]
    from_start = [sum(1 for m in months[:k + 1] if m == months[k]) for k in range(len(rows))]   # 1 = first trading day
    from_end = [sum(1 for m in months[k:] if m == months[k]) for k in range(len(rows))]         # 1 = last trading day
    held = []
    for i in range(len(rows) - 1):
        if strategy == "trend_50":
            average = _average(closes, i, 50)
            held.append(1 if average is not None and closes[i] > average else 0)
        elif strategy == "cross_20_100":
            fast, slow = _average(closes, i, 20), _average(closes, i, 100)
            held.append(1 if slow is not None and fast > slow else 0)
        elif strategy == "momentum_6m":
            held.append(1 if i >= 126 and closes[i] > closes[i - 126] else 0)
        elif strategy == "dip_buy":
            held.append(1 if i >= 1 and closes[i] / closes[i - 1] - 1 < -0.02 else 0)
        elif strategy == "three_down":
            held.append(1 if i >= 3 and closes[i] < closes[i - 1] < closes[i - 2] < closes[i - 3] else 0)
        elif strategy == "turn_of_month":
            # Day i+1 is the day being held. The trading calendar is known in advance, so using it is not cheating.
            held.append(1 if from_end[i + 1] <= 2 or from_start[i + 1] <= 3 else 0)
        else:
            held.append(1)
    return held


def daily_returns(rows, strategy, cost_bps=None):
    """[(date, return)] for one strategy. Pure function: same rows in, same numbers out.

    Cash earns nothing here (an assumption: in reality it would earn some interest).
    For the position rules, half the round-trip cost is charged on each day the position changes.
    """
    cost = (config.LAB_COST_BPS if cost_bps is None else cost_bps) / 10_000
    returns = []
    if strategy in POSITION_RULES:
        previous_position = 0
        for (prev, today), position in zip(zip(rows, rows[1:]), positions(rows, strategy)):
            value = position * (today[2] / prev[2] - 1)
            if position != previous_position:
                value -= cost / 2                          # one side of a round trip
            previous_position = position
            returns.append((today[0], value))
        return returns
    for previous, today in zip(rows, rows[1:]):
        day, opened, closed = today
        if strategy == "overnight":
            value = opened / previous[2] - 1 - cost        # yesterday's close to today's open
        elif strategy == "intraday":
            value = closed / opened - 1 - cost             # today's open to today's close
        else:
            value = closed / previous[2] - 1               # holding pays no daily trading cost
        returns.append((day, value))
    return returns


def exposure(rows, strategy):
    """Share of days in the market and how many times the rule switched in or out."""
    if strategy not in POSITION_RULES:
        return 1.0, (len(rows) - 1 if strategy in ("overnight", "intraday") else 1)
    held = positions(rows, strategy)
    switches = sum(1 for a, b in zip([0] + held, held) if a != b)
    return (sum(held) / len(held) if held else 0.0), switches


def summarise(returns):
    """Total return, annualised return, win rate and worst peak-to-trough fall."""
    if not returns:
        return None
    equity, peak, worst, wins = 1.0, 1.0, 0.0, 0
    for _day, value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
        wins += value > 0
    n = len(returns)
    return {"trades": n, "total_return": equity - 1, "annualised": equity ** (TRADING_DAYS / n) - 1,
            "win_rate": wins / n, "max_drawdown": worst}


def backtest(rows, cost_bps=None):
    results = {}
    for name in STRATEGIES:
        stats = summarise(daily_returns(rows, name, cost_bps))
        if stats:
            stats["exposure"], stats["switches"] = exposure(rows, name)
        results[name] = stats
    return results


def symbols():
    """Your watchlist plus the study list. Nothing here is a recommendation."""
    listed = [row["symbol"] for row in finance.list_watchlist()]
    return list(dict.fromkeys(listed + [item[0] for item in config.RESEARCH_LIST]))


def run_overnight():
    """The nightly job: refresh backtests and move each paper account forward. Returns a summary line."""
    today, tested, stepped = date.today().isoformat(), 0, 0
    for symbol in symbols():
        rows = ohlc(symbol)
        if len(rows) < 30:
            continue
        db.execute("DELETE FROM cass_backtests WHERE symbol = ?", (symbol,))   # keep only the latest run per symbol
        for name, stats in backtest(rows).items():
            db.execute("INSERT INTO cass_backtests (run_day, symbol, strategy, trades, total_return, annualised, "
                       "win_rate, max_drawdown, exposure, switches) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (today, symbol, name, stats["trades"], stats["total_return"], stats["annualised"],
                        stats["win_rate"], stats["max_drawdown"], stats["exposure"], stats["switches"]))
            stepped += forward_step(symbol, name, rows)
        tested += 1
    return f"{tested} symbols tested, {stepped} paper-account days added."


def forward_step(symbol, strategy, rows):
    """Add any sessions the paper account has not seen yet. This is the honest test:
    the pattern was fixed before these days happened. Returns how many days were added."""
    last = db.query("SELECT day, equity FROM cass_paper WHERE strategy = ? AND symbol = ? ORDER BY day DESC LIMIT 1",
                    (strategy, symbol))
    if not last:      # first night: open the account at today's date with the starting cash, no return yet
        db.execute("INSERT OR IGNORE INTO cass_paper (day, strategy, symbol, day_return, equity) VALUES (?, ?, ?, 0, ?)",
                   (rows[-1][0], strategy, symbol, config.PAPER_START_CASH))
        return 0
    equity, added = last[0]["equity"], 0
    for day, value in daily_returns(rows, strategy):
        if day > last[0]["day"]:
            equity *= 1 + value
            db.execute("INSERT OR IGNORE INTO cass_paper (day, strategy, symbol, day_return, equity) VALUES (?, ?, ?, ?, ?)",
                       (day, strategy, symbol, value, equity))
            added += 1
    return added


def report():
    """Everything the Lab page shows."""
    names = {row["symbol"]: row["name"] for row in finance.list_watchlist()}
    names.update({item[0]: item[1] for item in config.RESEARCH_LIST})
    paper = db.query("SELECT p.strategy, p.symbol, p.day, p.equity, "
                     "(SELECT COUNT(*) - 1 FROM cass_paper q WHERE q.strategy = p.strategy AND q.symbol = p.symbol) AS days "
                     "FROM cass_paper p WHERE p.day = (SELECT MAX(day) FROM cass_paper q "
                     "WHERE q.strategy = p.strategy AND q.symbol = p.symbol) ORDER BY p.symbol, p.strategy")
    return {"strategies": STRATEGIES, "notes": RULE_NOTES, "names": names, "cost_bps": config.LAB_COST_BPS,
            "start_cash": config.PAPER_START_CASH,
            "backtests": db.query("SELECT * FROM cass_backtests ORDER BY symbol, strategy"),
            "paper": paper,
            "study_list": [{"symbol": s, "name": n, "teaches": why} for s, n, why in config.RESEARCH_LIST],
            "disclaimer": "Test money and past prices only. General information, not personal financial advice."}
