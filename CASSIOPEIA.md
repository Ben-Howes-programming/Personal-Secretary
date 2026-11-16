# Cassiopeia

The desktop app that replaces the Streamlit front end. Version 0.1.0, written 16 November 2026 by Claude Fable 5.2. This file is the user guide, the honest status report and the roadmap.

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
| The old dashboard (finance, health, university, inbox pages) | `streamlit run app.py`. Both use the same database |
| Run the tests | `python -m pytest tests -q` (35 tests, about 10 seconds, no network) |

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
| Today | Greeting, latest briefing, seven-day schedule from every connected calendar plus events Cassiopeia planned, tasks, weather for Bath, headlines with each source's lean, screen time if enabled |
| Talk | Chat with five modes (Cassiopeia, Planner, Scholar, Analyst, Scout). It can remember things, plan events, add tasks, text or email you, run protocols, search your vault, read a web page and draft simulations. "Start talking" runs a hands-free voice conversation |
| Vault | Drag files in. They are filed as `vault/Area/Unit/Kind/` and indexed for search. Anything under Assessments is flagged so the assistant gives hints, not answers |
| Lab | Sandbox: describe a simulation, read the script, press Run, see the charts. Trading lab: three daily patterns tested on two years of prices, then followed forward with £10,000 of test money per pattern |
| Control | Protocols, message channels with a test button, what it remembers, job schedule, API budget, self-update |

Scheduled jobs (while Cassiopeia is running): morning briefing 07:30, evening summary 21:30, overnight lab 02:15. Change the first two in `.env`. A job missed while the Mac slept runs on wake if it is still within a few hours.

## 4. Protocols, smart home and the HomePod

Say or type "Initiate focus protocol". Presets live in `cassiopeia/protocols.json`.

Cassiopeia cannot see your Home devices. It reaches them through Apple's Shortcuts app:

1. In Shortcuts, create a shortcut named exactly `Cassiopeia Focus`. Add the actions you want: set a Home scene, turn on a Focus mode, play a playlist.
2. Do the same for `Cassiopeia Movie` and `Cassiopeia Wind Down`.
3. Replace the `[link to your ambient sound or playlist]` placeholder in `protocols.json`, or delete that step.

Lights and a TV only respond if they are in the Home app. Until a shortcut exists the step reports "did not run" and the others carry on.

HomePod direction (not built): a Siri shortcut on the HomePod can call Cassiopeia, but the server listens on this Mac only. Opening it to your home network needs a login token first. That is roadmap item 4.

## 5. Honest status

Tested on Linux (Python 3.13, headless Chrome): the 34 logic tests, every page rendered and screenshotted, server security checks, sandbox runs, backtest maths.

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
| 1 | First run on the Mac and fix what breaks | Start with `python -m cassiopeia`, then voice, then one "Send test" |
| 2 | Port the remaining classic pages (finance, health, university, inbox, placements) into the window | The data layer already exists in `database/` and `services/`. Only the pages need rebuilding in `cassiopeia/web/` |
| 3 | Event-triggered workflows | A rule table: when X happens (new email from a .ac.uk address, deadline within 48 hours, price move over a threshold) do Y. The scheduler already ticks every 30 seconds |
| 4 | Token login, then HomePod and phone access on the home network | Do not open the server beyond this Mac before this exists |
| 5 | Agents that carry out multi-step jobs | Placement scan, weekly review, study planner. Reuse `brain.AGENTS` and add a step loop with a hard step limit |
| 6 | Web form filling | Needs a browser automation tool and a confirm-before-submit screen. Never store passwords in the database |
| 7 | Site blocking in Focus protocol | Needs administrator rights or a Focus-mode shortcut. Prefer the shortcut |
| 8 | Screen-time analysis | The tracker records minutes per app on the Mac. Apple gives no access to iPhone Screen Time |
| 9 | Camera and gesture awareness | Research first. On-device only, with a visible indicator when the camera is on |
| 10 | Real money | Only after months of paper results, with a regulated broker's official interface, a hard cash limit, and Ben's explicit decision. Not before |
