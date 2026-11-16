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
}
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


def daily_returns(rows, strategy, cost_bps=None):
    """[(date, return)] for one strategy. Pure function: same rows in, same numbers out."""
    cost = (config.LAB_COST_BPS if cost_bps is None else cost_bps) / 10_000
    returns = []
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
    return {name: summarise(daily_returns(rows, name, cost_bps)) for name in STRATEGIES}


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
                       "win_rate, max_drawdown) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (today, symbol, name, stats["trades"], stats["total_return"], stats["annualised"],
                        stats["win_rate"], stats["max_drawdown"]))
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
    return {"strategies": STRATEGIES, "names": names, "cost_bps": config.LAB_COST_BPS,
            "start_cash": config.PAPER_START_CASH,
            "backtests": db.query("SELECT * FROM cass_backtests ORDER BY symbol, strategy"),
            "paper": paper,
            "study_list": [{"symbol": s, "name": n, "teaches": why} for s, n, why in config.RESEARCH_LIST],
            "disclaimer": "Test money and past prices only. General information, not personal financial advice."}
