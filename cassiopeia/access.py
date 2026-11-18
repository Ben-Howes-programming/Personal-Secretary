"""
access.py
=========
Purpose : Who may talk to Cassiopeia. This Mac always may. Other devices on your home
          Wi-Fi (phone, iPad, a HomePod running a Siri Shortcut) may only when
          ENABLE_LAN_ACCESS=true in .env AND they present the access token.
Location: cassiopeia/access.py
Used by : cassiopeia/server.py
Rules   : 1. A request from this Mac must also name localhost as its host (blocks DNS rebinding).
          2. Any other request needs the token, either as a cookie set by the /login page or
             as the header "Authorization: Bearer <token>" (what a Siri Shortcut sends).
          3. Ten wrong tokens from one address lock that address out for ten minutes.
          4. Some actions stay on this Mac whatever the token: self-update, running
             simulations, connecting Google, deleting vault files.
Note    : The connection is plain HTTP, so only switch this on at home, never on public Wi-Fi.
"""

import hmac
import secrets
import socket
import threading
import time

import config
from database import database as db

COOKIE = "cass_token"
LOCAL_NAMES = {"127.0.0.1", "localhost", "::1"}
LOCAL_ONLY = {"/api/updates/propose", "/api/updates/approve", "/api/updates/reject", "/api/sims/run",
              "/api/google/connect", "/api/vault/remove", "/api/access/rotate", "/api/lab/run"}
MAX_FAILURES, LOCKOUT_SECONDS = 10, 600

_failures = {}          # address -> [count, first failure time]
_lock = threading.Lock()


def token():
    """The access token, created on first use and kept in the settings table (never in Git)."""
    value = db.get_setting("cass_access_token")
    if not value:
        value = secrets.token_urlsafe(24)
        db.set_setting("cass_access_token", value)
    return value


def rotate():
    """Make a new token. Every phone and Shortcut using the old one stops working."""
    value = secrets.token_urlsafe(24)
    db.set_setting("cass_access_token", value)
    return value


def bind_host():
    return "0.0.0.0" if config.ENABLE_LAN_ACCESS else config.CASS_HOST


def lan_address():
    """This Mac's address on the home network, e.g. 192.168.1.23. No data is sent to find it."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))          # picks the outward-facing interface, sends nothing
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def is_loopback(client_ip):
    return client_ip in ("127.0.0.1", "::1") or client_ip.startswith("127.")


def host_name(headers):
    host = headers.get("Host") or ""
    return host[1:].split("]")[0] if host.startswith("[") else host.rsplit(":", 1)[0]


def presented_token(headers):
    auth = headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    for part in (headers.get("Cookie") or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE:
            return value
    return None


def locked_out(client_ip):
    with _lock:
        count, since = _failures.get(client_ip, (0, 0.0))
        if count >= MAX_FAILURES and time.time() - since < LOCKOUT_SECONDS:
            return True
        if time.time() - since >= LOCKOUT_SECONDS:
            _failures.pop(client_ip, None)
    return False


def record_failure(client_ip):
    with _lock:
        count, since = _failures.get(client_ip, (0, time.time()))
        _failures[client_ip] = (count + 1, since)


def token_ok(candidate):
    return bool(candidate) and hmac.compare_digest(candidate, token())


def check(client_ip, headers, path):
    """Returns (allowed, reason). `reason` is shown to the caller when refused."""
    if is_loopback(client_ip) and host_name(headers) in LOCAL_NAMES:
        return True, ""
    if path in LOCAL_ONLY:
        return False, "That action is only available on the Mac itself."
    if not config.ENABLE_LAN_ACCESS:
        return False, "Cassiopeia only answers on this computer."
    if locked_out(client_ip):
        return False, "Too many wrong tokens. Try again in ten minutes."
    if token_ok(presented_token(headers)):
        return True, ""
    if presented_token(headers):
        record_failure(client_ip)
    return False, "Sign in first: open /login on this address and enter the access token."


def status(include_token):
    address = lan_address() if config.ENABLE_LAN_ACCESS else None
    return {"lan": config.ENABLE_LAN_ACCESS, "address": f"http://{address}:{config.CASS_PORT}" if address else None,
            "token": token() if include_token else None}


LOGIN_PAGE = """<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cassiopeia sign in</title><style>body{{background:#141a3c;color:#efe6d2;font:16px system-ui;display:grid;place-items:center;min-height:90vh;margin:0}}
form{{display:grid;gap:.8rem;width:min(340px,90vw)}}input,button{{font:inherit;padding:.6rem;border-radius:8px;border:1px solid #2d3672}}
input{{background:#0d1230;color:inherit}}button{{background:#f2b33d;border:0;font-weight:600}}p{{color:#9ea6cc}}</style></head>
<body><form method="post" action="/login"><h1>Cassiopeia</h1><p>{message}</p>
<input name="token" type="password" autocomplete="current-password" placeholder="Access token" required autofocus>
<button>Sign in</button></form></body></html>"""
