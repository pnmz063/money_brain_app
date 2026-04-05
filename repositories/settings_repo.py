from __future__ import annotations

from db.connection import get_conn


def get_setting(key, user_id: int, default="0"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT value FROM settings WHERE key = %s AND user_id = %s",
        (key, user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings(key, value, user_id) VALUES (%s, %s, %s)
        ON CONFLICT (key, user_id) DO UPDATE SET value = EXCLUDED.value
    """, (str(key), str(value), user_id))
    conn.commit()
    conn.close()


def bulk_set_settings(items: dict, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    for key, value in items.items():
        cur.execute("""
            INSERT INTO settings(key, value, user_id) VALUES (%s, %s, %s)
            ON CONFLICT (key, user_id) DO UPDATE SET value = EXCLUDED.value
        """, (str(key), str(value), user_id))
    conn.commit()
    conn.close()
