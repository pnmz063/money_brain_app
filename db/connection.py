import os
import sqlite3
from pathlib import Path

# Local dev: DB рядом с проектом.
# Streamlit Cloud: /tmp/ (writable).
# Переменная окружения BUDGET_DB_DIR позволяет задать путь явно.

_default_dir = Path(__file__).resolve().parent.parent
_db_dir = Path(os.environ.get("BUDGET_DB_DIR", ""))

if _db_dir == Path(""):
    # Проверяем, можно ли писать в каталог проекта
    try:
        _test = _default_dir / ".write_test"
        _test.touch()
        _test.unlink()
        _db_dir = _default_dir
    except OSError:
        _db_dir = Path("/tmp")

DB_PATH = _db_dir / "budget_mvp.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
