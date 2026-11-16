# Setup guide

Version 1.0 of the rebuilt Personal Secretary. Follow the parts in order. Parts 1 to 6 get the app running (about 15 minutes). Part 8 is optional extras you can add any time.

Project folder: `~/Desktop/Programming/personal-secretary`

---

## Part 1. Protect what you have (2 minutes)

Open the project folder in VS Code, then open the terminal with **Terminal > New Terminal**.

```bash
cd ~/Desktop/Programming/personal-secretary
git status
```

- If `git status` lists changed files, save them first:
  ```bash
  git add -A
  git commit -m "Checkpoint before v1.0 rebuild"
  ```
- Make a branch so the old app stays untouched on `main`:
  ```bash
  git checkout -b rebuild-v1
  ```

To go back to the old app at any point: `git checkout main`.

---

## Part 2. Put the new files in (3 minutes)

1. Unzip `personal-secretary-v1.zip` by double-clicking it in Downloads. You get a folder called `personal-secretary-v1`.
2. Merge it into your project with one command. `ditto` adds and overwrites files but never deletes anything, and it includes the hidden files that Finder would miss:
   ```bash
   ditto ~/Downloads/personal-secretary-v1 ~/Desktop/Programming/personal-secretary
   ```
3. Remove the old page folder if you have one, because pages now live in `views/`:
   ```bash
   git rm -r -q --ignore-unmatch pages
   rm -rf pages
   ```

Do not drag the folders across in Finder: Finder replaces whole folders instead of merging them, and it skips hidden files such as `.streamlit`.

These personal files are **not** in the zip and are left exactly as they are: `.env`, `credentials.json`, `token.json`, `secretary.db`, `.venv/`.

What changed, file by file:

| File or folder | Status |
|---|---|
| `app.py`, `config.py`, `requirements.txt`, `README.md`, `.gitignore` | Replaced |
| `ai/claude.py`, `database/database.py`, `services/gmail.py`, `services/calendar.py`, `services/google_auth.py` | Replaced |
| `database/health.py` | Replaced if you had one |
| `ai/context.py`, `ai/voice.py` | New |
| `database/finance.py`, `database/university.py`, `database/tasks.py` | New |
| `services/inbox.py`, `market.py`, `news.py`, `training.py`, `microsoft.py`, `apple.py` | New |
| `ui/` (theme, shared state, email card) | New |
| `views/` (one file per page, 12 pages) | New |
| `tests/`, `.streamlit/config.toml`, `.env.example`, `CLAUDE.md`, `SETUP_GUIDE.md` | New |
| `pages/` | Remove |

---

## Part 3. Install the packages (2 minutes)

```bash
cd ~/Desktop/Programming/personal-secretary
source .venv/bin/activate
pip install -r requirements.txt
```

Your prompt should start with `(.venv)`. The only package you did not already have is `yfinance` (market prices).

If there is no `.venv` folder: `python3 -m venv .venv` first, then the three lines above.

---

## Part 4. Connect Claude (5 minutes)

The app can reach Claude two ways. `AI_BACKEND=auto` in `.env` tries them in this order.

| Route | Cost | What you need |
|---|---|---|
| **A. Your Pro plan, through Claude Code** | Counts against your Pro usage limits, no extra bill | Claude Code installed and signed in |
| **B. API key** | Billed per token, separately from Pro | `ANTHROPIC_API_KEY` in `.env` (you already have this) |

A Pro subscription does not include API access, which is why route A goes through Claude Code. Anthropic's help page confirms that `claude -p`, the command this app runs, draws on your subscription when you are signed in with your plan: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan

**Route A setup**

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Open a **new** terminal window, then:

```bash
claude
```

Sign in with your Claude account when the browser opens, choose your Pro subscription, then type `/exit`. Check it works without a browser:

```bash
claude -p "Say hello in three words"
```

**Trade-off to know about.** Route A answers in one piece after a few seconds. Route B streams word by word and is faster for the batch email triage. If chat feels slow on route A, set `AI_BACKEND=api` in `.env`. If your Pro limits are tight during a heavy week, the same switch moves the app off your plan.

**Important:** if `ANTHROPIC_API_KEY` is set as a system-wide variable in your shell, Claude Code will bill the API instead of your plan. The app strips the key before calling Claude Code, so this only matters when you run `claude` yourself.

---

## Part 5. Run it

```bash
cd ~/Desktop/Programming/personal-secretary
source .venv/bin/activate
streamlit run app.py
```

The browser opens at `http://localhost:8501`. Stop the app with **Ctrl+C** in the terminal.

Optional check that the logic is healthy (uses a temporary database, never your real one):

```bash
pip install pytest
python -m pytest tests -q
```

Expected: `20 passed`.

---

## Part 6. First-run checklist (5 minutes)

Do these once, in this order.

1. **Settings > Connections.** Press **Test Claude**. Google should show Connected because your existing `token.json` still works. If not, press **Connect Google**.
2. **Inbox.** Press **Check mail now**. Your existing analysed emails are kept and reused.
3. **Finance > Accounts.** Enter today's balance and interest rate for each account. Rename or remove accounts that do not match.
4. **Finance > Budget.** Enter your income and bills. Rent is pre-filled at £750.
5. **Finance > Investments.** Add the units you hold of each fund.
6. **University > Modules.** Add each module's code and credits, then add deadlines on the Deadlines tab.
7. **Health > Log.** Enter last night's sleep and today's weight. Or import from Apple Health (Part 8).
8. **Settings > Preferences.** Set bedtime target, gym days and runs per week.

---

## Part 7. Commit and push

```bash
git status
```

Check that `.env`, `credentials.json`, `token.json` and `secretary.db` do **not** appear in the list. If `secretary.db` does appear, it was tracked before. Untrack it (the file stays on your Mac):

```bash
git rm --cached secretary.db
```

Then:

```bash
git add -A
git commit -m "Rebuild as v1.0: new UI, finance, markets, health, university, token caching"
git push -u origin rebuild-v1
```

When you are happy with it after a few days of use:

```bash
git checkout main
git merge rebuild-v1
git push
```

---

## Part 8. Optional extras

### 8.1 Let the app add calendar events and Gmail drafts

Both are off by default. The app can never send an email either way.

1. In `.env` set `ENABLE_CALENDAR_WRITE=true` and/or `ENABLE_GMAIL_DRAFTS=true`.
2. Delete `token.json`, restart the app, and press **Connect Google** in Settings.
3. If Google refuses the new permission, open your project in the Google Cloud console and add the scopes `calendar.events` and/or `gmail.compose` on the OAuth consent screen (Data access).

### 8.2 FT in the news feed

FT headlines from the public section feeds already appear, and links open on ft.com where your subscription applies. To add the topics you follow: on ft.com open **myFT**, find the RSS feed link for your feed, and paste it into `.env` as `MYFT_RSS_URL=...`. The FT does not offer subscribers an API for full article text, so the app shows headlines and summaries only.

### 8.3 Voice

- **Speaking replies** works now. Turn on **Read replies aloud** on the Assistant page.
- **Dictation with no install:** click the message box and press the microphone key (enable it under System Settings > Keyboard > Dictation).
- **Hands-free recording inside the app:** `pip install faster-whisper`, restart, and a record button appears on the Assistant page. Audio is transcribed on your Mac. This package may not yet support your Python version; if the install fails, use dictation.

### 8.4 Apple Health

Health page > **Apple Health** tab has the three steps. It reads sleep, workouts, weight, steps and resting heart rate from the export file. Repeat every week or two.

### 8.5 Outlook

1. `pip install msal`
2. Go to https://entra.microsoft.com > **App registrations** > **New registration**. Supported account types: "Accounts in any organizational directory and personal Microsoft accounts". No redirect address needed.
3. In the new app: **Authentication** > set **Allow public client flows** to Yes.
4. Copy the **Application (client) ID** into `.env` as `MS_CLIENT_ID=...`.
5. Restart the app. Settings > **Connect Outlook**, then follow the code shown.

Your Bath account may be blocked until the university's IT team approves the app. A personal outlook.com account works without approval.

### 8.6 iCloud mail and calendar

1. Create an app-specific password at https://account.apple.com (Sign-In and Security > App-Specific Passwords).
2. In `.env` set `ICLOUD_USER=you@icloud.com` and `ICLOUD_APP_PASSWORD=...`.
3. For the calendar as well: `pip install caldav`.

### 8.7 Cost estimates

`config.py` has an empty `PRICES_PER_MTOK`. Fill it from https://docs.claude.com pricing if you use the API route and want a dollar figure on the usage page.

---

## Part 9. If something goes wrong

| What you see | Fix |
|---|---|
| `ModuleNotFoundError` | The venv is not active. Run `source .venv/bin/activate`, then `pip install -r requirements.txt` |
| A page shows a red error box | Copy the last line of the error into a chat with Claude along with the page name |
| Claude: "not connected" | Settings > Connections shows which route is missing. Run `claude -p "hi"` in the terminal to test route A |
| Claude API error mentioning the model | Model names are at the top of `config.py` under `MODELS`. Check them against docs.claude.com |
| Markets show "no data" for a fund | Search the fund on finance.yahoo.com and use the exact symbol shown there. If the price looks 100 times too big or small, tell me the symbol and what Yahoo shows |
| Google sign-in loops | Delete `token.json` and press Connect Google again |
| Layout looks unstyled | Check `.streamlit/config.toml` was copied (it is a hidden folder: press **Cmd+Shift+.** in Finder to show it) |

---

## What has and has not been tested

| Area | Status |
|---|---|
| Database, upgrade of your old `secretary.db`, finance maths, training plan, free-slot finder, news parsing, price maths, email parsing, Apple Health import | Covered by 20 automated tests, all passing |
| Every page, top to bottom, with sample data and with every button pressed | Ran without errors against a stand-in for Streamlit |
| Custom visual components (header, figure strip, day ribbon, lists) | Rendered and checked in a browser |
| The full app in real Streamlit on your Mac | **Not tested.** Streamlit could not be installed where this was built, so the first run is yours. Expect the odd layout tweak |
| Live Google, Yahoo Finance and news feeds | **Not tested live.** The Google code keeps your existing calls. Yahoo symbols for VALL and WQTM are the London listings and should be confirmed on first load |
| `claude -p` flags | Checked against Claude Code 2.1.325. A live call from the app was not possible in the build environment |
| Outlook, iCloud mail and calendar | **Written from the documentation, not run against real accounts** |
