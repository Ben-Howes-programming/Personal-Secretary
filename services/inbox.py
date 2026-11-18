"""
inbox.py
========
Purpose : One sync routine for every mail account (Gmail, Outlook, iCloud).
          New mail is fetched once, stored in SQLite, classified by rules where
          possible, and only the remainder is sent to Claude, in batches.
Location: services/inbox.py
Used by : ui/state.py
Note    : Pages read emails from the database, never straight from Gmail, so
          opening a page costs no tokens and no API calls.
"""

import time

import config
from ai import claude
from database import database as db
from services import apple, gmail, microsoft

BATCH_SIZE = 6   # emails per Claude call


def _store(email, analysis, analysed_by):
    email["analysis"] = analysis
    email["analysed_by"] = analysed_by
    email["analysis_version"] = db.ANALYSIS_VERSION
    db.save_email(email)


def sync(gmail_service=None, analyse=True, query=None, limit=None):
    """Fetch new mail from every connected account and analyse what needs it.

    Returns counts for the status line: new, by_rules, by_claude, pending, errors.
    query and limit override config.GMAIL_QUERY and config.MAX_EMAILS (used for a one-off catch-up).
    """
    stats = {"new": 0, "by_rules": 0, "by_claude": 0, "pending": 0, "errors": []}
    fresh = []

    # 1. Gmail
    if gmail_service is not None:
        try:
            for message_id in gmail.list_message_ids(gmail_service, query or config.GMAIL_QUERY, limit or config.MAX_EMAILS):
                if not db.email_is_cached(message_id):
                    fresh.append(gmail.get_email(gmail_service, message_id))
        except Exception as error:
            stats["errors"].append(f"Gmail: {str(error)[:200]}")

    # 2. Outlook and iCloud, if you have connected them
    for name, connected, fetch in (("Outlook", microsoft.is_connected, microsoft.list_messages),
                                   ("iCloud", apple.mail_configured, apple.fetch_mail)):
        if not connected():
            continue
        try:
            fresh.extend(email for email in fetch(config.MAX_EMAILS) if not db.email_is_cached(email["id"]))
        except Exception as error:
            stats["errors"].append(f"{name}: {str(error)[:200]}")

    stats["new"] = len(fresh)

    # 3. Rules first (free), then queue the rest for Claude
    queue = []
    for email in fresh:
        verdict = claude.quick_classify(email)
        if verdict:
            _store(email, verdict, "rules")
            stats["by_rules"] += 1
        else:
            _store(email, claude.unanalysed(), "pending")
            queue.append(email)

    # 4. Claude, capped per sync. Anything over the cap waits for the next sync.
    if analyse and claude.is_available():
        waiting = {email["id"]: email for email in queue}
        for email in db.pending_emails(config.MAX_AI_EMAILS_PER_SYNC):
            waiting.setdefault(email["id"], email)
        todo = list(waiting.values())[:config.MAX_AI_EMAILS_PER_SYNC]
        for start in range(0, len(todo), BATCH_SIZE):
            batch = todo[start:start + BATCH_SIZE]
            try:
                results = claude.analyse_emails(batch)
            except claude.AIError as error:
                stats["errors"].append(str(error)[:200])
                break
            for email, analysis in zip(batch, results):
                if analysis is None:
                    _store(email, claude.unanalysed("Claude could not read this one. Use Re-analyse to try again."), "failed")
                else:
                    _store(email, analysis, "claude")
                    stats["by_claude"] += 1

    stats["pending"] = len(db.pending_emails(500))
    db.set_setting("last_sync", time.time())
    db.set_setting("last_sync_stats", stats)
    return stats


def reanalyse(email):
    """Send one email to Claude again (used by the Re-analyse button)."""
    result = claude.analyse_emails([email])[0]
    if result is None:
        raise claude.AIError("Claude did not return a usable analysis.")
    email["draft_reply"] = None
    _store(email, result, "claude")
    return result


def minutes_since_sync():
    last = db.get_setting("last_sync")
    return None if not last else (time.time() - last) / 60
