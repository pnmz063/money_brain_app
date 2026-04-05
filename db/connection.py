from __future__ import annotations

import os

import psycopg2
import psycopg2.extras


def _get_database_url() -> str:
    """Read DATABASE_URL from env or Streamlit secrets."""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL", "")
        return url
    except Exception:
        return ""


def get_conn():
    """Return a plain psycopg2 connection (no cursor_factory).

    Use this for pd.read_sql_query — pandas manages cursors itself.
    For manual dict-cursor queries, call:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    """
    url = _get_database_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL не задана. "
            "Добавь Supabase connection string в .streamlit/secrets.toml "
            "или в переменную окружения DATABASE_URL."
        )
    conn = psycopg2.connect(url, connect_timeout=10)
    conn.autocommit = False
    return conn


def dict_cursor(conn):
    """Create a RealDictCursor from an existing connection."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
