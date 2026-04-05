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


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            expense_scope TEXT,
            is_fixed_default INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    _ensure_column(cur, "categories", "expense_scope", "expense_scope TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_date TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            kind TEXT NOT NULL,
            category_id INTEGER,
            is_fixed INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS obligations (
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
            is_active INTEGER NOT NULL DEFAULT 1,
            note TEXT
        )
        """
    )

    _ensure_column(cur, "obligations", "priority_score", "priority_score REAL NOT NULL DEFAULT 0")
    _ensure_column(cur, "obligations", "recommended_action", "recommended_action TEXT")
    _ensure_column(cur, "obligations", "recommendation_reason", "recommendation_reason TEXT")
    _ensure_column(cur, "obligations", "prepayment_allowed", "prepayment_allowed INTEGER NOT NULL DEFAULT 1")
    _ensure_column(cur, "obligations", "manual_prepayment_mode", "manual_prepayment_mode TEXT DEFAULT 'auto'")
    _ensure_column(cur, "obligations", "prepayment_order", "prepayment_order INTEGER")
    _ensure_column(cur, "obligations", "exclude_from_prepayment", "exclude_from_prepayment INTEGER NOT NULL DEFAULT 0")

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
        cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))

    for row in MINIMAL_DEFAULT_CATEGORIES:
        cur.execute(
            """
            INSERT OR IGNORE INTO categories(name, kind, expense_scope, is_fixed_default, is_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            row,
        )

    # Fix existing "Расход" category that was created with NULL scope
    cur.execute(
        "UPDATE categories SET expense_scope = 'variable_life' WHERE name = 'Расход' AND expense_scope IS NULL"
    )

    conn.commit()
    conn.close()
