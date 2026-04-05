from __future__ import annotations

from db.connection import get_conn


MINIMAL_DEFAULT_CATEGORIES = [
    ("Зарплата", "income", None, False, True),
    ("Пособие", "income", None, False, True),
    ("Премия", "income", None, False, True),
    ("Другой доход", "income", None, False, True),
    ("Расход", "expense", "variable_life", False, True),
    ("Досрочка", "transfer", None, False, True),
    ("Накопления", "transfer", None, False, True),
]


def _get_schema_version(cur) -> int:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)
    cur.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cur.fetchone()
    return int(row["version"]) if row else 0


def _set_schema_version(cur, version: int):
    cur.execute("DELETE FROM schema_version")
    cur.execute("INSERT INTO schema_version(version) VALUES (%s)", (version,))


def _migrate_to_v2(cur):
    """Create all tables with user_id support (PostgreSQL)."""

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    cur.execute("DROP TABLE IF EXISTS transactions")
    cur.execute("DROP TABLE IF EXISTS obligations")
    cur.execute("DROP TABLE IF EXISTS categories")
    cur.execute("DROP TABLE IF EXISTS settings")

    cur.execute("""
        CREATE TABLE settings (
            key TEXT NOT NULL,
            value TEXT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            PRIMARY KEY (key, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            expense_scope TEXT,
            is_fixed_default BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            UNIQUE(name, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE transactions (
            id SERIAL PRIMARY KEY,
            tx_date TEXT NOT NULL,
            name TEXT NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            kind TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            is_fixed BOOLEAN NOT NULL DEFAULT FALSE,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            user_id INTEGER NOT NULL REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE obligations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            obligation_type TEXT NOT NULL,
            rate DOUBLE PRECISION,
            balance DOUBLE PRECISION,
            monthly_payment DOUBLE PRECISION NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 3,
            priority_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            recommended_action TEXT,
            recommendation_reason TEXT,
            prepayment_allowed BOOLEAN NOT NULL DEFAULT TRUE,
            manual_prepayment_mode TEXT DEFAULT 'auto',
            prepayment_order INTEGER,
            exclude_from_prepayment BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            note TEXT,
            user_id INTEGER NOT NULL REFERENCES users(id)
        )
    """)


def seed_defaults_for_user(user_id: int):
    """Insert default categories and settings for a newly registered user."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        for row in MINIMAL_DEFAULT_CATEGORIES:
            cur.execute("""
                INSERT INTO categories(name, kind, expense_scope, is_fixed_default, is_active, user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name, user_id) DO NOTHING
            """, (*row, user_id))

        defaults = [
            ("strategy_name", "balanced"),
            ("strategy_life_pct", "60"),
            ("strategy_prepayment_pct", "25"),
            ("strategy_savings_pct", "15"),
            ("onboarding_completed", "false"),
            ("tax_regime", "ru_13_15"),
            ("tax_annual_threshold", "5000000"),
        ]
        for k, v in defaults:
            cur.execute("""
                INSERT INTO settings(key, value, user_id) VALUES (%s, %s, %s)
                ON CONFLICT (key, user_id) DO NOTHING
            """, (k, v, user_id))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            )
        """)
        conn.commit()

        version = _get_schema_version(cur)

        if version < 2:
            _migrate_to_v2(cur)
            _set_schema_version(cur, 2)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
