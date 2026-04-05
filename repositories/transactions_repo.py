from datetime import date
import pandas as pd
from db.connection import get_conn


def read_transactions(start_date: date, end_date: date):
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT t.id, t.tx_date, t.name, t.amount, t.kind, t.is_fixed, t.note,
               c.name AS category_name, c.expense_scope
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE date(t.tx_date) BETWEEN date(?) AND date(?)
        ORDER BY date(t.tx_date) DESC, t.id DESC
        """,
        conn,
        params=(start_date.isoformat(), end_date.isoformat()),
    )
    conn.close()
    return df


def add_transaction(tx_date, name, amount, kind, category_id, is_fixed=False, note=""):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO transactions(tx_date, name, amount, kind, category_id, is_fixed, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tx_date, name, amount, kind, category_id, 1 if is_fixed else 0, note),
    )
    conn.commit()
    conn.close()


def delete_transaction(tx_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
