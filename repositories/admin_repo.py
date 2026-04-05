from db.connection import get_conn


def reset_application_data():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions")
    cur.execute("DELETE FROM obligations")
    cur.execute("DELETE FROM categories")
    cur.execute("DELETE FROM settings")
    conn.commit()
    conn.close()
