from __future__ import annotations

import hashlib
import os
from typing import Optional, Tuple

from db.connection import get_conn


def _hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
    """Hash password with SHA-256 + random salt. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = os.urandom(32)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return pw_hash.hex(), salt.hex()


def _verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    salt = bytes.fromhex(stored_salt)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return pw_hash.hex() == stored_hash


def create_user(username: str, password: str, display_name: str = "") -> int | None:
    """Register a new user. Returns user_id or None if username taken."""
    pw_hash, salt = _hash_password(password)
    # Store as "hash:salt" in password_hash column
    combined = f"{pw_hash}:{salt}"
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users(username, password_hash, display_name) VALUES (?, ?, ?)",
            (username.strip(), combined, display_name.strip() or username.strip()),
        )
        conn.commit()
        user_id = cur.lastrowid
        return user_id
    except Exception:
        return None
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    """Check credentials. Returns user dict or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, password_hash, display_name FROM users WHERE username = ?",
        (username.strip(),),
    ).fetchone()
    conn.close()

    if row is None:
        return None

    stored = row["password_hash"]
    if ":" not in stored:
        return None

    stored_hash, stored_salt = stored.split(":", 1)
    if _verify_password(password, stored_hash, stored_salt):
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
        }
    return None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, display_name FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}
    return None
