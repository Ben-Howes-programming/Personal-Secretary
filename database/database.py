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
            availability_request INTEGER,
            requested_day TEXT,
            requested_start TEXT,
            requested_end TEXT,
            summary TEXT,
            draft_reply TEXT,
            status TEXT DEFAULT 'open',
            analysis_version INTEGER DEFAULT 3
        )
    """)

    existing_columns = {
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(emails)"
        ).fetchall()
    }

    new_columns = {
        "availability_request": "INTEGER",
        "requested_day": "TEXT",
        "requested_start": "TEXT",
        "requested_end": "TEXT",
        "status": "TEXT DEFAULT 'open'",
        "analysis_version": "INTEGER DEFAULT 3",
    }

    for column, column_type in new_columns.items():

        if column not in existing_columns:

            cursor.execute(
                f"ALTER TABLE emails ADD COLUMN "
                f"{column} {column_type}"
            )

    connection.commit()
    connection.close()


def save_email(email):
    connection = get_connection()
    cursor = connection.cursor()

    analysis = email.get("analysis", {})

    status = email.get("status", "open")

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
            availability_request,
            requested_day,
            requested_start,
            requested_end,
            summary,
            draft_reply,
            status,
            analysis_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        email["id"],
        email.get("sender"),
        email.get("subject"),
        email.get("date"),
        email.get("body"),
        analysis.get("category"),
        analysis.get("priority"),
        int(analysis.get("action_required", False)),
        int(analysis.get("reply_needed", False)),
        int(analysis.get("availability_request", False)),
        analysis.get("requested_day"),
        analysis.get("requested_start"),
        analysis.get("requested_end"),
        analysis.get("summary"),
        email.get("draft_reply"),
        status,
        3,
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
            "action_required": bool(
                row["action_required"]
            ),
            "reply_needed": bool(
                row["reply_needed"]
            ),
            "availability_request": (
                bool(row["availability_request"])
                if row["availability_request"] is not None
                else None
            ),
            "requested_day": row["requested_day"],
            "requested_start": row["requested_start"],
            "requested_end": row["requested_end"],
            "summary": row["summary"],
        },
        "draft_reply": row["draft_reply"],
        "status": row["status"] or "open",
        "analysis_version": (
            row["analysis_version"]
            if row["analysis_version"] is not None
            else 1
        ),
    }


def update_draft_reply(message_id, draft):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE emails
        SET draft_reply = ?
        WHERE id = ?
        """,
        (draft, message_id)
    )

    connection.commit()
    connection.close()


def update_email_status(message_id, status):
    if status not in ("open", "completed"):
        raise ValueError(
            "Status must be 'open' or 'completed'."
        )

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE emails
        SET status = ?
        WHERE id = ?
        """,
        (status, message_id)
    )

    connection.commit()
    connection.close()


def clear_draft_reply(message_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE emails
        SET draft_reply = NULL
        WHERE id = ?
        """,
        (message_id,)
    )

    connection.commit()
    connection.close()