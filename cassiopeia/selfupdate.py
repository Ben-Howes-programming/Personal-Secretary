"""
selfupdate.py
=============
Purpose : "Cassiopeia, update yourself to ...". The change is made by Claude Code on a
          separate Git branch in a separate folder, the tests are run, and you see the
          diff. Nothing reaches the running app until you approve it.
Location: cassiopeia/selfupdate.py
Used by : cassiopeia/server.py
Flow    : propose() -> status "awaiting approval" or "tests failed" -> approve() or reject().
Safety  : Needs a clean working tree. A change that touches secrets is refused. A change
          whose tests fail cannot be approved. Approving merges the branch; restart
          Cassiopeia to load the new code.
UNTESTED: written without access to a Mac with Claude Code. Expect to adjust
          config.SELF_UPDATE_CLI_ARGS on first use.
"""

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import config
from ai import claude
from database import database as db

ROOT = Path(config.PROJECT_ROOT)
SECRET_FILES = re.compile(r"(^|/)(\.env|credentials\.json|token\.json|ms_token\.json|[^/]*\.db)$", re.M)
BRIEF = """You are changing the source code of Cassiopeia, a local single-user app. Read CLAUDE.md first and follow it.

Requested change: {instruction}

Rules: make the smallest change that does the job. Add or update a test in tests/. Never touch .env,
credentials.json, token.json or any .db file. Do not add network calls to new hosts or new permissions
without that being the explicit request. When finished, reply with a three-line summary of what you changed."""


def _git(*arguments, cwd=ROOT, check=True):
    done = subprocess.run(["git", *arguments], cwd=cwd, capture_output=True, text=True, timeout=120)
    if check and done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout).strip()[:400])
    return done.stdout


def _set(update_id, **fields):
    names = ", ".join(f"{name} = ?" for name in fields)
    db.execute(f"UPDATE cass_updates SET {names} WHERE id = ?", (*fields.values(), update_id))


def get(update_id):
    rows = db.query("SELECT * FROM cass_updates WHERE id = ?", (update_id,))
    return rows[0] if rows else None


def recent(limit=6):
    return db.query("SELECT * FROM cass_updates ORDER BY id DESC LIMIT ?", (limit,))


def touches_secrets(changed_files):
    return [name for name in changed_files if SECRET_FILES.search(name)]


def propose(instruction):
    """Start a self-update in the background. Returns the new row straight away."""
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("Say what to change.")
    if not claude.find_cli():
        raise RuntimeError("Self-update needs the Claude Code command line tool, which was not found.")
    if _git("status", "--porcelain").strip():
        raise RuntimeError("There are uncommitted changes. Commit them first so the update starts from a known state.")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    branch, worktree = f"self/{stamp}", ROOT / ".cass_worktrees" / stamp
    update_id = db.execute("INSERT INTO cass_updates (instruction, branch, worktree, status, created_ts) "
                           "VALUES (?, ?, ?, 'working', ?)", (instruction, branch, str(worktree), time.time()))
    threading.Thread(target=_work, args=(update_id, instruction, branch, worktree), daemon=True).start()
    return get(update_id)


def _work(update_id, instruction, branch, worktree):
    try:
        worktree.parent.mkdir(exist_ok=True)
        _git("worktree", "add", "-b", branch, str(worktree), "HEAD")
        # Remove the API key so the edit is billed to the Claude plan, as the rest of the app does
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        subprocess.run([claude.find_cli(), "-p", BRIEF.format(instruction=instruction), *config.SELF_UPDATE_CLI_ARGS],
                       cwd=worktree, env=env, capture_output=True, text=True, timeout=config.SELF_UPDATE_TIMEOUT)
        _git("add", "-A", cwd=worktree)
        changed = _git("diff", "--cached", "--name-only", cwd=worktree).split()
        if not changed:
            return _set(update_id, status="no change", diff="Claude Code made no changes.")
        blocked = touches_secrets(changed)
        if blocked:
            return _set(update_id, status="refused", diff="The change touched protected files: " + ", ".join(blocked))
        _git("-c", "user.name=Cassiopeia", "-c", "user.email=cassiopeia@localhost", "commit", "-q", "-m",
             f"self-update: {instruction[:60]}", cwd=worktree)
        tests = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=worktree, capture_output=True,
                               text=True, timeout=600)
        diff = _git("diff", "--stat", "HEAD~1", "HEAD", cwd=worktree) + "\n" + _git("diff", "HEAD~1", "HEAD", cwd=worktree)
        _set(update_id, status="awaiting approval" if tests.returncode == 0 else "tests failed",
             diff=diff[:60000], test_output=(tests.stdout + tests.stderr)[-3000:])
    except Exception as problem:
        _set(update_id, status="failed", diff=f"Self-update stopped: {str(problem)[:500]}")


def _clean_up(row, delete_branch):
    _git("worktree", "remove", "--force", row["worktree"], check=False)
    if delete_branch:
        _git("branch", "-D", row["branch"], check=False)


def approve(update_id):
    """Merge an update whose tests passed. Returns the updated row."""
    row = get(update_id)
    if not row or row["status"] != "awaiting approval":
        raise RuntimeError("Only an update that is awaiting approval, with passing tests, can be merged.")
    _git("-c", "user.name=Cassiopeia", "-c", "user.email=cassiopeia@localhost", "merge", "--no-ff", "-m",
         f"Merge self-update: {row['instruction'][:60]}", row["branch"])
    _clean_up(row, delete_branch=False)
    _set(update_id, status="merged, restart Cassiopeia to load it")
    return get(update_id)


def reject(update_id):
    row = get(update_id)
    if not row:
        raise RuntimeError("No such update.")
    _clean_up(row, delete_branch=True)
    _set(update_id, status="rejected")
    return get(update_id)
