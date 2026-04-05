from __future__ import annotations

from db.connection import get_conn


def reset_user_data(user_id: int):
    """Delete all data for a specific user (but keep the user account)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM obligations WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM categories WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM settings WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
