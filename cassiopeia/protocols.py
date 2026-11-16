"""
protocols.py
============
Purpose : One-command presets such as "Initiate Focus Protocol". Each is a list of steps.
Location: cassiopeia/protocols.py
Used by : cassiopeia/brain.py, cassiopeia/server.py
Edit    : cassiopeia/protocols.json holds the presets. Change it freely.
Smart home: lights, TV and phone Focus modes are reached through a "shortcut" step, which
          runs a Shortcut you build once in Apple's Shortcuts app. Cassiopeia cannot see
          your Home devices directly, so a missing Shortcut is reported, not guessed.
"""

import json
import platform
import re
import subprocess
import webbrowser
from pathlib import Path

from ai import voice
from cassiopeia import notify
from database import tasks

FILE = Path(__file__).with_name("protocols.json")
IS_MAC = platform.system() == "Darwin"


def load():
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}


def match(text):
    """'Initiate focus protocol', 'movie protocol please' -> the preset's key, else None."""
    found = re.search(r"\b([a-z][a-z \-]{1,30}?)\s+protocol\b", (text or "").lower())
    if not found:
        return None
    wanted = re.sub(r"^(initiate|start|run|begin|activate|engage)\s+", "", found.group(1).strip())
    return next((key for key in load() if key.lower() == wanted), None)


def top_task():
    grouped = tasks.group_tasks(tasks.list_tasks())
    for bucket in ("Overdue", "Today", "Upcoming", "No date"):
        if grouped[bucket]:
            return grouped[bucket][0]["title"]
    return None


def _step(step):
    """Run one step. Returns (ok, what happened)."""
    kind, value = step.get("do"), step.get("value", "")
    if isinstance(value, str) and value.startswith("["):          # an unfilled [placeholder]
        return False, f"{kind}: skipped, fill in the placeholder in protocols.json"
    if kind == "say":
        return (True, f"said: {value}") if voice.speak(value) else (False, "say: speech needs macOS")
    if kind == "top_task":
        title = top_task()
        line = f"Your top task is: {title}." if title else "You have no open tasks."
        voice.speak(line)
        return True, line
    if kind == "notify":
        return notify.mac_notification("Cassiopeia", value)
    if kind == "open_url":
        if not re.match(r"https?://", value):
            return False, "open_url: only http and https links are opened"
        webbrowser.open(value)
        return True, f"opened {value}"
    if kind == "shortcut":
        if not IS_MAC:
            return False, f"shortcut '{value}': needs macOS"
        try:
            done = subprocess.run(["shortcuts", "run", value], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as problem:
            return False, f"shortcut '{value}': {problem}"
        if done.returncode != 0:
            return False, f"shortcut '{value}' did not run. Create it in the Shortcuts app with that exact name."
        return True, f"ran shortcut '{value}'"
    return False, f"unknown step '{kind}'"


def run(name):
    """Run every step of a preset, carrying on past failures. Returns a report for the screen."""
    preset = load().get(name)
    if not preset:
        return {"ok": False, "name": name, "steps": [], "error": f"No protocol called '{name}'."}
    results = []
    for step in preset.get("steps", []):
        ok, detail = _step(step)
        results.append({"ok": ok, "detail": detail})
    return {"ok": all(r["ok"] for r in results), "name": name, "about": preset.get("about", ""), "steps": results}
