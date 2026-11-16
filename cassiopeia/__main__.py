"""
__main__.py
===========
Purpose : Starts Cassiopeia: database, web server, scheduler, then the window.
Location: cassiopeia/__main__.py
Run     : python -m cassiopeia              open the app
          python -m cassiopeia --service    run in the background with no window (used at login)
Note    : If Cassiopeia is already running, this only opens a window onto it and exits.
"""

import argparse
import platform
import subprocess
import time
import webbrowser
from pathlib import Path

import requests

import config
from cassiopeia import scheduler, server, store

CHROME = Path("/Applications/Google Chrome.app")


def already_running(url):
    try:
        return requests.get(url + "/api/ping", timeout=1.5).json().get("app") == "cassiopeia"
    except Exception:
        return False


def open_window(url):
    """Open the app window. Returns True if this call blocks until the window closes."""
    # Chrome's app mode gives a clean window with no address bar, and its speech
    # recognition is what the voice conversation uses.
    if platform.system() == "Darwin" and CHROME.exists():
        subprocess.Popen(["open", "-na", "Google Chrome", "--args", f"--app={url}", "--window-size=1280,860"])
        return False
    try:
        import webview                       # optional: pip install pywebview
        webview.create_window(config.APP_NAME, url, width=1280, height=860)
        webview.start()
        return True
    except Exception:
        webbrowser.open(url)
        return False


def main():
    parser = argparse.ArgumentParser(prog="cassiopeia")
    parser.add_argument("--service", action="store_true", help="run in the background with no window")
    arguments = parser.parse_args()
    url = f"http://{config.CASS_HOST}:{config.CASS_PORT}"

    if already_running(url):
        if not arguments.service:
            open_window(url)
        return

    store.initialise()
    server.start()
    scheduler.start()
    print(f"{config.APP_NAME} is running at {url}  (Ctrl+C to stop)")
    if not arguments.service:
        open_window(url)
    try:
        while True:                          # the server and scheduler run on background threads
            time.sleep(3600)
    except KeyboardInterrupt:
        print(f"\n{config.APP_NAME} stopped.")


if __name__ == "__main__":
    main()
