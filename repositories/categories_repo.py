import pandas as pd
from db.connection import get_conn


def read_categories(kind=None, *, user_id: int):
    conn = get_conn()
    if kind:
        df = pd.read_sql_query(
            "SELECT * FROM categories WHERE is_active = 1 AND kind = ? AND user_id = ? ORDER BY name",
            conn,
            params=(kind, user_id),
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM categories WHERE is_active = 1 AND user_id = ? ORDER BY kind, name",
            conn,
            params=(user_id,),
        )
    conn.close()
    return df


def add_category(name, kind, user_id: int, expense_scope=None, is_fixed_default=False):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO categories(name, kind, expense_scope, is_fixed_default, is_active, user_id)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (name, kind, expense_scope, 1 if is_fixed_default else 0, user_id),
    )
    conn.commit()
    conn.close()


def ensure_category(name, kind, user_id: int, expense_scope=None, is_fixed_default=False):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM categories WHERE name = ? AND user_id = ?",
        (name, user_id),
    ).fetchone()
    if row:
        conn.close()
        return int(row["id"])

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO categories(name, kind, expense_scope, is_fixed_default, is_active, user_id)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (name, kind, expense_scope, 1 if is_fixed_default else 0, user_id),
    )
    conn.commit()
    category_id = cur.lastrowid
    conn.close()
    return int(category_id)


def disable_category(cat_id: int, user_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE categories SET is_active = 0 WHERE id = ? AND user_id = ?",
        (cat_id, user_id),
    )
    conn.commit()
    conn.close()
