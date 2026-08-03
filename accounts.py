"""
Minimal username/password accounts for the demo dashboard - just
enough so each friend testing the bot can log back in and see their
own balance and trade history, not shared security infrastructure.

Passwords are salted + hashed (never stored in plaintext), but there's
no email verification, password reset, or rate limiting - this is a
demo-funds testing tool, not a real financial account system. Don't
reuse a real/important password here.
"""

import json
import os
import re
import hashlib
import secrets

USERS_FILE = "state/users.json"


def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def _save_users(users: dict):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _hash_password(password: str, salt: str = None) -> tuple:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return digest, salt


def normalize_username(raw: str) -> str:
    """Lowercase, alphanumeric + underscore/hyphen only, 3-20 chars.
    Used both for display and as a filesystem-safe key for that user's
    state files."""
    raw = (raw or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_-]", "", raw)
    return raw[:20]


def register_or_login(username: str, password: str) -> tuple:
    """Returns (ok: bool, message: str).
    If the username doesn't exist yet, creates it with this password.
    If it exists, checks the password matches."""
    username = normalize_username(username)
    if len(username) < 3:
        return False, "username must be at least 3 characters (letters, numbers, _ or -)"
    if len(password) < 4:
        return False, "password must be at least 4 characters"

    users = _load_users()

    if username in users:
        record = users[username]
        digest, _ = _hash_password(password, record["salt"])
        if digest != record["hash"]:
            return False, "wrong password for that username"
        return True, "logged in"

    digest, salt = _hash_password(password)
    users[username] = {"hash": digest, "salt": salt}
    _save_users(users)
    return True, "account created"
