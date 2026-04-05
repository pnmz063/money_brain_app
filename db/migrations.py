from db.connection import get_conn


MINIMAL_DEFAULT_CATEGORIES = [
    ("Зарплата", "income", None, 0, 1),
    ("Пособие", "income", None, 0, 1),
    ("Премия", "income", None, 0, 1),
    ("Другой доход", "income", None, 0, 1),
    ("Расход", "expense", "variable_life", 0, 1),
    ("Досрочка", "transfer", None, 0, 1),
    ("Накопления", "transfer", None, 0, 1),
]


def _ensure_column(cur, table_name: str, column_name: str, ddl: str):
    cols = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
    col_names = [c[1] for c in cols]
    if column_name not in col_names:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _get_schema_version(cur) -> int:
    cur.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = cur.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    return int(row[0]) if row else 0


def _set_schema_version(cur, version: int):
    cur.execute("DELETE FROM schema_version")
    cur.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))


def _migrate_v1_to_v2(cur):
    """Add users table and user_id columns to all existing tables."""

    # 1. Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Recreate settings with composite PK (key, user_id)
    cur.execute("DROP TABLE IF EXISTS settings")
    cur.execute("""
        CREATE TABLE settings (
            key TEXT NOT NULL,
            value TEXT,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (key, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 3. Recreate categories with user_id and UNIQUE(name, user_id)
    cur.execute("DROP TABLE IF EXISTS categories")
    cur.execute("""
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            expense_scope TEXT,
            is_fixed_default INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            user_id INTEGER NOT NULL,
            UNIQUE(name, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 4. Recreate transactions with user_id
    cur.execute("DROP TABLE IF EXISTS transactions")
    cur.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_date TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            kind TEXT NOT NULL,
            category_id INTEGER,
            is_fixed INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER NOT NULL,
            FOREIGN KEY(category_id) REFERENCES categories(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 5. Recreate obligations with user_id
    cur.execute("DROP TABLE IF EXISTS obligations")
    cur.execute("""
        CREATE TABLE obligations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            obligation_type TEXT NOT NULL,
            rate REAL,
            balance REAL,
            monthly_payment REAL NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 3,
            priority_score REAL NOT NULL DEFAULT 0,
            recommended_action TEXT,
            recommendation_reason TEXT,
            prepayment_allowed INTEGER NOT NULL DEFAULT 1,
            manual_prepayment_mode TEXT DEFAULT 'auto',
            prepayment_order INTEGER,
            exclude_from_prepayment INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            note TEXT,
            user_id INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)


def seed_defaults_for_user(user_id: int):
    """Insert default categories and settings for a newly registered user."""
    conn = get_conn()
    cur = conn.cursor()

    for row in MINIMAL_DEFAULT_CATEGORIES:
        cur.execute(
            """
            INSERT OR IGNORE INTO categories(name, kind, expense_scope, is_fixed_default, is_active, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (*row, user_id),
        )

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
        cur.execute(
            "INSERT OR IGNORE INTO settings(key, value, user_id) VALUES (?, ?, ?)",
            (k, v, user_id),
        )

    conn.commit()
    conn.close()


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Ensure schema_version table exists
    cur.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")

    version = _get_schema_version(cur)

    if version < 2:
        _migrate_v1_to_v2(cur)
        _set_schema_version(cur, 2)

    # Also make sure users table exists (idempotent)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
