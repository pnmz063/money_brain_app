import pandas as pd
from db.connection import get_conn


def read_obligations():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT *
        FROM obligations
        WHERE is_active = 1
        ORDER BY
            CASE WHEN prepayment_order IS NULL THEN 999999 ELSE prepayment_order END ASC,
            priority ASC,
            priority_score DESC,
            rate DESC,
            name
    """, conn)
    conn.close()
    return df


def add_obligation(
    name,
    obligation_type,
    rate,
    balance,
    monthly_payment,
    priority,
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
    conn.execute("""
        INSERT INTO obligations(
            name,
            obligation_type,
            rate,
            balance,
            monthly_payment,
            priority,
            priority_score,
            recommended_action,
            recommendation_reason,
            prepayment_allowed,
            manual_prepayment_mode,
            prepayment_order,
            exclude_from_prepayment,
            note,
            is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        name,
        obligation_type,
        rate,
        balance,
        monthly_payment,
        priority,
        priority_score,
        recommended_action,
        recommendation_reason,
        1 if prepayment_allowed else 0,
        manual_prepayment_mode,
        prepayment_order,
        1 if exclude_from_prepayment else 0,
        note,
    ))
    conn.commit()
    conn.close()


def disable_obligation(ob_id: int):
    conn = get_conn()
    conn.execute("UPDATE obligations SET is_active = 0 WHERE id = ?", (ob_id,))
    conn.commit()
    conn.close()