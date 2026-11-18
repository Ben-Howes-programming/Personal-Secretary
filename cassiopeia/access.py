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
Note    : Other devices connect over HTTPS on port 8766 with a certificate made on this Mac (see the
          end of this file). If openssl is unavailable it falls back to plain HTTP: home Wi-Fi only.
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


# Set by server.start(): "https" when the encrypted server for other devices is running,
# "http" when home access fell back to plain HTTP, None when home access is off.
LAN_MODE = {"mode": None}


def bind_host():
    """Plain HTTP listens on the whole network only when home access is on and HTTPS is unavailable."""
    return "0.0.0.0" if config.ENABLE_LAN_ACCESS and LAN_MODE["mode"] == "http" else config.CASS_HOST


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
    secure = LAN_MODE["mode"] == "https"
    port = config.CASS_HTTPS_PORT if secure else config.CASS_PORT
    base = f"{'https' if secure else 'http'}://{address}:{port}" if address else None
    return {"lan": config.ENABLE_LAN_ACCESS, "secure": secure, "address": base,
            "certificate": f"{base}/cassiopeia.crt" if secure and base else None,
            "token": token() if include_token else None}


LOGIN_PAGE = """<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cassiopeia sign in</title><style>body{{background:#141a3c;color:#efe6d2;font:16px system-ui;display:grid;place-items:center;min-height:90vh;margin:0}}
form{{display:grid;gap:.8rem;width:min(340px,90vw)}}input,button{{font:inherit;padding:.6rem;border-radius:8px;border:1px solid #2d3672}}
input{{background:#0d1230;color:inherit}}button{{background:#f2b33d;border:0;font-weight:600}}p{{color:#9ea6cc}}</style></head>
<body><form method="post" action="/login"><h1>Cassiopeia</h1><p>{message}</p>
<input name="token" type="password" autocomplete="current-password" placeholder="Access token" required autofocus>
<button>Sign in</button></form></body></html>"""


# ------------------------------------------------------------------
# HTTPS for other devices (18 Nov 2026)
# A private certificate authority made on this Mac signs a certificate for this Mac's
# address. Install the authority once on your iPhone and the connection is encrypted
# and trusted, so the token never crosses the Wi-Fi in the clear.
# ------------------------------------------------------------------
import ipaddress  # noqa: E402
import platform  # noqa: E402
import ssl  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

CERT_DIR = Path(config.PROJECT_ROOT) / "certs"          # ignored by Git

CA_CONFIG = """[req]
distinguished_name = dn
prompt = no
[dn]
CN = Cassiopeia private authority
O = Cassiopeia
[v3_ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
"""

SERVER_CONFIG = """[req]
distinguished_name = dn
prompt = no
[dn]
CN = Cassiopeia
[v3_server]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = {names}
"""


def _openssl(*arguments, config_text=None):
    """Run the openssl command line tool. Returns True on success."""
    with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as handle:
        handle.write(config_text or "")
        config_path = handle.name
    args = [a.replace("{config}", config_path) for a in arguments]
    try:
        done = subprocess.run(["openssl", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        Path(config_path).unlink(missing_ok=True)
    return done.returncode == 0


def subject_names(address):
    names = ["DNS:localhost", "IP:127.0.0.1"]
    host = platform.node().split(".")[0]
    if host:
        names.append(f"DNS:{host}.local")
    if address:
        try:
            names.append(f"IP:{ipaddress.ip_address(address)}")
        except ValueError:
            pass
    return ",".join(names)


def ensure_certificate(address=None):
    """Make (or remake, if the Mac's address changed) the certificates. Returns (cert, key) paths or None."""
    CERT_DIR.mkdir(exist_ok=True)
    ca_key, ca_cert = CERT_DIR / "ca.key", CERT_DIR / "cassiopeia.crt"
    key, cert, names_file = CERT_DIR / "server.key", CERT_DIR / "server.crt", CERT_DIR / "names.txt"
    names = subject_names(address)
    if not (ca_key.exists() and ca_cert.exists()):
        if not _openssl("req", "-x509", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(ca_key), "-out", str(ca_cert),
                        "-days", "3650", "-config", "{config}", "-extensions", "v3_ca", config_text=CA_CONFIG):
            return None
        cert.unlink(missing_ok=True)
    if cert.exists() and key.exists() and names_file.exists() and names_file.read_text() == names:
        return cert, key
    request = CERT_DIR / "server.csr"
    server_config = SERVER_CONFIG.format(names=names)
    ok = (_openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(request),
                   "-config", "{config}", config_text=server_config)
          and _openssl("x509", "-req", "-in", str(request), "-CA", str(ca_cert), "-CAkey", str(ca_key), "-CAcreateserial",
                       "-out", str(cert), "-days", "825", "-sha256", "-extfile", "{config}", "-extensions", "v3_server",
                       config_text=server_config))
    request.unlink(missing_ok=True)
    if not ok:
        return None
    for private in (ca_key, key):
        private.chmod(0o600)                       # private keys readable by you only
    names_file.write_text(names)
    return cert, key


def tls_context(address=None):
    """An SSL context for the HTTPS server, or None if certificates could not be made."""
    made = ensure_certificate(address)
    if not made:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(made[0]), str(made[1]))
    return context


def authority_certificate():
    """The public certificate to install on your phone. Contains no secret."""
    path = CERT_DIR / "cassiopeia.crt"
    return path.read_bytes() if path.exists() else None
