from __future__ import annotations

import pandas as pd
from db.connection import get_conn


def read_obligations(user_id: int):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT *
        FROM obligations
        WHERE is_active = TRUE AND user_id = %s
        ORDER BY
            CASE WHEN prepayment_order IS NULL THEN 999999 ELSE prepayment_order END ASC,
            priority ASC,
            priority_score DESC,
            rate DESC,
            name
    """, conn, params=(user_id,))
    conn.close()
    return df


def add_obligation(
    name,
    obligation_type,
    rate,
    balance,
    monthly_payment,
    priority,
    user_id: int,
    note="",
    priority_score=0,
    recommended_action=None,
    recommendation_reason=None,
    prepayment_allowed=True,
    manual_prepayment_mode="auto",
    prepayment_order=None,
    exclude_from_prepayment=False,
):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO obligations(
            name, obligation_type, rate, balance, monthly_payment,
            priority, priority_score, recommended_action, recommendation_reason,
            prepayment_allowed, manual_prepayment_mode, prepayment_order,
            exclude_from_prepayment, note, is_active, user_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
    """, (
        name, obligation_type, rate, balance, monthly_payment,
        priority, priority_score, recommended_action, recommendation_reason,
        prepayment_allowed, manual_prepayment_mode, prepayment_order,
        exclude_from_prepayment, note, user_id,
    ))
    conn.commit()
    conn.close()


def disable_obligation(ob_id: int, user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE obligations SET is_active = FALSE WHERE id = %s AND user_id = %s",
        (ob_id, user_id),
    )
    conn.commit()
    conn.close()
