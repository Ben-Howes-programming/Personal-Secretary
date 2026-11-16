"""
market.py
=========
Purpose : Prices and price history for funds, indices, currencies and commodities.
Location: services/market.py
Used by : views/markets.py, views/finance.py, views/home.py
Data    : Yahoo Finance through the free `yfinance` package. Prices can be delayed
          by 15 minutes or more and are for tracking, not for trading decisions.
Cache   : Each symbol is fetched at most once every 30 minutes and stored in SQLite.
          If Yahoo is unreachable, the last stored prices are shown and marked stale.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from database import database as db

HISTORY_TTL = 30 * 60        # seconds
FX_SYMBOL = "GBPUSD=X"       # how many dollars one pound buys


def _download(symbol):
    """Two years of daily closes for one symbol, straight from Yahoo."""
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    frame = ticker.history(period="2y", interval="1d", auto_adjust=True)
    if frame is None or frame.empty:
        raise ValueError("no price data returned")
    currency = None
    try:
        currency = (ticker.history_metadata or {}).get("currency")
    except Exception:
        pass
    if not currency:
        try:
            currency = ticker.fast_info["currency"]
        except Exception:
            currency = None
    closes = [[index.strftime("%Y-%m-%d"), float(value)] for index, value in frame["Close"].items()
              if value == value]   # value == value drops NaN
    return {"symbol": symbol, "currency": currency, "closes": closes}


def get_history(symbol, force=False):
    """Cached history: {"symbol", "currency", "closes": [[date, close], ...], "stale", "error"}."""
    key = f"hist:{symbol}"
    if not force:
        cached = db.cache_get(key)
        if cached:
            return cached
    try:
        data = _download(symbol)
        data["stale"], data["error"] = False, None
        db.cache_set(key, data, HISTORY_TTL)
        return data
    except ImportError:
        error = "The yfinance package is not installed. Run: pip install yfinance"
    except Exception as problem:
        error = str(problem)[:160]
    old = db.cache_get(key, allow_stale=True)
    if old:
        old["stale"], old["error"] = True, error
        return old
    return {"symbol": symbol, "currency": None, "closes": [], "stale": True, "error": error}


def get_many(symbols, force=False):
    """Fetch several symbols at once. Only the uncached ones touch the network."""
    symbols = list(dict.fromkeys(symbols))   # keep order, drop repeats
    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(zip(symbols, pool.map(lambda s: get_history(s, force), symbols)))


def to_gbp(price, currency, gbpusd=None):
    """Convert a quoted price to pounds.

    London funds are quoted in pence (GBp or GBX), pounds (GBP) or dollars (USD).
    Returns None when the currency is one we cannot convert.
    """
    if price is None:
        return None
    if currency in ("GBp", "GBX", "GBx"):
        return price / 100
    if currency == "GBP":
        return price
    if currency == "USD" and gbpusd:
        return price / gbpusd
    return None


def pct_change(new, old):
    return None if not old or new is None else (new / old - 1) * 100


def _close_on_or_before(closes, target_iso):
    result = None
    for day, value in closes:
        if day <= target_iso:
            result = value
        else:
            break
    return result


def summarise(history, gbpusd=None, currency_override=None):
    """Headline numbers for one symbol from its history."""
    closes = history.get("closes") or []
    currency = currency_override or history.get("currency")
    out = {"symbol": history.get("symbol"), "currency": currency, "ok": bool(closes),
           "stale": history.get("stale"), "error": history.get("error"), "price": None, "price_gbp": None,
           "day": None, "month": None, "ytd": None, "year": None, "volatility": None, "drawdown": None,
           "as_of": None}
    if not closes:
        return out
    last_day, last = closes[-1]
    today = date.fromisoformat(last_day)
    out.update(price=last, as_of=last_day, price_gbp=to_gbp(last, currency, gbpusd))
    if len(closes) > 1:
        out["day"] = pct_change(last, closes[-2][1])
    out["month"] = pct_change(last, _close_on_or_before(closes, (today - timedelta(days=30)).isoformat()))
    out["ytd"] = pct_change(last, _close_on_or_before(closes, f"{today.year - 1}-12-31"))
    out["year"] = pct_change(last, _close_on_or_before(closes, (today - timedelta(days=365)).isoformat()))
    out["volatility"] = annualised_volatility([value for _day, value in closes[-253:]])
    out["drawdown"] = max_drawdown([value for _day, value in closes[-253:]])
    return out


def annualised_volatility(values):
    """Standard deviation of daily log returns, scaled by sqrt(252), in percent."""
    returns = [math.log(b / a) for a, b in zip(values, values[1:]) if a > 0 and b > 0]
    if len(returns) < 20:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252) * 100


def max_drawdown(values):
    """Largest fall from a previous peak, in percent (a negative number)."""
    peak, worst = None, 0.0
    for value in values:
        peak = value if peak is None else max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1)
    return worst * 100 if values else None


def gbpusd_rate(force=False):
    closes = get_history(FX_SYMBOL, force).get("closes") or []
    return closes[-1][1] if closes else None


def indexed(histories, days):
    """Rows for a comparison chart: every series rebased to 100 at the start of the window."""
    rows = []
    for symbol, history in histories.items():
        closes = (history.get("closes") or [])[-days:]
        if not closes:
            continue
        base = closes[0][1]
        rows.extend({"date": day, "series": symbol, "value": value / base * 100} for day, value in closes)
    return rows


def clear_cache():
    db.cache_clear("hist:")
