from db.connection import get_conn


def get_setting(key, user_id: int, default="0"):
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ? AND user_id = ?",
        (key, user_id),
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value, user_id: int):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO settings(key, value, user_id) VALUES (?, ?, ?)
        ON CONFLICT(key, user_id) DO UPDATE SET value = excluded.value
        """,
        (str(key), str(value), user_id),
    )
    conn.commit()
    conn.close()


def bulk_set_settings(items: dict, user_id: int):
    conn = get_conn()
    for key, value in items.items():
        conn.execute(
            """
            INSERT INTO settings(key, value, user_id) VALUES (?, ?, ?)
            ON CONFLICT(key, user_id) DO UPDATE SET value = excluded.value
            """,
            (str(key), str(value), user_id),
        )
    conn.commit()
    conn.close()
