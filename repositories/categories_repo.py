import pandas as pd
from db.connection import get_conn


def read_categories(kind=None):
    conn = get_conn()
    if kind:
        df = pd.read_sql_query(
            "SELECT * FROM categories WHERE is_active = 1 AND kind = ? ORDER BY name",
            conn,
            params=(kind,),
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM categories WHERE is_active = 1 ORDER BY kind, name",
            conn,
        )
    conn.close()
    return df


def add_category(name, kind, expense_scope=None, is_fixed_default=False):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO categories(name, kind, expense_scope, is_fixed_default, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (name, kind, expense_scope, 1 if is_fixed_default else 0),
    )
    conn.commit()
    conn.close()


def ensure_category(name, kind, expense_scope=None, is_fixed_default=False):
    conn = get_conn()
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if row:
        conn.close()
        return int(row["id"])

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO categories(name, kind, expense_scope, is_fixed_default, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (name, kind, expense_scope, 1 if is_fixed_default else 0),
    )
    conn.commit()
    category_id = cur.lastrowid
    conn.close()
    return int(category_id)


def disable_category(cat_id: int):
    conn = get_conn()
    conn.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
