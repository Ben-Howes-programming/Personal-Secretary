# Cassiopeia

The desktop app that replaces the Streamlit front end. Version 0.3.0. Written 16 and 17 November 2026 by Claude Fable 5.2, extended 18 November by Claude Opus 5.5. This file is the user guide, the honest status report and the roadmap.

## 1. Start it

```bash
cd ~/Developer/personal-secretary
source .venv/bin/activate
python -m cassiopeia
```

A window opens (Chrome in app mode if Chrome is installed, otherwise your default browser). The address is `http://127.0.0.1:8765` and it only answers on this Mac.

| You want | Do this |
|---|---|
| Open it without the terminal | Double-click `Cassiopeia.command` in Finder. First time: run `chmod +x Cassiopeia.command` |
| Always running, starts at login | `bash scripts/install_cassiopeia.sh` once. It also adds a Cassiopeia app to `~/Applications` |
| Undo that | `bash scripts/uninstall_cassiopeia.sh` |
| The old dashboard | `streamlit run app.py`. No longer needed: every page and the Google connection now live in Cassiopeia. Both use the same database |
| Run the tests | `python -m pytest tests -q` (53 tests, about 10 seconds, no network) |

No new packages are required. Optional: `pip install pypdf` to search inside PDFs, `pip install pywebview` for a native window without Chrome.

## 2. Switch on messages to yourself

All off by default. Edit `.env`, then restart Cassiopeia.

| Setting | What it does | First use |
|---|---|---|
| `OWNER_PHONE` | Your number. Already set | |
| `ENABLE_IMESSAGE=true` | Texts you through the Messages app on this Mac | macOS asks once to let Python control Messages. Allow it. Press "Send test" in Control |
| `ENABLE_EMAIL_TO_SELF=true` | Emails your own Gmail address | Delete `token.json`, reconnect Google from the classic dashboard, accept the new "send email" permission |
| `ENABLE_ACTIVITY_TRACKING=true` | Counts minutes per front app for the screen-time panel | macOS asks to let Python use System Events |
| `MONTHLY_API_BUDGET_GBP=10` | Pauses the API-key route for the month once reached | Nothing |

Cassiopeia cannot message anyone but you. `cassiopeia/notify.py` has no recipient argument.

## 3. What each section does

| Section | What works now |
|---|---|
| Today, Overview | Greeting, latest briefing, seven-day schedule from every connected calendar plus events Cassiopeia planned, tasks, weather for Bath, headlines with each source's lean, screen time if enabled |
| Today, Calendar | Week grid from 07:00 to 23:00 across all calendars, overlapping events side by side, a free-time finder, and a form to plan events. Planned events stay in Cassiopeia. Google Calendar is never changed |
| Today, Inbox | "Check for new mail" is free: rules sort it and Claude is not called. Claude reads an email only when you press Analyse or Draft a reply. Drafts are edited here and never sent. "Needs action" shows only the last 21 days. "Catch up" fetches up to 75 days of missed mail for free, and "Mark older than 30 days done" clears old clutter. Flags set by the old version 0.5 app are ignored |
| Today, Money | Accounts and balances you enter, net worth with its trend, ISA and Lifetime ISA allowances, monthly budget, overdraft payoff plan. Nothing is invented: an account with no balance shows "not set" |
| Today, Markets | Your funds rebased to 100 over 1, 3, 6 or 12 months, price, day, month and year change, volatility, the study list, market trackers with what each one tells you, headlines matching each fund, paper trades with a written reason, and a Claude study note per fund on request |
| Today, Placements | Every opportunity with status, deadline and days left, notes per application. Researching or drafting with 14 days or less left opens automatically |
| Today, Tutoring | Free lesson slots on the next two Sundays from your calendar, ready to paste, and enquiries filed as Tutoring |
| Today, Health | Sleep, strength, runs and protein this week, plain-English observations, a weekly training plan timed around your calendar and finishing two hours before bed, logging for sleep, sessions, lifts and body, next lift targets. "Add timed sessions to my calendar" copies the plan into Cassiopeia's calendar |
| Today, University | Each module against the 75% target with the average needed on unmarked work, open assessments, the spaced lecture review queue, study time |
| Talk | Chat with five modes (Cassiopeia, Planner, Scholar, Analyst, Scout). It can remember things, plan events, add tasks, text or email you, run protocols, search your vault, read a web page and draft simulations. "Start talking" runs a hands-free voice conversation |
| Vault | Drag files in. They are filed as `vault/Area/Unit/Kind/` and indexed for search. Anything under Assessments is flagged so the assistant gives hints, not answers |
| Lab | Sandbox: describe a simulation, read the script, press Run, see the charts. Trading lab: three daily patterns tested on two years of prices, then followed forward with £10,000 of test money per pattern |
| Control | Protocols, Google connection with a Connect button, phone and HomePod access, message channels with a test button, triggers and your own rules, what it remembers, job schedule, API budget, self-update |

Scheduled jobs (while Cassiopeia is running): morning briefing 07:30, evening summary 21:30, overnight lab 02:15, a free mail check every 30 minutes, and the triggers every 5 minutes.

Triggers tell you things without being asked: a task or assessment due today or tomorrow, an urgent email, an event starting in about 30 minutes, a placement still being researched or drafted that closes within 7 days, and a fund you hold moving more than 3% in a day. Each is announced once, as a Mac notification plus a text if texting is on. Nothing is sent during quiet hours (23:30 to 07:00, from `BEDTIME_TARGET`). Deadlines and emails found overnight are announced at 07:00. Switch each one on or off in Control.

Your own rules (Control, "Your own rules"): pick a measurement, above or below, and a threshold. Measurements: a symbol's daily change in %, a symbol's price in £, 7-day average sleep, open tasks, recent emails needing action, days until a placement deadline. Examples to try:

| Name | Measurement | Subject | Rule |
| --- | --- | --- | --- |
| World fund dip | Daily change | VWRP.L | below -2 |
| Quantum fund jump | Daily change | WQTM.L | above 5 |
| Sleep slipping | 7-day average sleep | | below 7 |
| Task pile-up | Open tasks | | above 12 |
| ESA final week | Days until a placement deadline | ESA | below 7 |

A rule fires at most once a day and never during quiet hours. An email counts as urgent when Claude rated it high priority and needing action, or, if Claude has not read it, when the subject contains words such as "urgent", "deadline" or "interview".

Briefing times: Change the first two in `.env`. A job missed while the Mac slept runs on wake if it is still within a few hours.

## 4. Protocols, smart home and the HomePod

Say or type "Initiate focus protocol". Presets live in `cassiopeia/protocols.json`.

Cassiopeia cannot see your Home devices. It reaches them through Apple's Shortcuts app:

1. In Shortcuts, create a shortcut named exactly `Cassiopeia Focus`. Add the actions you want: set a Home scene, turn on a Focus mode, play a playlist.
2. Do the same for `Cassiopeia Movie` and `Cassiopeia Wind Down`.
3. Replace the `[link to your ambient sound or playlist]` placeholder in `protocols.json`, or delete that step.

Lights and a TV only respond if they are in the Home app. Until a shortcut exists the step reports "did not run" and the others carry on.

### Phone and HomePod (switched on 18 November)

`ENABLE_LAN_ACCESS=true` in `.env` lets devices on your home Wi-Fi reach Cassiopeia, but only with the access token. Find the address and token in Control, under Phone and HomePod. macOS may ask once whether Python may accept incoming connections: allow it.

Phone: open the address in Safari, enter the token once, then Share, Add to Home Screen. It opens like an app.

Siri on the HomePod or iPhone (one-time setup in the Shortcuts app on your iPhone):

1. New shortcut, named "Ask Cassiopeia". Siri runs it when you say that name.
2. Add "Ask for Input" (Text), prompt "What do you need?".
3. Add "Get Contents of URL": URL `http://[address from Control]/api/siri`, Method POST, Headers `Authorization` = `Bearer [token from Control]`, Request Body JSON with key `text` = Provided Input.
4. Add "Get Dictionary Value" for key `reply`, then "Speak Text" with it.
5. In the shortcut settings, allow it on HomePod (Personal Requests must be on in the Home app).

Saying "Hey Siri, Ask Cassiopeia" then "Initiate focus protocol" runs the protocol on the Mac. Protocol steps that are Shortcuts run on the Mac.

Limits: the connection is plain HTTP, so use it on home Wi-Fi only, never on public networks. Self-update, running simulations, connecting Google and deleting vault files stay on the Mac whatever the token. Ten wrong tokens lock an address out for ten minutes. "Make a new one" in Control replaces the token everywhere. To switch it all off, set `ENABLE_LAN_ACCESS=false` and restart.

## 5. Honest status

Tested on Linux (Python 3.13, headless Chrome): all 53 tests, every page and tab rendered and screenshotted, server security checks, sandbox runs, backtest maths.

Not tested, because it needs your Mac. Expect first-run fixes:

| Item | Risk |
|---|---|
| Voice conversation | Uses the browser's speech recognition. Works in Chrome and Safari. Chrome sends audio to Google to transcribe it |
| iMessage, notifications, protocols, activity tracking | AppleScript and the `shortcuts` command. Each needs a one-time macOS permission |
| Login item and app icon | Standard launchd setup, never run. Background programs cannot read Desktop, Documents or Downloads without extra permission, which is why the project lives in `~/Developer` |
| Self-update | Drives the Claude Code command line with flags in `config.SELF_UPDATE_CLI_ARGS`. Check them with `claude --help` |
| Live data | Yahoo prices, Open-Meteo weather, Google Calendar and Claude were replaced by stand-ins in the tests |
| Email to yourself | Needs a new Google permission. Follows Google's documented call, unverified against your account |

## 6. Trading lab: read this before trusting a number

Nine rules are tested every night on two years of prices for your funds and the study list. "What each rule tests" on the Lab page explains each one. Rules: buy at the close and sell at the open; the reverse; buy and hold (the benchmark); hold above the 50-day average; 20-day average above the 100-day; price above six months ago; buy after a fall of more than 2%; buy after three falling days; hold only around the turn of the month. Every rule decides using prices up to the previous close only, and a test checks that no rule can see the future. Cash earns nothing in the model, which slightly flatters buy and hold.

- Test money only. There is no broker connection and no code path that could place an order.
- "Buy at the close, sell at the open" and similar patterns are well known. After costs they rarely beat holding. The lab subtracts `LAB_COST_BPS` (10, meaning 0.1% per round trip). That figure is an assumption. Replace it with your broker's real spread and fees.
- The backtest column looks backwards and is easy to fool yourself with. The paper account column only counts days after the pattern was fixed. Judge by that column, after at least a few months.
- General information, not personal financial advice.

## 7. Safety rules built in

1. Local only: `127.0.0.1`, host check, and a required header on every change.
2. Messages go to you alone.
3. Web pages and files are data. After the assistant reads a web page, its next reply cannot save, plan or send anything.
4. Simulations never run until you press Run. They get 30 seconds, an empty folder and no API keys.
5. Self-update works on a separate branch and folder, refuses changes to secrets, and cannot be merged if tests fail.
6. The API-key route pauses at the monthly cap. The Claude plan route is not counted.

## 8. Roadmap, in order

| # | Item | Notes |
|---|---|---|
| Done | First run on the Mac, all pages ported, Connect Google, placement and price triggers, your own rules, token login with phone and Siri access | 18 November |
| 1 | Fix what the first run of 0.3 turns up | Check the four new tabs, the Siri shortcut and one text |
| 2 | HTTPS for home access, so the token is not sent in the clear | A self-signed certificate, trusted once on the phone | Calendar, inbox, money and university are done. The data layer exists in `database/` and `services/`. Add a function to `cassiopeia/pages.py`, a route in `server.py`, a tab in `web/` |
| 3 | Event suggestions | The morning briefing already names a fund to read about from the biggest one-month moves. Next: events from Bath university and society calendars if they publish iCal feeds |
| 4 | Retire the Streamlit app | Delete `views/`, `ui/`, `app.py` once nothing is missed |
| 5 | Agents that carry out multi-step jobs | Placement scan, weekly review, study planner. Reuse `brain.AGENTS` and add a step loop with a hard step limit |
| 6 | Web form filling | Needs a browser automation tool and a confirm-before-submit screen. Never store passwords in the database |
| 7 | Site blocking in Focus protocol | Needs administrator rights or a Focus-mode shortcut. Prefer the shortcut |
| 8 | Screen-time analysis | The tracker records minutes per app on the Mac. Apple gives no access to iPhone Screen Time |
| 9 | Camera and gesture awareness | Research first. On-device only, with a visible indicator when the camera is on |
| 10 | Real money | Only after months of paper results, with a regulated broker's official interface, a hard cash limit, and Ben's explicit decision. Not before |
