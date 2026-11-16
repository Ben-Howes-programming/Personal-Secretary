"""
sandbox.py
==========
Purpose : "Run a simulation on ...". Claude writes a short Python script, you read and
          approve it, then it runs in a scratch folder and its charts appear on screen.
Location: cassiopeia/sandbox.py
Used by : cassiopeia/server.py, cassiopeia/brain.py
Safety  : Nothing runs until you press Run. Scripts get 30 seconds, an empty folder under
          sandbox/, and an environment with no API keys. A word filter blocks the obvious
          ways to reach the network or other folders. The filter is a seat belt, not a
          guarantee, which is why you see the code first.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

import config
from ai import claude
from cassiopeia import store
from database import database as db

WRITER_SYSTEM = """You write one short, self-contained Python script for a physics student's simulation sandbox.
Rules:
- Use only the standard library, numpy, pandas and matplotlib.
- Start with a header comment block saying what the script models and its assumptions. Add inline comments.
- Save every figure as a PNG in the current folder with plt.savefig (never plt.show). Use clear axis labels with units.
- Print the key numbers with units. For a what-if comparison, print a small table of the scenarios side by side.
- No network, no input(), no reading or writing outside the current folder, finish within 20 seconds.
- Never invent real-world data. Use stated assumptions and label them as assumptions in the output.
Reply with the script in one ```python block and nothing else."""

BLOCKED = re.compile(r"\b(subprocess|socket|requests|urllib|http\.client|shutil|ctypes|webbrowser|smtplib)\b"
                     r"|os\.(system|popen|remove|unlink|rmdir|exec\w*|spawn\w*)|__import__|\beval\(|\bexec\("
                     r"|\.\./|/Users/|~/|/etc/|\binput\(")
SHOWN_TYPES = {".png", ".svg", ".csv", ".txt"}
TIME_LIMIT = 30


def extract_code(reply):
    found = re.search(r"```(?:python)?\s*\n(.*?)```", reply, flags=re.S)
    return (found.group(1) if found else reply).strip()


def problems(code):
    """Reasons this script may not run here. An empty list means it passed the filter."""
    hits = sorted({m.group(0) for m in BLOCKED.finditer(code)})
    return [f"uses {hit}" for hit in hits]


def draft(prompt):
    """Ask Claude for a script and store it for review. Returns the stored row."""
    reply = claude.complete(f"Write a simulation for: {prompt}", system=WRITER_SYSTEM, tier="chat",
                            max_tokens=1800, purpose="sandbox script")
    return save_draft(prompt, extract_code(reply))


def save_draft(prompt, code):
    sim_id = db.execute("INSERT INTO cass_sims (prompt, code, status, created_ts) VALUES (?, ?, 'awaiting approval', ?)",
                        (prompt, code, time.time()))
    return get(sim_id)


def get(sim_id):
    rows = db.query("SELECT * FROM cass_sims WHERE id = ?", (sim_id,))
    if not rows:
        return None
    row = rows[0]
    row["files"] = store.from_json(row["files"], [])
    row["problems"] = problems(row["code"])
    return row


def recent(limit=8):
    return [get(row["id"]) for row in db.query("SELECT id FROM cass_sims ORDER BY id DESC LIMIT ?", (limit,))]


def folder(sim_id):
    return Path(config.SANDBOX_PATH) / f"run_{int(sim_id)}"


def run(sim_id):
    """Run an approved script. Returns the updated row."""
    sim = get(sim_id)
    if sim is None:
        return None
    if sim["problems"]:
        status, output, files = "blocked", "Not run: the script " + ", ".join(sim["problems"]) + ".", []
    else:
        work = folder(sim_id)
        work.mkdir(parents=True, exist_ok=True)
        (work / "simulation.py").write_text(sim["code"])
        # A bare environment: no API keys or tokens are visible to the script
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "MPLBACKEND": "Agg", "HOME": str(work),
               "MPLCONFIGDIR": str(work)}
        try:
            done = subprocess.run([sys.executable, "simulation.py"], cwd=work, env=env, capture_output=True,
                                  text=True, timeout=TIME_LIMIT)
            output = (done.stdout + ("\n" + done.stderr if done.returncode else "")).strip()[-6000:]
            status = "done" if done.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            status, output = "failed", f"Stopped after {TIME_LIMIT} seconds."
        files = sorted(p.name for p in work.iterdir() if p.suffix.lower() in SHOWN_TYPES)
    db.execute("UPDATE cass_sims SET status = ?, output = ?, files = ? WHERE id = ?",
               (status, output, store.to_json(files), sim_id))
    return get(sim_id)
