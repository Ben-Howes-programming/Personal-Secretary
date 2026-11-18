"""
server.py
=========
Purpose : The local web server behind the Cassiopeia window. Serves the page in
          cassiopeia/web/ and answers its requests with JSON.
Location: cassiopeia/server.py
Used by : cassiopeia/__main__.py
Safety  : Listens on 127.0.0.1 only. Requests must name localhost as the host, and every
          request that changes something must carry the X-Cassiopeia header, which a page
          on another website cannot add. Built on Python's standard library: no extra packages.
"""

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config
from ai import claude, voice
from cassiopeia import (access, accounts, brain, more_pages, briefing, events, lab, notify, pages, protocols, sandbox, scheduler, selfupdate,
                        store, triggers, vault, weather)
from database import database as db
from database import tasks, university
from services import calendar as cal

WEB = Path(__file__).with_name("web")
MAX_UPLOAD = 50 * 1024 * 1024          # 50 MB per file


class Problem(Exception):
    """An error with a message that is safe to show on screen."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------
# GET: reading. Each function takes the query dictionary and returns JSON-ready data.
# ------------------------------------------------------------------
def get_state(_q):
    week, errors = events.upcoming(7)
    spent = claude.month_cost_gbp()
    return {
        "app": config.APP_NAME, "owner": config.OWNER_NAME, "now": events.now().isoformat(),
        "events": [{"day": cal.event_day(e), "line": cal.describe_event(e), "source": e.get("source", "Calendar"),
                    "local_id": e.get("local_id")} for e in week[:16]],
        "calendar_errors": errors,
        "tasks": tasks.group_tasks(tasks.list_tasks()),
        "briefings": store.latest_briefings(2),
        "inbox_waiting": sum(1 for e in db.list_emails(120, include_done=False)
                             if pages.needs_action(e)),
        "ai": claude.backend_status(),
        "budget": {"spent_gbp": spent, "cap_gbp": config.MONTHLY_API_BUDGET_GBP, "over": claude.over_budget()},
        "jobs": store.jobs(),
        "schedule": {"morning briefing": config.MORNING_BRIEFING_AT, "evening summary": config.EVENING_SUMMARY_AT,
                     "overnight lab": config.OVERNIGHT_LAB_AT},
        "channels": {"text": config.ENABLE_IMESSAGE and bool(config.OWNER_PHONE), "email": config.ENABLE_EMAIL_TO_SELF,
                     "activity": config.ENABLE_ACTIVITY_TRACKING},
        "activity": scheduler.activity_today(), "outbox": store.outbox(6), "memories": store.memories(40),
        "agents": {key: {"label": a["label"], "about": a["about"]} for key, a in brain.AGENTS.items()},
        "protocols": {key: p.get("about", "") for key, p in protocols.load().items()},
    }


def get_headlines(_q):
    from services import news
    items = news.get_news()[:10]
    return [{"title": i["title"], "link": i["link"], "source": i.get("source", ""), "lean": i.get("lean", "")}
            for i in items]


def get_messages(q):
    return db.get_messages(int(q["id"])) if q.get("id") else []


def get_vault(q):
    if q.get("q"):
        return {"results": vault.search(q["q"], limit=12)}
    return {"files": vault.listing(), "areas": vault.AREAS, "kinds": vault.KINDS,
            "units": [m["name"] for m in university.list_modules()]}


GET = {
    "/api/ping": lambda q: {"app": "cassiopeia"},
    "/api/state": get_state,
    "/api/weather": lambda q: weather.get(),
    "/api/headlines": get_headlines,
    "/api/conversations": lambda q: db.list_conversations(12),
    "/api/messages": get_messages,
    "/api/vault": get_vault,
    "/api/lab": lambda q: lab.report(),
    "/api/sims": lambda q: sandbox.recent(),
    "/api/updates": lambda q: selfupdate.recent(),
    "/api/calendar": lambda q: pages.calendar(q.get("start"), q.get("days", 7)),
    "/api/inbox": lambda q: pages.inbox_list(q.get("show", "open")),
    "/api/triggers": lambda q: triggers.status(),
    "/api/money": lambda q: pages.money(),
    "/api/google": lambda q: accounts.google_status(),
    "/api/health": lambda q: more_pages.health_page(q.get("next") == "1"),
    "/api/markets": lambda q: more_pages.markets_page(int(q.get("days", 130))),
    "/api/placements": lambda q: more_pages.placements_page(),
    "/api/tutoring": lambda q: more_pages.tutoring_page(),
    "/api/university": lambda q: pages.university_page(),
}


# ------------------------------------------------------------------
# POST: doing. Each function takes (JSON body, query, raw bytes) and returns JSON-ready data.
# ------------------------------------------------------------------
def need(body, *names):
    missing = [n for n in names if not str(body.get(n, "")).strip()]
    if missing:
        raise Problem("Missing: " + ", ".join(missing))
    return [body[n] for n in names]


def siri(body):
    """For a Siri Shortcut on a HomePod or iPhone: text in, plain speakable text out."""
    from ai import voice
    text = str(body.get("text", "")).strip()
    if not text:
        raise Problem("Send JSON like {\"text\": \"what is on today\"}.")
    key = "cass_siri_conversation:" + events.now().date().isoformat()     # one running conversation per day
    result = brain.chat(text, db.get_setting(key), "cassiopeia")
    db.set_setting(key, result["conversation_id"])
    return {"reply": voice.plain_text(result["reply"])[:900], "actions": [a["detail"] for a in result["actions"]]}


def post_chat(body, q, raw):
    return brain.chat(body.get("text"), body.get("conversation_id"), body.get("agent") or "cassiopeia")


def post_upload(body, q, raw):
    if not raw:
        raise Problem("The file was empty.")
    return vault.save(q.get("name", "file"), raw, q.get("area"), q.get("unit"), q.get("kind"),
                      [m["name"] for m in university.list_modules()])


def post_event(body, q, raw):
    title, start = need(body, "title", "start")
    start = events.parse_when(start)
    if not start:
        raise Problem("Start must look like 2026-11-20T14:00.")
    return {"id": store.add_event(title, start, events.parse_when(body.get("end")), body.get("notes", ""))}


def post_task(body, q, raw):
    (title,) = need(body, "title")
    return {"id": tasks.add_task(title, priority=body.get("priority") or "Medium", due=body.get("due") or None)}


def post_test_message(body, q, raw):
    line = f"Test from {config.APP_NAME}. If you can read this, messages to you work."
    ok, detail = (notify.email_me("Test", line) if body.get("channel") == "email" else notify.text_me(line))
    return {"ok": ok, "detail": detail}


def post_transcribe(body, q, raw):
    text, error = voice.transcribe(raw)
    return {"text": text, "error": error}


def guarded(action):
    """Turn RuntimeError and ValueError from a module into a message for the screen."""
    def run(body, q, raw):
        try:
            return action(body)
        except (RuntimeError, ValueError, KeyError, claude.AIError) as problem:
            raise Problem(str(problem))
    return run


POST = {
    "/api/chat": post_chat,
    "/api/briefing": lambda b, q, r: briefing.deliver(b.get("kind") if b.get("kind") in ("morning", "evening") else "morning",
                                                      send=bool(b.get("send"))),
    "/api/vault/upload": post_upload,
    "/api/vault/remove": lambda b, q, r: {"ok": vault.remove(int(b["id"]))},
    "/api/events": post_event,
    "/api/events/remove": lambda b, q, r: {"ok": store.delete_event(int(b["id"])) is None},
    "/api/tasks": post_task,
    "/api/tasks/done": lambda b, q, r: {"ok": tasks.complete_task(int(b["id"])) is None},
    "/api/memories": lambda b, q, r: {"id": store.remember(b.get("text"))},
    "/api/memories/forget": lambda b, q, r: {"ok": store.forget(int(b["id"])) is None},
    "/api/protocols/run": lambda b, q, r: protocols.run(str(b.get("name", "")).lower()),
    "/api/lab/run": lambda b, q, r: {"summary": lab.run_overnight()},
    "/api/sims/draft": guarded(lambda b: sandbox.draft(need(b, "prompt")[0])),
    "/api/sims/run": lambda b, q, r: sandbox.run(int(b["id"])),
    "/api/updates/propose": guarded(lambda b: selfupdate.propose(b.get("instruction"))),
    "/api/updates/approve": guarded(lambda b: selfupdate.approve(int(b["id"]))),
    "/api/updates/reject": guarded(lambda b: selfupdate.reject(int(b["id"]))),
    "/api/calendar/free": guarded(lambda b: pages.free_time(b.get("day"), b.get("start", "09:00"), b.get("end", "18:00"), b.get("minutes", 60))),
    "/api/inbox/sync": guarded(lambda b: pages.inbox_sync(analyse=bool(b.get("analyse")))),
    "/api/inbox/catch-up": guarded(lambda b: pages.catch_up(b.get("days"))),
    "/api/inbox/archive-older": guarded(lambda b: pages.archive_older(b.get("days", 30))),
    "/api/inbox/analyse": guarded(lambda b: pages.analyse_one(b["id"])),
    "/api/inbox/draft": guarded(lambda b: pages.draft_reply(b["id"])),
    "/api/inbox/save-draft": guarded(lambda b: pages.save_draft(b["id"], b.get("text", ""), bool(b.get("to_gmail")))),
    "/api/inbox/discard-draft": guarded(lambda b: pages.discard_draft(b["id"])),
    "/api/inbox/done": guarded(lambda b: pages.set_done(b["id"], bool(b.get("done", True)))),
    "/api/siri": guarded(lambda b: siri(b)),
    "/api/access/rotate": lambda b, q, r: {"token": access.rotate()},
    "/api/google/connect": guarded(lambda b: accounts.connect_google(bool(b.get("force")))),
    "/api/health/update": guarded(lambda b: more_pages.health_update(b.get("action"), b)),
    "/api/health/review": guarded(lambda b: more_pages.health_review()),
    "/api/markets/update": guarded(lambda b: more_pages.markets_update(b.get("action"), b)),
    "/api/markets/refresh": guarded(lambda b: more_pages.markets_page(int(b.get("days", 130)), force=True)),
    "/api/markets/note": guarded(lambda b: more_pages.study_note(str(b.get("symbol", "")))),
    "/api/placements/update": guarded(lambda b: more_pages.placements_update(b.get("action"), b)),
    "/api/money/update": guarded(lambda b: pages.money_update(b.get("action"), b)),
    "/api/university/update": guarded(lambda b: pages.university_update(b.get("action"), b)),
    "/api/triggers/set": guarded(lambda b: triggers.set_enabled(b.get("kind"), b.get("on")) or triggers.status()),
    "/api/rules/add": guarded(lambda b: triggers.add_rule(b.get("name"), b.get("metric"), b.get("op"), b.get("threshold"), b.get("subject")) and triggers.status()),
    "/api/rules/remove": guarded(lambda b: triggers.remove_rule(b["id"]) or triggers.status()),
    "/api/triggers/check": lambda b, q, r: {"sent": triggers.check()},
    "/api/test-message": post_test_message,
    "/api/voice/transcribe": post_transcribe,
    "/api/speak": lambda b, q, r: {"ok": voice.speak(b.get("text", ""))},
    "/api/speak/stop": lambda b, q, r: {"ok": voice.stop_speaking() is None},
}


# ------------------------------------------------------------------
# Files: the page itself, vault downloads and simulation outputs
# ------------------------------------------------------------------
def static_file(path):
    """(bytes, content type) for a page asset, or None. Only files directly inside web/ are served."""
    name = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/")
    target = (WEB / name).resolve()
    if target.parent != WEB.resolve() or not target.is_file():
        return None
    return target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream"


def sandbox_file(path):
    """/sandbox/<run id>/<file name> -> (bytes, type), limited to the output types the sandbox shows."""
    parts = path.strip("/").split("/")
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    target = sandbox.folder(parts[1]) / Path(parts[2]).name
    if target.suffix.lower() not in sandbox.SHOWN_TYPES or not target.is_file():
        return None
    return target.read_bytes(), mimetypes.guess_type(target.name)[0] or "text/plain"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *arguments):       # keep the terminal quiet
        pass

    def reply(self, status, payload, content_type="application/json", extra=None):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def allowed(self, path):
        """This Mac, or another device with the access token. See cassiopeia/access.py."""
        ok, reason = access.check(self.client_address[0], self.headers, path)
        if ok:
            return True
        if self.command == "GET" and path in ("/", "/index.html"):        # a phone browser: send it to sign in
            self.reply(303, b"", "text/plain", {"Location": "/login"})
            return False
        self.reply(403, {"error": reason})
        return False

    def is_local(self):
        return access.is_loopback(self.client_address[0]) and access.host_name(self.headers) in access.LOCAL_NAMES

    def login(self, method):
        """The sign-in page for phones and other devices on the home network."""
        if not config.ENABLE_LAN_ACCESS and not self.is_local():
            return self.reply(403, {"error": "Cassiopeia only answers on this computer."})
        message = "Enter the access token shown in Control on your Mac."
        if method == "POST":
            client = self.client_address[0]
            length = min(int(self.headers.get("Content-Length") or 0), 4096)
            entered = parse_qs(self.rfile.read(length).decode("utf-8", "ignore")).get("token", [""])[0].strip()
            if access.locked_out(client):
                message = "Too many wrong tokens. Try again in ten minutes."
            elif access.token_ok(entered):
                cookie = f"{access.COOKIE}={entered}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000"
                return self.reply(303, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})
            else:
                access.record_failure(client)
                message = "That token was not right."
        page = access.LOGIN_PAGE.format(message=message).encode()
        self.reply(200, page, "text/html; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/login":
            return self.login("GET")
        if not self.allowed(url.path):
            return
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        try:
            if url.path == "/api/access":
                return self.reply(200, access.status(include_token=self.is_local()))
            if url.path in GET:
                return self.reply(200, GET[url.path](query))
            if url.path == "/api/vault/file":
                row = vault.get(int(query.get("id", 0)))
                if not row:
                    raise Problem("No such file.", 404)
                return self.reply(200, vault.full_path(row).read_bytes(), "application/octet-stream",
                                  {"Content-Disposition": f'attachment; filename="{row["name"]}"'})
            found = sandbox_file(url.path) if url.path.startswith("/sandbox/") else static_file(url.path)
            if found:
                return self.reply(200, found[0], found[1])
            self.reply(404, {"error": "Not found."})
        except Problem as problem:
            self.reply(problem.status, {"error": str(problem)})
        except Exception as problem:
            self.reply(500, {"error": f"{type(problem).__name__}: {str(problem)[:300]}"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/login":
            return self.login("POST")
        if not self.allowed(url.path):
            return
        # A page on another website cannot add this header. A Siri Shortcut sends a Bearer token instead.
        bearer = (self.headers.get("Authorization") or "").lower().startswith("bearer ")
        if self.headers.get("X-Cassiopeia") != "1" and not bearer:
            return self.reply(403, {"error": "Missing X-Cassiopeia header."})
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self.reply(413, {"error": "That file is over the 50 MB limit."})
        raw = self.rfile.read(length) if length else b""
        body = {}
        if "json" in (self.headers.get("Content-Type") or ""):
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return self.reply(400, {"error": "The request was not valid JSON."})
        try:
            if url.path not in POST:
                return self.reply(404, {"error": "Not found."})
            self.reply(200, POST[url.path](body, query, raw))
        except Problem as problem:
            self.reply(problem.status, {"error": str(problem)})
        except Exception as problem:
            self.reply(500, {"error": f"{type(problem).__name__}: {str(problem)[:300]}"})


def start(port=None):
    """Start the server on a background thread. Returns the server (call .shutdown() to stop)."""
    server = ThreadingHTTPServer((access.bind_host(), config.CASS_PORT if port is None else port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="cassiopeia-server", daemon=True).start()
    return server
