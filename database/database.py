import sqlite3


DATABASE = "secretary.db"


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            sender TEXT,
            subject TEXT,
            date TEXT,
            body TEXT,
            category TEXT,
            priority TEXT,
            action_required INTEGER,
            reply_needed INTEGER,
            summary TEXT,
            draft_reply TEXT
        )
    """)

    connection.commit()
    connection.close()


def save_email(email):
    connection = get_connection()
    cursor = connection.cursor()

    analysis = email["analysis"]

    cursor.execute("""
        INSERT OR REPLACE INTO emails (
            id,
            sender,
            subject,
            date,
            body,
            category,
            priority,
            action_required,
            reply_needed,
            summary,
            draft_reply
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        email["id"],
        email["sender"],
        email["subject"],
        email["date"],
        email["body"],
        analysis.get("category"),
        analysis.get("priority"),
        int(analysis.get("action_required", False)),
        int(analysis.get("reply_needed", False)),
        analysis.get("summary"),
        email.get("draft_reply")
    ))

    connection.commit()
    connection.close()


def email_is_cached(message_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT id FROM emails WHERE id = ?",
        (message_id,)
    )

    result = cursor.fetchone()

    connection.close()

    return result is not None


def get_cached_email(message_id):
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM emails WHERE id = ?",
        (message_id,)
    )

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None

    return {
        "id": row["id"],
        "sender": row["sender"],
        "subject": row["subject"],
        "date": row["date"],
        "body": row["body"],
        "analysis": {
            "category": row["category"],
            "priority": row["priority"],
            "action_required": bool(row["action_required"]),
            "reply_needed": bool(row["reply_needed"]),
            "summary": row["summary"]
        },
        "draft_reply": row["draft_reply"]
    }