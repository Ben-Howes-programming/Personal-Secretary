"""
finance.py
==========
Purpose : Everything the Finance and Markets pages store: accounts, balance
          snapshots, holdings, contributions, budget lines, watchlist, paper trades.
          Also the pure maths (tax year, projections, payoff) so it can be tested.
Location: database/finance.py
Note    : No figures are invented. Balances start empty and you enter them.
"""

import time
from datetime import date, datetime

from database.database import execute, query

MONTHLY_FACTOR = {"weekly": 52 / 12, "monthly": 1.0, "yearly": 1 / 12}


# ------------------------------------------------------------------
# Accounts and balances
# ------------------------------------------------------------------
def list_accounts():
    """Every open account with its most recent balance (None until you enter one)."""
    return query(
        """
        SELECT a.*, b.balance, b.date AS balance_date
        FROM accounts a
        LEFT JOIN balances b ON b.id = (
            SELECT id FROM balances WHERE account_id = a.id ORDER BY date DESC LIMIT 1
        )
        WHERE a.archived = 0 ORDER BY a.is_liability, a.id
        """
    )


def add_account(name, kind, provider="", interest_rate=None, is_liability=False, notes=""):
    return execute(
        "INSERT INTO accounts (name, kind, provider, interest_rate, is_liability, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (name, kind, provider, interest_rate, int(is_liability), notes))


def update_account(account_id, interest_rate=None, notes=None):
    execute("UPDATE accounts SET interest_rate = ?, notes = COALESCE(?, notes) WHERE id = ?",
            (interest_rate, notes, account_id))


def archive_account(account_id):
    execute("UPDATE accounts SET archived = 1 WHERE id = ?", (account_id,))


def record_balance(account_id, balance, on=None):
    """One snapshot per account per day. Entering a second one that day replaces the first."""
    on = on or date.today().isoformat()
    execute("INSERT OR REPLACE INTO balances (account_id, date, balance) VALUES (?, ?, ?)", (account_id, on, balance))


def net_worth(accounts=None):
    """Assets minus liabilities, using the latest balance of each account."""
    accounts = list_accounts() if accounts is None else accounts
    assets = sum(a["balance"] or 0 for a in accounts if not a["is_liability"])
    debts = sum(abs(a["balance"] or 0) for a in accounts if a["is_liability"])
    return {"assets": assets, "debts": debts, "net": assets - debts,
            "has_data": any(a["balance"] is not None for a in accounts)}


def net_worth_history():
    """Net worth on every date you recorded a balance, carrying older balances forward."""
    rows = query(
        "SELECT b.date, b.account_id, b.balance, a.is_liability FROM balances b "
        "JOIN accounts a ON a.id = b.account_id WHERE a.archived = 0 ORDER BY b.date")
    latest, history = {}, {}
    for row in rows:
        sign = -1 if row["is_liability"] else 1
        latest[row["account_id"]] = sign * abs(row["balance"] or 0)
        history[row["date"]] = sum(latest.values())
    return [{"date": day, "net_worth": value} for day, value in history.items()]


# ------------------------------------------------------------------
# Holdings and contributions
# ------------------------------------------------------------------
def list_holdings():
    return query("SELECT h.*, a.name AS account FROM holdings h JOIN accounts a ON a.id = h.account_id ORDER BY a.id, h.symbol")


def add_holding(account_id, symbol, units, avg_cost):
    return execute("INSERT INTO holdings (account_id, symbol, units, avg_cost) VALUES (?, ?, ?, ?)",
                   (account_id, symbol.upper().strip(), units, avg_cost))


def delete_holding(holding_id):
    execute("DELETE FROM holdings WHERE id = ?", (holding_id,))


def add_contribution(account_id, amount, on=None):
    execute("INSERT INTO contributions (account_id, date, amount) VALUES (?, ?, ?)",
            (account_id, on or date.today().isoformat(), amount))


def tax_year_start(today=None):
    """UK tax years run 6 April to 5 April."""
    today = today or date.today()
    start = date(today.year, 4, 6)
    return start if today >= start else date(today.year - 1, 4, 6)


def contributions_this_tax_year(today=None):
    """Total paid in since 6 April, split by account kind (investment, lisa, ...)."""
    rows = query(
        "SELECT a.kind, COALESCE(SUM(c.amount), 0) AS total FROM contributions c "
        "JOIN accounts a ON a.id = c.account_id WHERE c.date >= ? GROUP BY a.kind",
        (tax_year_start(today).isoformat(),))
    return {row["kind"]: row["total"] for row in rows}


# ------------------------------------------------------------------
# Budget
# ------------------------------------------------------------------
def list_recurring():
    return query("SELECT * FROM recurring WHERE active = 1 ORDER BY kind DESC, amount DESC")


def add_recurring(name, kind, amount, frequency="monthly"):
    execute("INSERT INTO recurring (name, kind, amount, frequency) VALUES (?, ?, ?, ?)", (name, kind, amount, frequency))


def update_recurring(recurring_id, amount):
    execute("UPDATE recurring SET amount = ? WHERE id = ?", (amount, recurring_id))


def delete_recurring(recurring_id):
    execute("UPDATE recurring SET active = 0 WHERE id = ?", (recurring_id,))


def monthly_budget(recurring=None):
    """Regular income and costs converted to a per-month figure."""
    recurring = list_recurring() if recurring is None else recurring
    income = sum(r["amount"] * MONTHLY_FACTOR.get(r["frequency"], 1) for r in recurring if r["kind"] == "income")
    costs = sum(r["amount"] * MONTHLY_FACTOR.get(r["frequency"], 1) for r in recurring if r["kind"] == "expense")
    surplus = income - costs
    return {"income": income, "costs": costs, "surplus": surplus,
            "savings_rate": (surplus / income) if income > 0 else None}


def add_cashflow(kind, category, amount, note="", on=None):
    execute("INSERT INTO cashflows (date, kind, category, amount, note) VALUES (?, ?, ?, ?, ?)",
            (on or date.today().isoformat(), kind, category, amount, note))


def cashflows_for_month(year, month):
    prefix = f"{year:04d}-{month:02d}"
    return query("SELECT * FROM cashflows WHERE date LIKE ? ORDER BY date DESC", (prefix + "%",))


# ------------------------------------------------------------------
# Watchlist and paper trades
# ------------------------------------------------------------------
def list_watchlist(kind=None):
    if kind:
        return query("SELECT * FROM watchlist WHERE kind = ? ORDER BY added", (kind,))
    return query("SELECT * FROM watchlist ORDER BY added")


def add_to_watchlist(symbol, name="", kind="holding", note="", keywords=""):
    execute("INSERT OR REPLACE INTO watchlist (symbol, name, kind, note, keywords, added) VALUES (?, ?, ?, ?, ?, ?)",
            (symbol.upper().strip(), name, kind, note, keywords, time.time()))


def remove_from_watchlist(symbol):
    execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))


def list_paper_trades():
    return query("SELECT * FROM paper_trades ORDER BY date DESC")


def add_paper_trade(symbol, units, price_gbp, thesis, on=None):
    execute("INSERT INTO paper_trades (date, symbol, units, price_gbp, thesis) VALUES (?, ?, ?, ?, ?)",
            (on or date.today().isoformat(), symbol.upper().strip(), units, price_gbp, thesis))


def close_paper_trade(trade_id, close_price_gbp):
    execute("UPDATE paper_trades SET closed_date = ?, close_price_gbp = ? WHERE id = ?",
            (date.today().isoformat(), close_price_gbp, trade_id))


# ------------------------------------------------------------------
# Pure maths (no database)
# ------------------------------------------------------------------
def future_value(start, monthly, annual_rate_pct, years):
    """Compound growth with a fixed monthly payment.

    FV = P(1+i)^n + PMT * ((1+i)^n - 1) / i, with i the monthly rate and n the months.
    """
    months = int(round(years * 12))
    i = annual_rate_pct / 100 / 12
    if abs(i) < 1e-12:
        return start + monthly * months
    growth = (1 + i) ** months
    return start * growth + monthly * (growth - 1) / i


def months_between(start, end):
    """Whole months from one date to another (never negative)."""
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def payoff_plan(balance, target_date, today=None):
    """Monthly amount needed to clear an interest-free balance by a target date."""
    today = today or date.today()
    months = months_between(today, target_date)
    balance = abs(balance or 0)
    return {"months": months, "per_month": (balance / months) if months else balance}


def parse_date(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
