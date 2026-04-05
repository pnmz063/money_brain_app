from db.connection import get_conn


def reset_user_data(user_id: int):
    """Delete all data for a specific user (but keep the user account)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM obligations WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM categories WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
