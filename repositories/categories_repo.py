from __future__ import annotations

import pandas as pd
from db.connection import get_conn


def read_categories(kind=None, *, user_id: int):
    conn = get_conn()
    if kind:
        df = pd.read_sql_query(
            "SELECT * FROM categories WHERE is_active = TRUE AND kind = %s AND user_id = %s ORDER BY name",
            conn,
            params=(kind, user_id),
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM categories WHERE is_active = TRUE AND user_id = %s ORDER BY kind, name",
            conn,
            params=(user_id,),
        )
    conn.close()
    return df


def add_category(name, kind, user_id: int, expense_scope=None, is_fixed_default=False):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO categories(name, kind, expense_scope, is_fixed_default, is_active, user_id)
        VALUES (%s, %s, %s, %s, TRUE, %s)
    """, (name, kind, expense_scope, is_fixed_default, user_id))
    conn.commit()
    conn.close()


def ensure_category(name, kind, user_id: int, expense_scope=None, is_fixed_default=False):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM categories WHERE name = %s AND user_id = %s",
        (name, user_id),
    )
    row = cur.fetchone()
    if row:
        conn.close()
        return int(row["id"])

    cur.execute("""
        INSERT INTO categories(name, kind, expense_scope, is_fixed_default, is_active, user_id)
        VALUES (%s, %s, %s, %s, TRUE, %s)
        RETURNING id
    """, (name, kind, expense_scope, is_fixed_default, user_id))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    return int(row["id"])


def disable_category(cat_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE categories SET is_active = FALSE WHERE id = %s AND user_id = %s",
        (cat_id, user_id),
    )
    conn.commit()
    conn.close()
