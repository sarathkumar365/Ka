"""Accounts: open sign-up with an opaque id, then username and password login.

Repeated wrong passwords are limited per address and username in api/auth.py, so nobody can
lock another person out from somewhere else.
"""

import re
import secrets
import sqlite3
from datetime import datetime

from server.store.db import Db

from .passwords import check_password, hash_password

USERNAME = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
MIN_PASSWORD = 10
WRONG = "wrong username or password"
# Checked when the username is unknown, so timing does not tell which part was wrong.
_DUMMY = hash_password("not a real password")


class AuthError(Exception):
    """Safe to show at the login screen."""


TAKEN = "that username is taken"


def user_id_for(db: Db, username: str) -> str | None:
    row = db.conn.execute("select id from users where username=?", (username,)).fetchone()
    return row[0] if row else None


def create_user(db: Db, username: str, password: str, now: datetime) -> str:
    """A new account; its id is random so it never reveals or reuses the username."""
    if not USERNAME.match(username):
        raise AuthError(
            "username: 3 to 32 lower-case letters, digits, - or _, starting with a letter"
        )
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"password: at least {MIN_PASSWORD} characters")
    user_id = f"u_{secrets.token_hex(6)}"
    try:
        with db.conn:
            db.conn.execute(
                "insert into users (id, username, password_hash, created_at) values (?,?,?,?)",
                (user_id, username, hash_password(password), now.isoformat()),
            )
    except sqlite3.IntegrityError:
        raise AuthError(TAKEN) from None
    return user_id


def delete_user(db: Db, user_id: str) -> None:
    """Undo a sign-up whose folder could not be made."""
    with db.conn:
        db.conn.execute("delete from sessions where user_id=?", (user_id,))
        db.conn.execute("delete from users where id=?", (user_id,))


def authenticate(db: Db, username: str, password: str, now: datetime) -> str:
    row = db.conn.execute(
        "select id, password_hash from users where username=?",
        (username,),
    ).fetchone()
    if row is None:
        check_password(_DUMMY, password)
        raise AuthError(WRONG)
    uid, stored = row[0], row[1]
    if not check_password(stored, password):
        raise AuthError(WRONG)
    return uid
