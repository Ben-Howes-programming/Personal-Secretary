"""
finance.py
==========
Purpose : Your accounts, investments, budget, ISA allowances and goals in one place.
Location: views/finance.py
Note    : You enter the balances, so nothing here is guessed. Everything on this
          page is general information to help you think, not personal financial advice.
"""

from datetime import date

import streamlit as st

import config
from database import finance
from services import market
from ui import state
from ui import theme as ui

KINDS = {"current": "Current account", "savings": "Savings", "investment": "Stocks and Shares ISA",
         "lisa": "Lifetime ISA", "overdraft": "Overdraft", "other": "Other"}

ui.header("Finance", "What you have, what you owe, and where it is heading.")

accounts = finance.list_accounts()
worth = finance.net_worth(accounts)
budget = finance.monthly_budget()
cash = sum(a["balance"] or 0 for a in accounts if a["kind"] in ("current", "savings"))
invested = sum(a["balance"] or 0 for a in accounts if a["kind"] in ("investment", "lisa"))

ui.kpis([
    ("net worth", ui.money(worth["net"]) if worth["has_data"] else "not set"),
    ("cash and savings", ui.money(cash) if worth["has_data"] else "not set"),
    ("invested", ui.money(invested) if worth["has_data"] else "not set"),
    ("owed", ui.money(worth["debts"]) if worth["has_data"] else "not set", "interest-free overdraft" if worth["debts"] else "", "neutral"),
    ("monthly surplus", ui.money(budget["surplus"]) if budget["income"] else "add income",
     f"{budget['savings_rate'] * 100:.0f}% of income" if budget["savings_rate"] is not None else "",
     "good" if budget["surplus"] > 0 else "bad"),
])
if not worth["has_data"]:
    ui.note("info", "Start on the Accounts tab: enter today's balance for each account. It takes two minutes and unlocks everything else.")

overview, accounts_tab, investments, budget_tab, goals = st.tabs(["Overview", "Accounts", "Investments", "Budget", "Allowances and goals"])

# ------------------------------------------------------------------
with overview:
    history = finance.net_worth_history()
    ui.section("Net worth over time")
    if len(history) >= 2:
        ui.line_chart([{"date": h["date"], "value": h["net_worth"]} for h in history], y_title="Net worth (£)", number_format=",.0f")
    else:
        ui.empty("One snapshot so far.", "Update your balances on another day and a trend line appears here.")

    ui.section("Where it sits")
    split = {}
    for account in accounts:
        if account["balance"] and not account["is_liability"]:
            split[KINDS.get(account["kind"], "Other")] = split.get(KINDS.get(account["kind"], "Other"), 0) + account["balance"]
    if split:
        ui.bar_chart([{"label": name, "value": value} for name, value in split.items()], y_title="Balance (£)", number_format=",.0f")
        total = sum(split.values())
        largest = max(split, key=split.get)
        ui.muted(f"{largest} holds {split[largest] / total * 100:.0f}% of your assets.")
    else:
        ui.empty("No balances yet.")

    rated = [a for a in accounts if a["kind"] == "savings" and a["balance"] and a["interest_rate"]]
    if rated:
        yearly = sum(a["balance"] * a["interest_rate"] / 100 for a in rated)
        ui.note("info", f"At today's rates your savings earn about {ui.money(yearly)} a year before tax. Rates change, so check them when you update balances.")

# ------------------------------------------------------------------
with accounts_tab:
    ui.section("Update balances")
    with st.form("balances"):
        on = st.date_input("Balances as of", value=date.today())
        inputs = {}
        for account in accounts:
            label_col, balance_col, rate_col = st.columns([2.2, 1.2, 1])
            label_col.markdown(f"**{account['name']}**  \n<span class='ps-muted'>{ui.esc(account['provider'] or '')}"
                               f"{', last updated ' + account['balance_date'] if account['balance_date'] else ''}</span>",
                               unsafe_allow_html=True)
            help_text = "Enter the amount owed as a positive number" if account["is_liability"] else None
            inputs[account["id"]] = (
                balance_col.number_input("Balance (£)", value=float(abs(account["balance"])) if account["balance"] is not None else None,
                                         step=10.0, key=f"bal_{account['id']}", help=help_text, placeholder="not set"),
                rate_col.number_input("Interest %", value=account["interest_rate"], step=0.05, key=f"rate_{account['id']}",
                                      placeholder="n/a"),
            )
        if ui.submit("Save balances", type="primary"):
            for account_id, (balance, rate) in inputs.items():
                if balance is not None:
                    finance.record_balance(account_id, balance, on.isoformat())
                finance.update_account(account_id, rate)
            st.toast("Balances saved")
            st.rerun()

    with st.expander("Add or remove an account"):
        with st.form("new_account", clear_on_submit=True):
            a, b, c = st.columns(3)
            name = a.text_input("Name")
            provider = b.text_input("Provider")
            kind = c.selectbox("Type", list(KINDS), format_func=KINDS.get)
            if ui.submit("Add account") and name.strip():
                finance.add_account(name.strip(), kind, provider.strip(), is_liability=(kind == "overdraft"))
                st.rerun()
        target = st.selectbox("Remove", [None] + accounts, format_func=lambda a: "Choose an account" if a is None else a["name"])
        if target and st.button("Remove this account", help="History is kept but the account is hidden"):
            finance.archive_account(target["id"])
            st.rerun()

# ------------------------------------------------------------------
with investments:
    holdings = finance.list_holdings()
    ui.section("Holdings")
    if holdings:
        histories = market.get_many([h["symbol"] for h in holdings] + [market.FX_SYMBOL])
        rate = market.gbpusd_rate()
        table, total_value, total_cost = [], 0.0, 0.0
        for holding in holdings:
            figures = market.summarise(histories[holding["symbol"]], rate)
            price = figures["price_gbp"]
            value = price * holding["units"] if price is not None else None
            cost = (holding["avg_cost"] or 0) * holding["units"]
            if value is not None:
                total_value += value
                total_cost += cost
            table.append({"Account": holding["account"], "Fund": holding["symbol"], "Units": holding["units"],
                          "Price (£)": round(price, 4) if price is not None else None,
                          "Value (£)": round(value, 2) if value is not None else None,
                          "Paid (£)": round(cost, 2),
                          "Gain (£)": round(value - cost, 2) if value is not None and cost else None,
                          "Gain %": round((value / cost - 1) * 100, 1) if value is not None and cost else None})
        ui.table(table)
        if total_cost:
            ui.kpis([("value now", ui.money(total_value)), ("paid in", ui.money(total_cost)),
                     ("gain", ui.money(total_value - total_cost), ui.pct((total_value / total_cost - 1) * 100),
                      ui.tone_of(total_value - total_cost))])
        ui.muted("Prices come from Yahoo Finance and can be delayed. Your provider's figure is the one that counts.")
        removable = st.selectbox("Remove a holding", [None] + holdings,
                                 format_func=lambda h: "Choose" if h is None else f"{h['symbol']} in {h['account']}")
        if removable and st.button("Remove holding"):
            finance.delete_holding(removable["id"])
            st.rerun()
    else:
        ui.empty("No holdings entered.", "Add the funds you own to see live value and gain.")

    investable = [a for a in accounts if a["kind"] in ("investment", "lisa", "other")]
    with st.form("new_holding", clear_on_submit=True):
        st.markdown("**Add a holding**")
        a, b, c, d = st.columns(4)
        account = a.selectbox("Account", investable, format_func=lambda x: x["name"])
        symbol = b.text_input("Yahoo symbol", placeholder="VWRP.L")
        units = c.number_input("Units", min_value=0.0, step=0.01, format="%.4f")
        avg_cost = d.number_input("Average price paid (£ per unit)", min_value=0.0, step=0.01, format="%.4f")
        if ui.submit("Add holding") and symbol.strip() and units > 0 and account:
            finance.add_holding(account["id"], symbol, units, avg_cost)
            st.rerun()

# ------------------------------------------------------------------
with budget_tab:
    recurring = finance.list_recurring()
    ui.section("Regular money in and out")
    with st.form("recurring"):
        edits = {}
        for item in recurring:
            name_col, amount_col = st.columns([3, 1])
            name_col.markdown(f"**{item['name']}**  \n<span class='ps-muted'>{item['kind']}, {item['frequency']}</span>",
                              unsafe_allow_html=True)
            edits[item["id"]] = amount_col.number_input("£", value=float(item["amount"] or 0), step=10.0, key=f"rec_{item['id']}",
                                                        label_visibility="collapsed")
        if ui.submit("Save amounts", type="primary"):
            for recurring_id, amount in edits.items():
                finance.update_recurring(recurring_id, amount)
            st.rerun()
    ui.kpis([("income a month", ui.money(budget["income"])), ("fixed costs a month", ui.money(budget["costs"])),
             ("left over", ui.money(budget["surplus"]), "", "good" if budget["surplus"] > 0 else "bad")])
    if budget["income"] and budget["costs"]:
        ui.muted(f"Rent is {config.RENT_PER_MONTH / budget['income'] * 100:.0f}% of your monthly income.")

    with st.expander("Add or remove a regular item"):
        with st.form("new_recurring", clear_on_submit=True):
            a, b, c, d = st.columns(4)
            name = a.text_input("Name", placeholder="Gym membership")
            kind = b.selectbox("Kind", ["expense", "income"])
            amount = c.number_input("Amount (£)", min_value=0.0, step=5.0)
            frequency = d.selectbox("How often", ["monthly", "weekly", "yearly"])
            if ui.submit("Add item") and name.strip():
                finance.add_recurring(name.strip(), kind, amount, frequency)
                st.rerun()
        gone = st.selectbox("Remove", [None] + recurring, format_func=lambda r: "Choose an item" if r is None else r["name"])
        if gone and st.button("Remove item"):
            finance.delete_recurring(gone["id"])
            st.rerun()

    ui.section("This month's one-off spending and income")
    with st.form("cashflow", clear_on_submit=True):
        a, b, c, d = st.columns([1, 1.5, 1, 2])
        flow_kind = a.selectbox("Kind", ["expense", "income"], key="flow_kind")
        category = b.text_input("Category", placeholder="Food, travel, tutoring")
        flow_amount = c.number_input("Amount (£)", min_value=0.0, step=1.0, key="flow_amount")
        flow_note = d.text_input("Note")
        if ui.submit("Log it") and flow_amount > 0:
            finance.add_cashflow(flow_kind, category.strip() or "Other", flow_amount, flow_note)
            st.rerun()
    flows = finance.cashflows_for_month(date.today().year, date.today().month)
    if flows:
        spent = sum(f["amount"] for f in flows if f["kind"] == "expense")
        earned = sum(f["amount"] for f in flows if f["kind"] == "income")
        ui.muted(f"Logged this month: {ui.money(spent)} spent, {ui.money(earned)} extra income.")
        ui.table([{"Date": f["date"], "Kind": f["kind"], "Category": f["category"], "Amount (£)": f["amount"], "Note": f["note"]}
                  for f in flows])

# ------------------------------------------------------------------
with goals:
    paid = finance.contributions_this_tax_year()
    lisa_paid = paid.get("lisa", 0)
    isa_paid = paid.get("investment", 0) + lisa_paid
    start = finance.tax_year_start()
    ui.section(f"ISA allowances, tax year from {start.strftime('%d %B %Y')}")
    ui.kpis([
        ("ISA allowance used", ui.money(isa_paid), f"{ui.money(max(0, config.ISA_ALLOWANCE - isa_paid))} left of {ui.money(config.ISA_ALLOWANCE)}"),
        ("Lifetime ISA paid in", ui.money(lisa_paid), f"{ui.money(max(0, config.LISA_ALLOWANCE - lisa_paid))} left of {ui.money(config.LISA_ALLOWANCE)}"),
        ("Lifetime ISA bonus earned", ui.money(lisa_paid * config.LISA_BONUS_RATE), "25% government bonus", "good"),
    ])
    ui.muted("The Lifetime ISA limit counts towards the overall ISA allowance. Withdrawing from a Lifetime ISA for anything other than "
             "a first home or after age 60 carries a 25% charge, which costs more than the bonus. Limits are set in config.py: "
             "check gov.uk each tax year.")
    isa_accounts = [a for a in accounts if a["kind"] in ("investment", "lisa")]
    with st.form("contribution", clear_on_submit=True):
        a, b, c = st.columns(3)
        into = a.selectbox("Paid into", isa_accounts, format_func=lambda x: x["name"])
        paid_amount = b.number_input("Amount (£)", min_value=0.0, step=25.0)
        paid_on = c.date_input("Date", value=date.today())
        if ui.submit("Record a payment in") and paid_amount > 0 and into:
            finance.add_contribution(into["id"], paid_amount, paid_on.isoformat())
            st.rerun()

    ui.section("Clearing the overdraft")
    overdraft = next((a for a in accounts if a["kind"] == "overdraft"), None)
    owed = abs(overdraft["balance"]) if overdraft and overdraft["balance"] else 0.0
    target = st.date_input("Clear it by", value=finance.parse_date(state.pref("overdraft_clear_by")) or date(2029, 7, 1),
                           help="Set this to when the interest-free period ends for you.")
    if target.isoformat() != state.pref("overdraft_clear_by"):
        state.set_pref("overdraft_clear_by", target.isoformat())
    if owed:
        plan = finance.payoff_plan(owed, target)
        ui.note("info", f"{ui.money(owed)} over {plan['months']} months is {ui.money(plan['per_month'], 2)} a month. "
                        "While it is interest-free, cash in a savings account earns more than clearing it early saves, "
                        "so the usual approach is to save the money and clear it in one go before the interest starts.")
    else:
        ui.empty("No overdraft balance entered.", "Enter it on the Accounts tab to see a payoff plan.")

    ui.section("What regular saving grows into")
    a, b, c, d = st.columns(4)
    lump = a.number_input("Starting amount (£)", min_value=0.0, value=float(max(0.0, invested)), step=100.0)
    monthly = b.number_input("Added each month (£)", min_value=0.0, value=float(max(0.0, round(budget["surplus"]))) if budget["income"] else 100.0, step=25.0)
    growth = c.number_input("Growth a year (%)", min_value=-10.0, max_value=20.0, value=5.0, step=0.5,
                            help="An assumption, not a forecast. Try 2%, 5% and 8% to see the range.")
    years = d.slider("Years", 1, 40, 10)
    st.latex(r"FV = P(1+i)^{n} + PMT\,\frac{(1+i)^{n}-1}{i}, \qquad i=\frac{r}{12},\; n=12\times\text{years}")
    final = finance.future_value(lump, monthly, growth, years)
    paid_in = lump + monthly * 12 * years
    ui.kpis([("after " + str(years) + " years", ui.money(final)), ("you paid in", ui.money(paid_in)),
             ("growth", ui.money(final - paid_in), "", ui.tone_of(final - paid_in))])
    curve = [{"date": date(date.today().year + year, date.today().month, 1).isoformat(), "series": name,
              "value": finance.future_value(lump, monthly, rate, year)}
             for year in range(0, years + 1) for name, rate in ((f"{growth:g}% a year", growth), ("0% (cash under the mattress)", 0.0))]
    ui.line_chart(curve, y_title="Value (£)", number_format=",.0f")
    ui.muted("Markets do not grow in a straight line. Real returns arrive unevenly, and inflation reduces what the final figure buys.")
