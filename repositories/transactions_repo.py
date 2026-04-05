from __future__ import annotations

from datetime import date
import pandas as pd
from db.connection import get_conn


def read_transactions(start_date: date, end_date: date, user_id: int):
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT t.id, t.tx_date, t.name, t.amount, t.kind, t.is_fixed, t.note,
               c.name AS category_name, c.expense_scope
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.tx_date >= %s AND t.tx_date <= %s
          AND t.user_id = %s
        ORDER BY t.tx_date DESC, t.id DESC
        """,
        conn,
        params=(start_date.isoformat(), end_date.isoformat(), user_id),
    )
    conn.close()
    return df


def add_transaction(tx_date, name, amount, kind, category_id, user_id: int, is_fixed=False, note=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions(tx_date, name, amount, kind, category_id, is_fixed, note, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (tx_date, name, amount, kind, category_id, is_fixed, note, user_id))
    conn.commit()
    conn.close()


def delete_transaction(tx_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE id = %s AND user_id = %s", (tx_id, user_id))
    conn.commit()
    conn.close()
