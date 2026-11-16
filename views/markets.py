"""
markets.py
==========
Purpose : Track your funds, follow the wider market, read the news that affects
          them, test ideas with pretend money, and learn the vocabulary.
Location: views/markets.py
Note    : Nothing here is a recommendation. The study list exists to teach concepts,
          and the lab uses pretend money. General information, not financial advice.
"""

from datetime import datetime

import streamlit as st

import config
from ai import claude
from database import finance
from services import market, news
from ui import theme as ui

PERIODS = {"1 month": 22, "3 months": 66, "6 months": 130, "1 year": 253, "2 years": 520}

ui.header("Markets", "Your funds, the wider picture, and a place to practise.")

watch = finance.list_watchlist()
mine = [w for w in watch if w["kind"] == "holding"]
study = [w for w in watch if w["kind"] == "research"]
histories = market.get_many([w["symbol"] for w in watch] + [t[0] for t in config.MARKET_TRACKERS] + [market.FX_SYMBOL])
rate = market.gbpusd_rate()
problems = sorted({h["error"] for h in histories.values() if h.get("error")})
if problems:
    ui.note("warn", "Some prices could not be refreshed: " + "; ".join(problems[:2]))


def figures_for(item):
    return market.summarise(histories[item["symbol"]], rate, item.get("currency"))


def price_text(figures):
    if not figures["ok"]:
        return "no data"
    if figures["price_gbp"] is not None:
        return ui.money(figures["price_gbp"], 2)
    return f"{figures['price']:,.2f} {figures['currency'] or ''}".strip()


funds, trackers, lab, headlines, learn = st.tabs(["Your funds", "Market trackers", "Research lab", "News", "Learn"])

# ------------------------------------------------------------------
with funds:
    if not mine:
        ui.empty("Your watchlist is empty.", "Add a fund below.")
    else:
        ui.kpis([(w["symbol"].replace(".L", ""), price_text(f), f"{ui.pct(f['day'])} today" if f["ok"] else "", ui.tone_of(f["day"]))
                 for w, f in ((w, figures_for(w)) for w in mine)])
        period_col, pick_col = st.columns([1, 2])
        period = period_col.segmented_control("Period", list(PERIODS), default="6 months", key="fund_period") or "6 months"
        symbols = [w["symbol"] for w in mine]
        chosen = pick_col.multiselect("Compare", symbols, default=symbols, key="fund_pick")
        ui.section("Growth of £100")
        ui.line_chart(market.indexed({s: histories[s] for s in chosen}, PERIODS[period]), y_title="Indexed to 100",
                      order=symbols, number_format=",.1f")
        ui.muted("Each line starts at 100, so you compare growth rather than price. A fund priced at £3 is not cheaper than one at £100.")

        ui.section("The numbers")
        ui.table([{"Fund": w["name"] or w["symbol"], "Symbol": w["symbol"], "Price": price_text(f),
                   "1 month %": f["month"], "This year %": f["ytd"], "1 year %": f["year"],
                   "Volatility %": f["volatility"], "Worst fall %": f["drawdown"], "As of": f["as_of"]}
                  for w, f in ((w, figures_for(w)) for w in mine)],
                 column_config={name: st.column_config.NumberColumn(format="%.1f")
                                for name in ("1 month %", "This year %", "1 year %", "Volatility %", "Worst fall %")})
        ui.muted("Volatility is how much the price swings in a typical year. Worst fall is the largest drop from a peak in the last year. "
                 "Funds launched recently show blanks until they have enough history.")

    with st.expander("Add or remove a fund"):
        with st.form("add_symbol", clear_on_submit=True):
            a, b, c = st.columns([1, 2, 2])
            symbol = a.text_input("Yahoo symbol", placeholder="VUAG.L", help="London listings end in .L. Search the fund on finance.yahoo.com to find it.")
            name = b.text_input("Name")
            keywords = c.text_input("News keywords, comma separated", placeholder="s&p 500, wall street")
            if ui.submit("Add to your funds") and symbol.strip():
                finance.add_to_watchlist(symbol, name.strip(), "holding", keywords=keywords)
                st.rerun()
        gone = st.selectbox("Remove", [None] + watch, format_func=lambda w: "Choose a symbol" if w is None else f"{w['symbol']} ({w['kind']})")
        if gone and st.button("Remove from the list"):
            finance.remove_from_watchlist(gone["symbol"])
            st.rerun()

# ------------------------------------------------------------------
with trackers:
    ui.muted("A small set of instruments worth being able to read. Each has one line on what it tells you.")
    for symbol, name, meaning in config.MARKET_TRACKERS:
        figures = market.summarise(histories[symbol], rate)
        value = f"{figures['price']:,.2f}" if figures["ok"] else "no data"
        moves = f"{ui.pct(figures['day'])} today, {ui.pct(figures['month'])} in a month" if figures["ok"] else ""
        ui.rows([ui.row(f"{name}: {value}", meaning, moves, tone=ui.tone_of(figures["day"]) if figures["ok"] else None)])
    ui.section("Compare trackers")
    names = {symbol: name for symbol, name, _meaning in config.MARKET_TRACKERS}
    picked = st.multiselect("Show", list(names), default=["^FTSE", "^GSPC"], format_func=names.get, key="tracker_pick")
    rows = market.indexed({symbol: histories[symbol] for symbol in picked}, 253)
    for row in rows:
        row["series"] = names[row["series"]]
    ui.line_chart(rows, y_title="Indexed to 100, one year", order=[names[s] for s in names], number_format=",.1f")

# ------------------------------------------------------------------
with lab:
    ui.note("info", "A study list and a pretend-money portfolio. The aim is to form a view, write it down, and check it against what happens. "
                    "Nothing here is a suggestion to buy.")
    ui.section("Study list")
    for item in study:
        figures = figures_for(item)
        moves = f"{ui.pct(figures['year'])} in a year, volatility {figures['volatility']:.0f}%" if figures["ok"] and figures["volatility"] and figures["year"] is not None else ""
        ui.rows([ui.row(f"{item['name']} ({item['symbol']})", f"Why study it: {item['note']}", moves)])
    study_pick = st.selectbox("Write a study note on", [None] + study + mine,
                              format_func=lambda w: "Choose an instrument" if w is None else f"{w['name'] or w['symbol']} ({w['symbol']})")
    if study_pick and st.button("Write the study note", help="Uses Claude once, then the note is reused for a week"):
        figures = figures_for(study_pick)
        facts = (f"1 year {ui.pct(figures['year'])}, volatility {figures['volatility'] or 0:.0f}%, worst fall {ui.pct(figures['drawdown'])}"
                 if figures["ok"] else "no price data available")
        try:
            with st.spinner("Writing"):
                st.session_state["study_note"] = (study_pick["symbol"], claude.ticker_brief(study_pick["symbol"], study_pick["name"], facts))
        except claude.AIError as error:
            st.error(str(error))
    if st.session_state.get("study_note"):
        st.markdown(f"**{st.session_state['study_note'][0]}**")
        st.markdown(st.session_state["study_note"][1])

    with st.form("add_study", clear_on_submit=True):
        a, b, c = st.columns([1, 2, 3])
        symbol = a.text_input("Yahoo symbol", key="study_symbol")
        name = b.text_input("Name", key="study_name")
        why = c.text_input("What do you want to learn from it?")
        if ui.submit("Add to the study list") and symbol.strip():
            finance.add_to_watchlist(symbol, name.strip(), "research", note=why)
            st.rerun()

    ui.section("Pretend-money portfolio")
    trades = finance.list_paper_trades()
    benchmark = histories.get("VWRP.L", {}).get("closes") or []
    if trades:
        table = []
        for trade in trades:
            history = histories.get(trade["symbol"]) or market.get_history(trade["symbol"])
            now_price = market.summarise(history, rate)["price_gbp"]
            end_price = trade["close_price_gbp"] or now_price
            gain = (end_price / trade["price_gbp"] - 1) * 100 if end_price and trade["price_gbp"] else None
            start_level = market._close_on_or_before(benchmark, trade["date"])
            end_level = market._close_on_or_before(benchmark, trade["closed_date"] or "9999")
            versus = (end_level / start_level - 1) * 100 if start_level and end_level else None
            table.append({"Opened": trade["date"], "Symbol": trade["symbol"], "Units": trade["units"],
                          "Bought at (£)": trade["price_gbp"], "Now (£)": round(end_price, 4) if end_price else None,
                          "Return %": round(gain, 1) if gain is not None else None,
                          "All-World over the same time %": round(versus, 1) if versus is not None else None,
                          "Your reasoning": trade["thesis"], "Status": "closed" if trade["closed_date"] else "open"})
        ui.table(table)
        ui.muted("The comparison column is the test: an idea only added something if it beat simply holding the global fund.")
        open_trades = [t for t in trades if not t["closed_date"]]
        closing = st.selectbox("Close a pretend trade", [None] + open_trades,
                               format_func=lambda t: "Choose" if t is None else f"{t['symbol']} opened {t['date']}")
        if closing and st.button("Close at today's price"):
            history = histories.get(closing["symbol"]) or market.get_history(closing["symbol"])
            price = market.summarise(history, rate)["price_gbp"]
            if price:
                finance.close_paper_trade(closing["id"], price)
                st.rerun()
            else:
                st.error("No current price for that symbol.")
    else:
        ui.empty("No pretend trades yet.", "Log one below with your reasoning, then come back in a month.")
    with st.form("paper_trade", clear_on_submit=True):
        a, b, c = st.columns([1, 1, 3])
        candidates = [w["symbol"] for w in watch]
        trade_symbol = a.selectbox("Symbol", candidates) if candidates else a.text_input("Symbol")
        amount = b.number_input("Pretend amount (£)", min_value=0.0, value=500.0, step=50.0)
        thesis = c.text_input("Why do you expect this to do well? What would prove you wrong?")
        if ui.submit("Log pretend trade") and trade_symbol and amount > 0:
            price = market.summarise(histories.get(trade_symbol) or market.get_history(trade_symbol), rate)["price_gbp"]
            if not price:
                st.error("No current price in pounds for that symbol, so the trade was not logged.")
            elif not thesis.strip():
                st.error("Write your reasoning first. That is the point of the exercise.")
            else:
                finance.add_paper_trade(trade_symbol, amount / price, price, thesis.strip())
                st.rerun()

# ------------------------------------------------------------------
with headlines:
    sources = st.pills("Sources", ["FT", "BBC", "Guardian"], selection_mode="multi", default=["FT", "BBC", "Guardian"], key="news_sources")
    items = news.get_news(sources or None)
    if not items:
        ui.empty("No headlines loaded.", "Check your internet connection, then press Refresh data in the sidebar.")

    def show(entries):
        for item in entries:
            when = datetime.fromtimestamp(item["published_ts"]).strftime("%d %b %H:%M") if item.get("published_ts") else ""
            st.markdown(f"[{item['title']}]({item['link']})  \n<span class='ps-muted'>{ui.esc(item['source'])} {ui.esc(item['section'])}, "
                        f"{ui.esc(item['lean'])}. {when}</span>", unsafe_allow_html=True)

    ui.section("Touching your funds")
    any_match = False
    for fund in mine:
        hits = news.matching(items, (fund.get("keywords") or "").split(","))[:4]
        if hits:
            any_match = True
            st.markdown(f"**{fund['symbol'].replace('.L', '')}**")
            show(hits)
    if not any_match:
        ui.empty("No headline matches your fund keywords right now.", "Edit keywords by re-adding a fund with new ones.")

    ui.section("Latest")
    if items and st.button("Summarise these headlines", help="Uses Claude's cheapest model once per set of headlines"):
        try:
            with st.spinner("Summarising"):
                st.session_state["digest"] = claude.news_digest([f"{i['source']}: {i['title']}" for i in items[:40]])
        except claude.AIError as error:
            st.error(str(error))
    if st.session_state.get("digest"):
        ui.note("info", "Summary of headlines only. Read the articles before drawing conclusions.")
        st.markdown(st.session_state["digest"])
    show(items[:30])
    ui.muted("Headlines open on the publisher's site, where your FT subscription applies. "
             "Add your personal myFT feed in .env (MYFT_RSS_URL) to see the topics you follow.")

# ------------------------------------------------------------------
with learn:
    ui.muted("Worked through in order, these take you from the basics to reading a fund factsheet.")
    lessons = [
        ("Shares, funds and ETFs", "A share is a slice of one company. A fund pools money to hold many. An ETF is a fund that trades on an exchange like a share. VWRP holds thousands of companies in one purchase.", None),
        ("Accumulating and distributing", "An accumulating fund (Acc) reinvests dividends for you. A distributing fund (Dist) pays them out as cash. Inside an ISA neither is taxed, and Acc saves you reinvesting by hand.", None),
        ("Costs: the ongoing charge", "The OCF or TER is the yearly fee taken from the fund. 0.5% against 0.07% looks small, but it compounds.", r"V_n = V_0\,(1 + r - c)^n"),
        ("Return", "The percentage change in value over a period. Compare returns over the same period, never across different ones.", r"R = \frac{P_1}{P_0} - 1"),
        ("Volatility", "The standard deviation of returns: how widely results scatter around the average. Daily volatility scales to yearly with the square root of the number of trading days, the same way a random walk spreads.", r"\sigma_{\text{year}} = \sigma_{\text{day}}\sqrt{252}"),
        ("Drawdown", "The fall from a previous peak. A 50% fall needs a 100% rise to recover, which is why large losses matter more than large gains.", r"D = \frac{P_{\text{now}}}{P_{\text{peak}}} - 1"),
        ("Diversification", "Holding assets that do not move together lowers the swings of the whole. One sector fund, such as quantum computing, carries far more risk than a global fund.", r"\sigma_p^2 = w_1^2\sigma_1^2 + w_2^2\sigma_2^2 + 2w_1w_2\rho\,\sigma_1\sigma_2"),
        ("Bonds and yields", "A bond pays fixed interest. When market interest rates rise, existing bonds are worth less, so price and yield move in opposite directions.", None),
        ("Currency risk", "Your global funds hold mostly dollar assets. If the pound falls against the dollar, their value in pounds rises, and the reverse.", None),
        ("Pound-cost averaging", "Investing a fixed sum every month buys more units when prices are low and fewer when high. It removes the temptation to time the market.", None),
        ("Valuation: price to earnings", "Share price divided by yearly profit per share. A high figure means investors are paying for expected growth, which may or may not arrive.", r"\text{P/E} = \frac{\text{price per share}}{\text{earnings per share}}"),
        ("Real returns", "What matters is growth after inflation. 5% growth with 3% inflation buys you about 2% more.", r"r_{\text{real}} \approx r_{\text{nominal}} - \pi"),
    ]
    for number, (title, body, formula) in enumerate(lessons, start=1):
        with st.expander(f"{number}. {title}"):
            st.write(body)
            if formula:
                st.latex(formula)
